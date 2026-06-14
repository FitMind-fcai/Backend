from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.shared.repositories.base_repository import BaseRepository
from app.tracking_module.models.hydration_log import HydrationLog


class HydrationLogRepository(BaseRepository[HydrationLog]):
    def __init__(self, db: Session):
        super().__init__(HydrationLog, db)

    def create_log(self, user_id: int, log_date: date, water_ml: float,
                   notes: Optional[str] = None) -> HydrationLog:
        return self.create({
            "user_id": user_id,
            "log_date": log_date,
            "water_ml": water_ml,
            "notes": notes,
        })

    def list_logs(self, user_id: int, skip: int = 0, limit: int = 50,
                  log_date: Optional[date] = None) -> List[HydrationLog]:
        query = self.db.query(HydrationLog).filter(HydrationLog.user_id == user_id)
        if log_date is not None:
            query = query.filter(HydrationLog.log_date == log_date)
        return query.order_by(HydrationLog.log_date.desc(), HydrationLog.id.desc()).offset(skip).limit(limit).all()

    def list_logs_since(self, user_id: int, since: date, until: Optional[date] = None) -> List[HydrationLog]:
        query = self.db.query(HydrationLog).filter(
            HydrationLog.user_id == user_id,
            HydrationLog.log_date >= since,
        )
        if until is not None:
            query = query.filter(HydrationLog.log_date <= until)
        return query.order_by(HydrationLog.log_date.asc()).all()
