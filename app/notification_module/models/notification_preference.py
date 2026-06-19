from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func

from app.db.database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    meal_reminders_enabled     = Column(Boolean, default=True, nullable=False)
    workout_reminders_enabled  = Column(Boolean, default=True, nullable=False)
    hydration_reminders_enabled = Column(Boolean, default=True, nullable=False)
    sleep_reminders_enabled    = Column(Boolean, default=True, nullable=False)

    # How many hours between hydration reminders (if no log exists)
    hydration_interval_hours = Column(Integer, default=2, nullable=False)
    # Minutes before the canonical meal time to fire the reminder
    meal_reminder_minutes_before = Column(Integer, default=15, nullable=False)
    # UTC hour at which to send the workout reminder (0-23)
    workout_reminder_hour = Column(Integer, default=7, nullable=False)
    # UTC hour at which to send the sleep reminder (0-23)
    sleep_reminder_hour = Column(Integer, default=21, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
