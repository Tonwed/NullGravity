"""Pydantic schemas for request logs."""

from datetime import datetime, timezone
from typing import Optional, Dict

from pydantic import BaseModel, ConfigDict, field_serializer

class LogAccount(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)

class LogEntry(BaseModel):
    id: int
    timestamp: datetime
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: Optional[str] = None
    request_headers: Optional[Dict] = None
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    error_detail: Optional[str] = None
    account: Optional[LogAccount] = None

    @field_serializer("timestamp")
    def serialize_dt(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    model_config = ConfigDict(from_attributes=True)

class LogListResponse(BaseModel):
    items: list[LogEntry]
    total: int
    page: int
    page_size: int
