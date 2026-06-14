from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func

from app.db.database import Base


class HydrationLog(Base):
    __tablename__ = "hydration_logs"
    __table_args__ = (
        Index("idx_hydration_logs_user_date", "user_id", "log_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    log_date = Column(Date, nullable=False)
    water_ml = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
