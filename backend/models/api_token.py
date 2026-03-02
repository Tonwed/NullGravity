"""API Token database model."""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.connection import Base


def generate_sk_token() -> str:
    """Generate a sk-xxx style API token."""
    return f"sk-{secrets.token_hex(32)}"


class ApiToken(Base):
    """API tokens for authenticating OpenAI-compatible proxy requests."""

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, default=generate_sk_token
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<ApiToken(id={self.id}, name={self.name})>"
