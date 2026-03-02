"""Pydantic schemas for Account API."""

from datetime import datetime
from pydantic import BaseModel


class AccountCreate(BaseModel):
    """Schema for creating a new account."""
    email: str
    provider: str = "Google"
    label: str | None = None
    refresh_token: str | None = None


class AccountUpdate(BaseModel):
    """Schema for updating an account."""
    email: str | None = None
    provider: str | None = None
    label: str | None = None
    status: str | None = None
    is_disabled: bool | None = None


class AccountResponse(BaseModel):
    """Schema for account API response."""
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    avatar_cached: bool = False
    provider: str
    status: str
    label: str | None = None
    quota_percent: float
    is_forbidden: bool
    is_disabled: bool
    token_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_sync_at: datetime | None = None

    # Detailed status & quota
    tier: str | None = None
    status_reason: str | None = None
    status_details: dict | None = None
    ineligible_tiers: list[dict] | None = None
    quota_buckets: list[dict] | None = None
    models: list[dict] | None = None
    device_profile: dict | None = None

    # Credentials summary (per-client data)
    class CredentialSummary(BaseModel):
        client_type: str
        updated_at: datetime
        token_expires_at: datetime | None = None
        tier: str | None = None
        project_id: str | None = None
        models: list[dict] | None = None
        quota_data: list[dict] | None = None
        last_sync_at: datetime | None = None
        
        model_config = {"from_attributes": True}
    
    credentials: list[CredentialSummary] = []

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    """Schema for paginated account list."""
    items: list[AccountResponse]
    total: int
