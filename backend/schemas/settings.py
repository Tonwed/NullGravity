"""Pydantic schemas for Settings API."""

from pydantic import BaseModel


class SettingUpdate(BaseModel):
    """Schema for updating a setting."""
    key: str
    value: str


class SettingResponse(BaseModel):
    """Schema for a single setting response."""
    key: str
    value: str

    model_config = {"from_attributes": True}


class SettingsResponse(BaseModel):
    """Schema for all settings response."""
    settings: dict[str, str]
