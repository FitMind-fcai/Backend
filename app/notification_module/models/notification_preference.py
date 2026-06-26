from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, text
from sqlalchemy.sql import func

from app.db.database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    meal_reminders_enabled      = Column(Boolean, default=True, nullable=False)
    hydration_reminders_enabled = Column(Boolean, default=True, nullable=False)
    sleep_reminders_enabled     = Column(Boolean, default=True, nullable=False)
    coaching_reminders_enabled  = Column(Boolean, default=True, server_default=text("true"), nullable=False)

    hydration_interval_hours     = Column(Integer, default=2, nullable=False)
    meal_reminder_minutes_before = Column(Integer, default=15, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
