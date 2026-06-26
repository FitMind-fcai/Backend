from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DeviceTokenRegister(BaseModel):
    token: str
    platform: Literal["android", "ios"]


class DeviceTokenResponse(BaseModel):
    id: int
    token: str
    platform: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    meal_reminders_enabled: Optional[bool] = None
    hydration_reminders_enabled: Optional[bool] = None
    sleep_reminders_enabled: Optional[bool] = None
    coaching_reminders_enabled: Optional[bool] = None
    hydration_interval_hours: Optional[int] = Field(default=None, ge=1, le=24)
    meal_reminder_minutes_before: Optional[int] = Field(default=None, ge=0, le=60)


class NotificationPreferenceResponse(BaseModel):
    meal_reminders_enabled: bool
    hydration_reminders_enabled: bool
    sleep_reminders_enabled: bool
    coaching_reminders_enabled: bool
    hydration_interval_hours: int
    meal_reminder_minutes_before: int

    model_config = {"from_attributes": True}
