"""Notification schema exports."""

from app.notification_module.schemas.notifications import (
    DeviceTokenRegister,
    DeviceTokenResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)

__all__ = [
    "DeviceTokenRegister",
    "DeviceTokenResponse",
    "NotificationPreferenceResponse",
    "NotificationPreferenceUpdate",
]
