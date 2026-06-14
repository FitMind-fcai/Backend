from typing import List, Optional

from sqlalchemy.orm import Session

from app.notification_module.models.device_token import DeviceToken


class DeviceTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, user_id: int, token: str, platform: str) -> DeviceToken:
        existing = self.db.query(DeviceToken).filter(DeviceToken.token == token).first()
        if existing:
            existing.user_id   = user_id
            existing.platform  = platform
            existing.is_active = True
            self.db.commit()
            self.db.refresh(existing)
            return existing
        record = DeviceToken(user_id=user_id, token=token, platform=platform)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def deactivate(self, token: str) -> None:
        self.db.query(DeviceToken).filter(DeviceToken.token == token).update({"is_active": False})
        self.db.commit()

    def deactivate_all_for_user(self, user_id: int) -> None:
        self.db.query(DeviceToken).filter(DeviceToken.user_id == user_id).update({"is_active": False})
        self.db.commit()

    def get_active_tokens_for_user(self, user_id: int) -> List[DeviceToken]:
        return (
            self.db.query(DeviceToken)
            .filter(DeviceToken.user_id == user_id, DeviceToken.is_active == True)
            .all()
        )

    def get_all_active(self) -> List[DeviceToken]:
        return self.db.query(DeviceToken).filter(DeviceToken.is_active == True).all()
