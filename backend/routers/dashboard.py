"""Dashboard statistics API routes."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.connection import get_session
from models.account import Account
from models.credential import OAuthCredential
from models.log import Log
from models.event import Event
import utils.proxy as proxy_utils
from services.proxy_logger import get_proxy_logger


router = APIRouter()


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class AccountQuotaSummary(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    avatar_cached: bool = False
    provider: str = "Google"
    status: str = "active"
    tier: str | None = None
    is_forbidden: bool = False
    status_reason: str | None = None
    # Per-client model quota
    gemini_models: list[dict] | None = None
    antigravity_models: list[dict] | None = None
    last_sync_at: str | None = None
    has_gemini: bool = False
    has_antigravity: bool = False


class EventItem(BaseModel):
    id: int
    type: str
    level: str  # info, success, warning, error
    message: str
    timestamp: str | None
    account_email: str | None = None
    account_avatar: str | None = None

class DashboardStats(BaseModel):
    # Counts
    total_accounts: int = 0
    active_accounts: int = 0
    forbidden_accounts: int = 0
    validation_required_accounts: int = 0
    # Request stats
    total_requests: int = 0
    requests_today: int = 0
    success_rate: float | None = None
    avg_latency_ms: float | None = None
    # System
    proxy_enabled: bool = False
    proxy_connected: bool | None = None
    proxy_ip: str | None = None
    proxy_latency_ms: float | None = None
    auto_refresh_enabled: bool = False
    backend_uptime_seconds: float | None = None
    # Account quota summaries
    accounts: list[AccountQuotaSummary] = []
    # Recent Events (Business Logic)
    recent_events: list[EventItem] = []


# Track backend start time
import time as _time
_backend_start_time = _time.time()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get comprehensive dashboard statistics."""
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- Account Stats ---
    accounts_result = await session.execute(
        select(Account).options(selectinload(Account.credentials))
    )
    accounts = list(accounts_result.scalars().all())

    total_accounts = len(accounts)
    active_accounts = sum(
        1 for a in accounts
        if a.status == "active" and not a.is_forbidden and not a.is_disabled
    )
    forbidden_accounts = sum(1 for a in accounts if a.is_forbidden)
    validation_required = sum(
        1 for a in accounts if a.status_reason == "VALIDATION_REQUIRED"
    )

    # --- Request Stats ---
    total_requests_result = await session.execute(select(func.count(Log.id)))
    total_requests = total_requests_result.scalar() or 0

    requests_today_result = await session.execute(
        select(func.count(Log.id)).where(Log.timestamp >= today_start)
    )
    requests_today = requests_today_result.scalar() or 0

    # Success rate (2xx responses)
    if total_requests > 0:
        success_result = await session.execute(
            select(func.count(Log.id)).where(
                and_(Log.status_code >= 200, Log.status_code < 300)
            )
        )
        success_count = success_result.scalar() or 0
        success_rate = round((success_count / total_requests) * 100, 1)
    else:
        success_rate = None

    # Average latency
    avg_latency_result = await session.execute(select(func.avg(Log.duration_ms)))
    avg_latency = avg_latency_result.scalar()
    avg_latency_ms = round(avg_latency, 1) if avg_latency is not None else None

    # --- Proxy Status ---
    proxy_enabled = proxy_utils._proxy_enabled
    proxy_connected = proxy_utils._proxy_status.get("connected") if proxy_enabled else None
    proxy_ip = proxy_utils._proxy_status.get("ip") if proxy_enabled else None
    proxy_latency = proxy_utils._proxy_status.get("latency_ms") if proxy_enabled else None

    # --- Auto Refresh ---
    from models.settings import AppSettings
    auto_refresh_result = await session.execute(
        select(AppSettings).where(AppSettings.key == "auto_refresh_enabled")
    )
    auto_refresh_setting = auto_refresh_result.scalar_one_or_none()
    auto_refresh_enabled = (
        auto_refresh_setting.value == "true" if auto_refresh_setting else False
    )

    # --- Account Summaries ---
    account_summaries = []
    for acc in accounts:
        gemini_creds = [c for c in acc.credentials if c.client_type == "gemini_cli"]
        antigravity_creds = [c for c in acc.credentials if c.client_type == "antigravity"]

        gemini_models = None
        if gemini_creds and gemini_creds[0].models:
            gemini_models = gemini_creds[0].models

        antigravity_models = None
        if antigravity_creds and antigravity_creds[0].models:
            antigravity_models = antigravity_creds[0].models

        last_sync = acc.last_sync_at.isoformat() if acc.last_sync_at else None

        account_summaries.append(AccountQuotaSummary(
            id=acc.id,
            email=acc.email,
            display_name=acc.display_name,
            avatar_url=acc.avatar_url,
            avatar_cached=acc.avatar_cached,
            provider=acc.provider,
            status=acc.status,
            tier=acc.tier,
            is_forbidden=acc.is_forbidden,
            status_reason=acc.status_reason,
            gemini_models=gemini_models,
            antigravity_models=antigravity_models,
            last_sync_at=last_sync,
            has_gemini=len(gemini_creds) > 0,
            has_antigravity=len(antigravity_creds) > 0,
        ))

    # --- Recent Events ---
    recent_events_result = await session.execute(
        select(Event)
        .options(selectinload(Event.account))
        .order_by(Event.timestamp.desc())
        .limit(10)
    )
    recent_events_raw = recent_events_result.scalars().all()
    recent_events = []
    for evt in recent_events_raw:
        recent_events.append(EventItem(
            id=evt.id,
            type=evt.type,
            level=evt.level,
            message=evt.message,
            timestamp=evt.timestamp.isoformat() if evt.timestamp else None,
            account_email=evt.account.email if evt.account else None,
            account_avatar=f"/api/accounts/{evt.account.id}/avatar" if evt.account and evt.account.avatar_cached else None,
        ))

    # --- Backend Uptime ---
    uptime_seconds = _time.time() - _backend_start_time

    return DashboardStats(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        forbidden_accounts=forbidden_accounts,
        validation_required_accounts=validation_required,
        total_requests=total_requests,
        requests_today=requests_today,
        success_rate=success_rate,
        avg_latency_ms=avg_latency_ms,
        proxy_enabled=proxy_enabled,
        proxy_connected=proxy_connected,
        proxy_ip=proxy_ip,
        proxy_latency_ms=proxy_latency,
        auto_refresh_enabled=auto_refresh_enabled,
        backend_uptime_seconds=round(uptime_seconds, 0),
        accounts=account_summaries,
        recent_events=recent_events,
    )


# ---------------------------------------------------------------------------
# Token Statistics
# ---------------------------------------------------------------------------

class TokenStats(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    by_model: list[dict] = []
    by_account: list[dict] = []
    top_models: list[dict] = []
    time_series: list[dict] = []
    series_keys: list[str] = []  # 新增：系列名称列表


@router.get("/token-stats", response_model=TokenStats)
async def get_token_stats(
    time_range: str = "24h", 
    group_by: str = "total",  # total, model, api_token
    session: AsyncSession = Depends(get_session)
):
    """Get token usage statistics from database."""
    from models.proxy_log import ProxyLog
    from datetime import timedelta
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    
    now = datetime.now(timezone.utc)
    if time_range == "24h":
        cutoff = now - timedelta(hours=24)
    elif time_range == "7d":
        cutoff = now - timedelta(days=7)
    elif time_range == "30d":
        cutoff = now - timedelta(days=30)
    else:
        cutoff = now - timedelta(hours=24)
    
    # 查询数据库，预加载 account 关系
    result = await session.execute(
        select(ProxyLog).options(selectinload(ProxyLog.account)).where(ProxyLog.timestamp >= cutoff)
    )
    logs = result.scalars().all()
    
    total_requests = len(logs)
    total_input = sum(log.input_tokens for log in logs)
    total_output = sum(log.output_tokens for log in logs)
    
    # 按模型统计
    model_stats = {}
    for log in logs:
        if log.model not in model_stats:
            model_stats[log.model] = {"model": log.model, "requests": 0, "input_tokens": 0, "output_tokens": 0}
        model_stats[log.model]["requests"] += 1
        model_stats[log.model]["input_tokens"] += log.input_tokens
        model_stats[log.model]["output_tokens"] += log.output_tokens
    
    by_model = sorted(model_stats.values(), key=lambda x: x["requests"], reverse=True)
    
    # 按账号统计
    account_stats = {}
    for log in logs:
        email = log.account.email if log.account else "unknown"
        if email not in account_stats:
            account_stats[email] = {"email": email, "requests": 0, "input_tokens": 0, "output_tokens": 0}
        account_stats[email]["requests"] += 1
        account_stats[email]["input_tokens"] += log.input_tokens
        account_stats[email]["output_tokens"] += log.output_tokens
    
    # 按 API Token 统计
    token_stats = {}
    for log in logs:
        if log.api_token_id:
            if log.api_token_id not in token_stats:
                token_stats[log.api_token_id] = {"token_id": log.api_token_id, "requests": 0, "input_tokens": 0, "output_tokens": 0}
            token_stats[log.api_token_id]["requests"] += 1
            token_stats[log.api_token_id]["input_tokens"] += log.input_tokens
            token_stats[log.api_token_id]["output_tokens"] += log.output_tokens
    
    by_token = sorted(token_stats.values(), key=lambda x: x["requests"], reverse=True)[:10]
    
    by_account = sorted(account_stats.values(), key=lambda x: x["requests"], reverse=True)[:10]
    top_models = [{"model": m["model"], "count": m["requests"]} for m in by_model[:5]]
    
    # 生成时间序列数据（使用北京时间 UTC+8）
    beijing_tz = timezone(timedelta(hours=8))
    time_series = []
    series_keys = []
    
    if group_by == "model":
        # 按模型分组，只显示有数据的模型
        top_models_list = [m["model"] for m in by_model[:10]]
        series_keys = top_models_list
        
        if time_range == "24h":
            temp_series = []
            for i in range(24):
                hour_start = cutoff + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                beijing_time = hour_start.astimezone(beijing_tz)
                data_point = {"time": beijing_time.strftime("%H:00"), "hour": beijing_time.hour}
                for model in top_models_list:
                    model_logs = [log for log in logs if hour_start <= log.timestamp.replace(tzinfo=timezone.utc) < hour_end and log.model == model]
                    data_point[model] = sum(log.input_tokens + log.output_tokens for log in model_logs)
                temp_series.append(data_point)
            temp_series.sort(key=lambda x: (x["hour"] - 6) % 24)
            time_series = [{k: v for k, v in item.items() if k != "hour"} for item in temp_series]
    elif group_by == "user":
        # 按 API Token 分组
        if not by_token:
            # 如果没有 token 数据，返回空
            series_keys = []
            time_series = []
        else:
            series_keys = [t["token_id"] for t in by_token]
            
            # 获取 token 名称映射
            from models.api_token import ApiToken
            token_result = await session.execute(select(ApiToken).where(ApiToken.id.in_(series_keys)))
            tokens = {t.id: t.name for t in token_result.scalars().all()}
            
            # 使用 token 名称作为 series_keys
            series_keys = [tokens.get(tid, tid[:8]) for tid in series_keys]
            token_id_to_name = {tid: tokens.get(tid, tid[:8]) for tid in [t["token_id"] for t in by_token]}
            
            if time_range == "24h":
                temp_series = []
                for i in range(24):
                    hour_start = cutoff + timedelta(hours=i)
                    hour_end = hour_start + timedelta(hours=1)
                    beijing_time = hour_start.astimezone(beijing_tz)
                    data_point = {"time": beijing_time.strftime("%H:00"), "hour": beijing_time.hour}
                    for token_id, token_name in token_id_to_name.items():
                        token_logs = [log for log in logs if hour_start <= log.timestamp.replace(tzinfo=timezone.utc) < hour_end and log.api_token_id == token_id]
                        data_point[token_name] = sum(log.input_tokens + log.output_tokens for log in token_logs)
                    temp_series.append(data_point)
                temp_series.sort(key=lambda x: (x["hour"] - 6) % 24)
                time_series = [{k: v for k, v in item.items() if k != "hour"} for item in temp_series]
    elif group_by == "account":
        # 按账号分组
        top_accounts = by_account[:10]
        series_keys = [acc["email"] for acc in top_accounts]
        
        if time_range == "24h":
            temp_series = []
            for i in range(24):
                hour_start = cutoff + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                beijing_time = hour_start.astimezone(beijing_tz)
                data_point = {"time": beijing_time.strftime("%H:00"), "hour": beijing_time.hour}
                for email in series_keys:
                    account_logs = [log for log in logs if hour_start <= log.timestamp.replace(tzinfo=timezone.utc) < hour_end and (log.account.email if log.account else "unknown") == email]
                    data_point[email] = sum(log.input_tokens + log.output_tokens for log in account_logs)
                temp_series.append(data_point)
            temp_series.sort(key=lambda x: (x["hour"] - 6) % 24)
            time_series = [{k: v for k, v in item.items() if k != "hour"} for item in temp_series]
    else:
        # 总体（不分组）
        series_keys = ["tokens"]
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
                    "tokens": sum(log.input_tokens + log.output_tokens for log in hour_logs) if hour_logs else 0,
                })
            temp_series.sort(key=lambda x: (x["hour"] - 6) % 24)
            time_series = [{"time": item["time"], "tokens": item["tokens"]} for item in temp_series]
        elif time_range == "7d":
            for i in range(7):
                day_start = cutoff + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                day_logs = [log for log in logs if day_start <= log.timestamp.replace(tzinfo=timezone.utc) < day_end]
                time_series.append({
                    "time": day_start.astimezone(beijing_tz).strftime("%m/%d"),
                    "tokens": sum(log.input_tokens + log.output_tokens for log in day_logs) if day_logs else 0,
                })
        else:  # 30d
            for i in range(30):
                day_start = cutoff + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                day_logs = [log for log in logs if day_start <= log.timestamp.replace(tzinfo=timezone.utc) < day_end]
                time_series.append({
                    "time": day_start.astimezone(beijing_tz).strftime("%m/%d"),
                    "tokens": sum(log.input_tokens + log.output_tokens for log in day_logs) if day_logs else 0,
                })
    
    return TokenStats(
        total_requests=total_requests,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
        by_model=by_model,
        by_account=by_account,
        top_models=top_models,
        time_series=time_series,
        series_keys=series_keys,
    )
