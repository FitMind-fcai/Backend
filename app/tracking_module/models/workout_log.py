from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Float, Text, Index # type: ignore
from sqlalchemy.sql import func # type: ignore

from app.db.database import Base


class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    __table_args__ = (
        Index("idx_workout_logs_user_date", "user_id", "log_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    central_exercise_id = Column(Integer, ForeignKey("central_exercises.id"), nullable=True, index=True)
    workout_day_exercise_id = Column(Integer, ForeignKey("workout_day_exercises.id"), nullable=True)

    log_date = Column(Date, nullable=False)
    sets_completed = Column(Integer, nullable=False)
    reps_completed = Column(Integer, nullable=False)
    weight_used = Column(Float, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
