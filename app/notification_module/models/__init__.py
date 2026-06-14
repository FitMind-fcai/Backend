"""Notification model exports."""

from app.notification_module.models.device_token import DeviceToken
from app.notification_module.models.notification_preference import NotificationPreference

__all__ = ["DeviceToken", "NotificationPreference"]
