"""Account database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base


class Account(Base):
    """AI service account model."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    avatar_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="Google")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # OAuth tokens (Legacy: now stored in OAuthCredential table)
    # These fields can be kept for backward compatibility or migration
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_scope: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Multi-client credentials relationship
    credentials: Mapped[list["OAuthCredential"]] = relationship(
        "OAuthCredential", back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )

    # Account state
    quota_percent: Mapped[float] = mapped_column(Float, default=100.0)
    is_forbidden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Detailed status & quota
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ineligible_tiers: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    quota_buckets: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    models: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Device fingerprint for account isolation
    device_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, email={self.email}, provider={self.provider})>"
