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
