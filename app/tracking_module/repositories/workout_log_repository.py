from typing import List, Optional
from datetime import date

from sqlalchemy.orm import Session

from app.shared.repositories.base_repository import BaseRepository
from app.tracking_module.models.workout_log import WorkoutLog


class WorkoutLogRepository(BaseRepository[WorkoutLog]):
    def __init__(self, db: Session):
        super().__init__(WorkoutLog, db)

    def create_log(
        self,
        user_id: int,
        central_exercise_id: Optional[int],
        log_date: date,
        sets_completed: int,
        reps_completed: int,
        workout_day_exercise_id: Optional[int] = None,
        weight_used: Optional[float] = None,
        duration_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> WorkoutLog:
        payload = {
            "user_id": user_id,
            "central_exercise_id": central_exercise_id,
            "workout_day_exercise_id": workout_day_exercise_id,
            "log_date": log_date,
            "sets_completed": sets_completed,
            "reps_completed": reps_completed,
            "weight_used": weight_used,
            "duration_seconds": duration_seconds,
            "notes": notes,
        }
        return self.create(payload)

    def list_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None) -> List[WorkoutLog]:
        query = self.db.query(WorkoutLog).filter(WorkoutLog.user_id == user_id)
        if log_date is not None:
            query = query.filter(WorkoutLog.log_date == log_date)
        return query.order_by(WorkoutLog.log_date.desc(), WorkoutLog.id.desc()).offset(skip).limit(limit).all()

    def list_logs_since(self, user_id: int, since: date, until: Optional[date] = None) -> List[WorkoutLog]:
        query = self.db.query(WorkoutLog).filter(
            WorkoutLog.user_id == user_id,
            WorkoutLog.log_date >= since,
        )
        if until is not None:
            query = query.filter(WorkoutLog.log_date <= until)
        return query.order_by(WorkoutLog.log_date.asc(), WorkoutLog.id.asc()).all()
