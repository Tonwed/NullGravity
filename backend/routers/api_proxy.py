"""
API Proxy Router — Management endpoints for the CloudCode reverse proxy.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from services.cloudcode_proxy import (
    get_proxy_state,
    get_pool,
    start_proxy,
    stop_proxy,
    DEFAULT_PROXY_PORT,
    UPSTREAM_DAILY,
    UPSTREAM_PROD,
)
from services.proxy_logger import get_proxy_logger

router = APIRouter()


class ProxyStartRequest(BaseModel):
    port: int = DEFAULT_PROXY_PORT
    upstream: str = UPSTREAM_DAILY


class ProxyStatusResponse(BaseModel):
    running: bool
    port: int
    upstream: str
    total_requests: int
    total_rotations: int
    started_at: str | None
    current_account_email: str | None
    current_account_id: str | None
    pool_size: int
    pool_available: int


@router.get("/status")
async def proxy_status():
    """Get the current proxy status including per-account details."""
    state = get_proxy_state()
    pool = get_pool()
    pool_accounts = await pool.get_account_statuses_with_email()
    schedule_mode = await pool._get_schedule_mode()
    cooldown = await pool._get_cooldown_seconds()
    return {
        **state,
        "pool_size": len(pool_accounts),
        "pool_available": sum(1 for a in pool_accounts if a["status"] == "available"),
        "pool_accounts": pool_accounts,
        "schedule_mode": schedule_mode,
        "pool_cooldown": cooldown,
    }


@router.post("/start")
async def proxy_start(req: ProxyStartRequest | None = None):
    """Start the CloudCode reverse proxy."""
    port = req.port if req else DEFAULT_PROXY_PORT
    upstream = req.upstream if req else UPSTREAM_DAILY

    state = get_proxy_state()
    if state["running"]:
        return {"success": False, "error": "Proxy is already running", **get_proxy_state()}

    await start_proxy(port=port, upstream=upstream)
    return {"success": True, **get_proxy_state(), "pool_size": get_pool().size}


@router.post("/stop")
async def proxy_stop():
    """Stop the CloudCode reverse proxy."""
    await stop_proxy()
    return {"success": True, **get_proxy_state()}


@router.post("/refresh-pool")
async def refresh_pool():
    """Refresh the account pool from the database."""
    pool = get_pool()
    await pool.refresh()
    return {
        "success": True,
        "pool_size": pool.size,
        "pool_available": pool.available_count,
    }


@router.get("/pool")
async def get_pool_info():
    """Get account pool details."""
    pool = get_pool()
    state = get_proxy_state()
    return {
        "pool_size": pool.size,
        "pool_available": pool.available_count,
        "current_account_email": state.get("current_account_email"),
        "current_account_id": state.get("current_account_id"),
    }


@router.get("/logs")
async def get_proxy_logs(limit: int = 100, offset: int = 0):
    """Get proxy-specific request logs (separate from main backend logs)."""
    plog = get_proxy_logger()
    return {
        "items": plog.get_logs(limit=limit, offset=offset),
        "total": plog.get_count(),
    }


@router.delete("/logs")
async def clear_proxy_logs():
    """Clear all proxy request logs."""
    plog = get_proxy_logger()
    plog.clear()
    return {"success": True}
