from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func

from app.db.database import Base


class SleepLog(Base):
    __tablename__ = "sleep_logs"
    __table_args__ = (
        Index("idx_sleep_logs_user_date", "user_id", "log_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    log_date = Column(Date, nullable=False)
    sleep_hours = Column(Float, nullable=False)
    sleep_quality = Column(Integer, nullable=False)  # 1–10
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
