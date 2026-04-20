from typing import List, Optional
from datetime import date

from sqlalchemy.orm import Session

from app.shared.repositories.base_repository import BaseRepository
from app.tracking_module.models.weight_log import WeightLog


class WeightLogRepository(BaseRepository[WeightLog]):
    def __init__(self, db: Session):
        super().__init__(WeightLog, db)

    def create_log(self, user_id: int, log_date: date, weight: float, notes: Optional[str] = None) -> WeightLog:
        payload = {
            "user_id": user_id,
            "log_date": log_date,
            "weight": weight,
            "notes": notes,
        }
        return self.create(payload)

    def list_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None) -> List[WeightLog]:
        query = self.db.query(WeightLog).filter(WeightLog.user_id == user_id)
        if log_date is not None:
            query = query.filter(WeightLog.log_date == log_date)
        return query.order_by(WeightLog.log_date.desc(), WeightLog.id.desc()).offset(skip).limit(limit).all()
