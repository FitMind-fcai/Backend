from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.services.notification_service import NotificationService


def get_device_token_repository(db: Session = Depends(get_db)) -> DeviceTokenRepository:
    return DeviceTokenRepository(db)


def get_notification_preference_repository(db: Session = Depends(get_db)) -> NotificationPreferenceRepository:
    return NotificationPreferenceRepository(db)


def get_notification_service(
    token_repo: DeviceTokenRepository = Depends(get_device_token_repository),
    pref_repo: NotificationPreferenceRepository = Depends(get_notification_preference_repository),
) -> NotificationService:
    return NotificationService(token_repo=token_repo, pref_repo=pref_repo)
