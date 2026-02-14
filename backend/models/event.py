from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import Optional, Any

from database.connection import Base
from models.account import Account

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(50), index=True)  # e.g., "account.create", "system.start"
    level: Mapped[str] = mapped_column(String(20), default="info")  # info, success, warning, error
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    account_id: Mapped[Optional[str]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account: Mapped[Optional["Account"]] = relationship("Account", backref="events")
