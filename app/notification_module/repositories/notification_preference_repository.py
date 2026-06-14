from typing import List

from sqlalchemy.orm import Session

from app.notification_module.models.notification_preference import NotificationPreference


class NotificationPreferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, user_id: int) -> NotificationPreference:
        pref = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).first()
        if not pref:
            pref = NotificationPreference(user_id=user_id)
            self.db.add(pref)
            self.db.commit()
            self.db.refresh(pref)
        return pref

    def update(self, user_id: int, **kwargs) -> NotificationPreference:
        pref = self.get_or_create(user_id)
        for key, val in kwargs.items():
            setattr(pref, key, val)
        self.db.commit()
        self.db.refresh(pref)
        return pref

    def get_with_hydration_enabled(self) -> List[NotificationPreference]:
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.hydration_reminders_enabled == True
        ).all()

    def get_with_meal_enabled(self) -> List[NotificationPreference]:
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.meal_reminders_enabled == True
        ).all()

    def get_with_workout_enabled(self) -> List[NotificationPreference]:
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.workout_reminders_enabled == True
        ).all()

    def get_with_sleep_enabled(self) -> List[NotificationPreference]:
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.sleep_reminders_enabled == True
        ).all()
