"""OAuth Credential database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base


class OAuthCredential(Base):
    """Stores OAuth tokens for specific clients (Gemini CLI, Antigravity)."""

    __tablename__ = "oauth_credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # client_type: 'gemini_cli' or 'antigravity'
    client_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_scope: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Per-client synced data (models, quota, tier)
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    models: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    quota_data: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account = relationship("Account", back_populates="credentials")

    def __repr__(self) -> str:
        return f"<OAuthCredential(account_id={self.account_id}, client={self.client_type})>"
