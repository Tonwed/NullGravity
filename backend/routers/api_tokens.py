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
