"""Model mapping rules for API proxy."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from database.connection import Base


class ModelMapping(Base):
    """A mapping rule that rewrites model IDs before forwarding upstream."""

    __tablename__ = "model_mappings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pattern = Column(String(255), nullable=False)       # e.g. "claude-sonnet-4-5" or "claude-*"
    target = Column(String(255), nullable=False)         # e.g. "claude-opus-4-6-thinking"
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)                # lower = higher priority
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
