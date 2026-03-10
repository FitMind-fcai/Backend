from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import List, Optional
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralMeal


class CentralMealRepository(BaseRepository[CentralMeal]):
    """Repository for the central meal catalog (shared across all modules)"""

    def __init__(self, db: Session):
        super().__init__(CentralMeal, db)

    def get_by_name(self, name: str) -> Optional[CentralMeal]:
        """Get meal by name (case-insensitive)"""
        return (
            self.db.query(CentralMeal)
            .filter(sql_func.lower(CentralMeal.meal_name) == name.lower())
            .filter(CentralMeal.is_active == True)
            .first()
        )

    def get_by_filters(
        self,
        cuisine_type: Optional[str] = None,
        max_calories: Optional[int] = None,
        min_protein: Optional[float] = None,
        limit: int = 30
    ) -> List[CentralMeal]:
        """Get meals filtered by attributes — used to build AI context"""
        query = self.db.query(CentralMeal).filter(CentralMeal.is_active == True)
        if cuisine_type and cuisine_type.lower() not in ("any", "mixed", ""):
            query = query.filter(CentralMeal.cuisine_type.ilike(f"%{cuisine_type}%"))
        if max_calories:
            query = query.filter(CentralMeal.calories_per_serving <= max_calories)
        if min_protein:
            query = query.filter(CentralMeal.protein_g >= min_protein)
        return query.limit(limit).all()

    def find_or_create(self, meal_data: dict) -> CentralMeal:
        """Find meal by name or create a new catalog entry if not found"""
        existing = self.get_by_name(meal_data["meal_name"])
        if existing:
            return existing
        meal = CentralMeal(**meal_data)
        self.db.add(meal)
        self.db.commit()
        self.db.refresh(meal)
        return meal
