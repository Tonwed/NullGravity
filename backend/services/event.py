from sqlalchemy.ext.asyncio import AsyncSession
from models.event import Event
from typing import Optional, Any
from datetime import datetime, timezone

async def log_event(
    session: AsyncSession,
    type: str,
    message: str,
    level: str = "info",
    account_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None
) -> Event:
    """Log a business event."""
    event = Event(
        type=type,
        level=level,
        message=message,
        account_id=account_id,
        details=details,
        timestamp=datetime.now(timezone.utc)
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event
