from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.shared.repositories.base_repository import BaseRepository
from app.tracking_module.models.sleep_log import SleepLog


class SleepLogRepository(BaseRepository[SleepLog]):
    def __init__(self, db: Session):
        super().__init__(SleepLog, db)

    def create_log(self, user_id: int, log_date: date, sleep_hours: float,
                   sleep_quality: int, notes: Optional[str] = None) -> SleepLog:
        return self.create({
            "user_id": user_id,
            "log_date": log_date,
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "notes": notes,
        })

    def list_logs(self, user_id: int, skip: int = 0, limit: int = 50,
                  log_date: Optional[date] = None) -> List[SleepLog]:
        query = self.db.query(SleepLog).filter(SleepLog.user_id == user_id)
        if log_date is not None:
            query = query.filter(SleepLog.log_date == log_date)
        return query.order_by(SleepLog.log_date.desc(), SleepLog.id.desc()).offset(skip).limit(limit).all()

    def list_logs_since(self, user_id: int, since: date, until: Optional[date] = None) -> List[SleepLog]:
        query = self.db.query(SleepLog).filter(
            SleepLog.user_id == user_id,
            SleepLog.log_date >= since,
        )
        if until is not None:
            query = query.filter(SleepLog.log_date <= until)
        return query.order_by(SleepLog.log_date.asc()).all()
