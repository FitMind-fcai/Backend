from typing import List, Optional
from datetime import date

from sqlalchemy.orm import Session

from app.shared.repositories.base_repository import BaseRepository
from app.tracking_module.models.meal_log import MealLog


class MealLogRepository(BaseRepository[MealLog]):
    def __init__(self, db: Session):
        super().__init__(MealLog, db)

    def create_log(
        self,
        user_id: int,
        log_date: date,
        meal_type: str,
        meal_name: str,
        servings: float,
        calories: float,
        protein_g: float,
        carbs_g: float,
        fats_g: float,
        log_method: str,
        serving_size_g_snapshot: Optional[float] = None,
        serving_description_snapshot: Optional[str] = None,
        central_food_id: Optional[int] = None,
        image_url: Optional[str] = None,
    ) -> MealLog:
        payload = {
            "user_id": user_id,
            "central_food_id": central_food_id,
            "log_date": log_date,
            "meal_type": meal_type,
            "meal_name": meal_name,
            "servings": servings,
            "serving_size_g_snapshot": serving_size_g_snapshot,
            "serving_description_snapshot": serving_description_snapshot,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fats_g": fats_g,
            "log_method": log_method,
            "image_url": image_url,
        }
        return self.create(payload)

    def list_logs(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
    ) -> List[MealLog]:
        query = self.db.query(MealLog).filter(MealLog.user_id == user_id)
        if log_date is not None:
            query = query.filter(MealLog.log_date == log_date)
        if meal_type is not None:
            query = query.filter(MealLog.meal_type == meal_type)
        return query.order_by(MealLog.log_date.desc(), MealLog.id.desc()).offset(skip).limit(limit).all()

    def list_logs_since(self, user_id: int, since: date, until: Optional[date] = None) -> List[MealLog]:
        query = self.db.query(MealLog).filter(
            MealLog.user_id == user_id,
            MealLog.log_date >= since,
        )
        if until is not None:
            query = query.filter(MealLog.log_date <= until)
        return query.order_by(MealLog.log_date.asc(), MealLog.id.asc()).all()
