from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class CoachingMessage(Base):
    __tablename__ = "coaching_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    category = Column(String(30), nullable=False, index=True)  # "daily" | "weekly" | "alert"
    urgency = Column(String(20), nullable=False)  # "on_track" | "needs_attention" | "off_track"
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)

    is_read = Column(Boolean, default=False, nullable=False)
    is_dismissed = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
