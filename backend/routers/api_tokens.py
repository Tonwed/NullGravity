"""
API Token Router — CRUD endpoints for managing sk-xxx API tokens.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select, delete

from database.connection import async_session
from models.api_token import ApiToken, generate_sk_token

router = APIRouter()


class TokenCreateRequest(BaseModel):
    name: str


class TokenResponse(BaseModel):
    id: str
    name: str
    token: str
    is_active: bool
    total_requests: int
    last_used_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class TokenListResponse(BaseModel):
    items: list[TokenResponse]
    total: int


@router.get("/")
async def list_tokens():
    """List all API tokens."""
    async with async_session() as session:
        result = await session.execute(
            select(ApiToken).order_by(ApiToken.created_at.desc())
        )
        tokens = result.scalars().all()
        return {
            "items": [
                {
                    "id": t.id,
                    "name": t.name,
                    "token": t.token,
                    "is_active": t.is_active,
                    "total_requests": t.total_requests,
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tokens
            ],
            "total": len(tokens),
        }


@router.post("/")
async def create_token(req: TokenCreateRequest):
    """Create a new API token."""
    token = ApiToken(name=req.name)
    async with async_session() as session:
        session.add(token)
        await session.commit()
        await session.refresh(token)
        return {
            "id": token.id,
            "name": token.name,
            "token": token.token,
            "is_active": token.is_active,
            "total_requests": 0,
            "last_used_at": None,
            "created_at": token.created_at.isoformat() if token.created_at else None,
        }


@router.delete("/{token_id}")
async def delete_token(token_id: str):
    """Delete an API token."""
    async with async_session() as session:
        result = await session.execute(
            select(ApiToken).where(ApiToken.id == token_id)
        )
        token = result.scalar_one_or_none()
        if not token:
            return {"success": False, "error": "Token not found"}
        await session.delete(token)
        await session.commit()
        return {"success": True}


@router.patch("/{token_id}/toggle")
async def toggle_token(token_id: str):
    """Toggle a token's active status."""
    async with async_session() as session:
        result = await session.execute(
            select(ApiToken).where(ApiToken.id == token_id)
        )
        token = result.scalar_one_or_none()
        if not token:
            return {"success": False, "error": "Token not found"}
        token.is_active = not token.is_active
        await session.commit()
        return {"success": True, "is_active": token.is_active}


@router.post("/{token_id}/regenerate")
async def regenerate_token(token_id: str):
    """Regenerate a token's secret key."""
    async with async_session() as session:
        result = await session.execute(
            select(ApiToken).where(ApiToken.id == token_id)
        )
        token = result.scalar_one_or_none()
        if not token:
            return {"success": False, "error": "Token not found"}
        token.token = generate_sk_token()
        await session.commit()
        return {"success": True, "token": token.token}


@router.get("/{token_id}/usage")
async def get_token_usage(token_id: str, time_range: str = "24h"):
    """Get usage statistics for a specific token."""
    from models.proxy_log import ProxyLog
    from datetime import timedelta
    from sqlalchemy import func
    
    async with async_session() as session:
        # 计算时间范围
        now = datetime.now(timezone.utc)
        if time_range == "7d":
            cutoff = now - timedelta(days=7)
        elif time_range == "30d":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = now - timedelta(hours=24)
        
        # 查询该 token 的日志
        result = await session.execute(
            select(ProxyLog)
            .where(ProxyLog.api_token_id == token_id)
            .where(ProxyLog.timestamp >= cutoff)
        )
        logs = result.scalars().all()
        
        # 统计总数
        total_requests = len(logs)
        total_input = sum(log.input_tokens for log in logs)
        total_output = sum(log.output_tokens for log in logs)
        
        # 按模型统计
        model_stats = {}
        for log in logs:
            if log.model not in model_stats:
                model_stats[log.model] = {"model": log.model, "requests": 0, "tokens": 0}
            model_stats[log.model]["requests"] += 1
            model_stats[log.model]["tokens"] += log.input_tokens + log.output_tokens
        
        by_model = sorted(model_stats.values(), key=lambda x: x["requests"], reverse=True)
        
        # 生成时间序列
        beijing_tz = timezone(timedelta(hours=8))
        time_series = []
        if time_range == "24h":
            temp_series = []
            for i in range(24):
                hour_start = cutoff + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                hour_logs = [log for log in logs if hour_start <= log.timestamp.replace(tzinfo=timezone.utc) < hour_end]
                beijing_time = hour_start.astimezone(beijing_tz)
                temp_series.append({
                    "time": beijing_time.strftime("%H:00"),
                    "hour": beijing_time.hour,
                    "requests": len(hour_logs),
                    "tokens": sum(log.input_tokens + log.output_tokens for log in hour_logs),
                })
            temp_series.sort(key=lambda x: (x["hour"] - 6) % 24)
            time_series = [{"time": item["time"], "requests": item["requests"], "tokens": item["tokens"]} for item in temp_series]
        else:
            for i in range(7 if time_range == "7d" else 30):
                day_start = cutoff + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                day_logs = [log for log in logs if day_start <= log.timestamp.replace(tzinfo=timezone.utc) < day_end]
                time_series.append({
                    "time": day_start.astimezone(beijing_tz).strftime("%m/%d"),
                    "requests": len(day_logs),
                    "tokens": sum(log.input_tokens + log.output_tokens for log in day_logs),
                })
        
        # 获取 token 信息
        token_result = await session.execute(select(ApiToken).where(ApiToken.id == token_id))
        token = token_result.scalar_one_or_none()
        
        return {
            "token_id": token_id,
            "token_name": token.name if token else "Unknown",
            "total_requests": total_requests,
            "total_tokens": total_input + total_output,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "by_model": by_model,
            "time_series": time_series,
        }


async def validate_api_token(token_str: str) -> bool:
    """Validate an API token and update usage stats. Returns True if valid."""
    async with async_session() as session:
        result = await session.execute(
            select(ApiToken)
            .where(ApiToken.token == token_str)
            .where(ApiToken.is_active == True)
        )
        token = result.scalar_one_or_none()
        if not token:
            return False
        token.total_requests += 1
        token.last_used_at = datetime.now(timezone.utc)
        await session.commit()
        return True
