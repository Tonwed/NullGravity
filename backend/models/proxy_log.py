"""Database model for proxy request logs."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base

class ProxyLog(Base):
    """Stores API proxy request logs with token usage."""
    __tablename__ = "proxy_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    api_format: Mapped[str] = mapped_column(String(20))  # openai, anthropic
    model: Mapped[str] = mapped_column(String(100))
    original_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stream: Mapped[bool] = mapped_column(Boolean, default=False)
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(5000), nullable=True)  # Increased from 500 to 5000 for full error messages
    client_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    account = relationship("Account")
    
    api_token_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("api_tokens.id", ondelete="SET NULL"), nullable=True)
    api_token = relationship("ApiToken")
