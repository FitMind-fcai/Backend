from fastapi import APIRouter, Depends, status

from app.auth_module.core.dependencies import get_current_verified_user
from app.auth_module.models.user import User
from app.notification_module.core.dependencies import get_notification_service
from app.notification_module.schemas.notifications import (
    DeviceTokenRegister,
    DeviceTokenResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.notification_module.services.notification_service import NotificationService

notification_router = APIRouter(prefix="/notifications")


@notification_router.post(
    "/device-token",
    response_model=DeviceTokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Notifications"],
    summary="Register or update FCM device token",
    description=(
        "Store the Firebase Cloud Messaging (FCM) device token for the current user. "
        "Call this after the app receives a new FCM token (on login, token refresh, etc.).\n\n"
        "If the same token was previously registered by another user it is reassigned. "
        "A user can have tokens from multiple devices."
    ),
)
def register_device_token(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_verified_user),
    service: NotificationService = Depends(get_notification_service),
) -> DeviceTokenResponse:
    return service.register_token(
        user_id=current_user.id,
        token=payload.token,
        platform=payload.platform,
    )


@notification_router.delete(
    "/device-token",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Notifications"],
    summary="Deregister device token",
    description="Mark a device token as inactive. Call this on logout so the device stops receiving notifications.",
)
def deregister_device_token(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_verified_user),
    service: NotificationService = Depends(get_notification_service),
):
    service.deregister_token(token=payload.token)


@notification_router.get(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    tags=["Notifications"],
    summary="Get notification preferences",
    description=(
        "Returns the current user's notification settings. "
        "Defaults are created automatically on first access."
    ),
)
def get_preferences(
    current_user: User = Depends(get_current_verified_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceResponse:
    return service.get_preferences(user_id=current_user.id)


@notification_router.put(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    tags=["Notifications"],
    summary="Update notification preferences",
    description=(
        "Partially update notification preferences. Only provided fields are changed.\n\n"
        "**Settable fields:**\n"
        "- `meal_reminders_enabled` / `workout_reminders_enabled` / `hydration_reminders_enabled` / `sleep_reminders_enabled` — toggle each reminder type\n"
        "- `hydration_interval_hours` (1–24) — send a reminder if no water logged in this many hours\n"
        "- `meal_reminder_minutes_before` (0–60) — how many minutes before the canonical meal time to fire the reminder\n"
        "- `workout_reminder_hour` (0–23 UTC) — hour of day to send the workout reminder\n"
        "- `sleep_reminder_hour` (0–23 UTC) — hour of day to send the sleep log reminder\n\n"
        "Canonical meal times: Breakfast 07:30, Lunch 13:00, Dinner 19:00, Snack 15:00 (all UTC)."
    ),
)
def update_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceResponse:
    return service.update_preferences(user_id=current_user.id, payload=payload)
