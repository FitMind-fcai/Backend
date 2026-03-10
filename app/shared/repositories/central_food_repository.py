from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import List, Optional
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralFood


class CentralFoodRepository(BaseRepository[CentralFood]):
    """Repository for the central food catalog (USDA foods + manual entries)"""

    def __init__(self, db: Session):
        super().__init__(CentralFood, db)

    def get_by_name(self, name: str) -> Optional[CentralFood]:
        """Exact name lookup (case-insensitive)"""
        return (
            self.db.query(CentralFood)
            .filter(sql_func.lower(CentralFood.food_name) == name.lower())
            .filter(CentralFood.is_active == True)
            .first()
        )

    def get_by_usda_id(self, fdc_id: int) -> Optional[CentralFood]:
        """Lookup by USDA FDC ID"""
        return (
            self.db.query(CentralFood)
            .filter(CentralFood.usda_fdc_id == fdc_id)
            .first()
        )

    def search(
        self,
        query: str,
        food_category: Optional[str] = None,
        limit: int = 30
    ) -> List[CentralFood]:
        """Full-text search by food name — used for food logging search (MyFitnessPal-style)"""
        q = (
            self.db.query(CentralFood)
            .filter(CentralFood.is_active == True)
            .filter(CentralFood.food_name.ilike(f"%{query}%"))
        )
        if food_category:
            q = q.filter(CentralFood.food_category.ilike(f"%{food_category}%"))
        return q.order_by(CentralFood.food_name).limit(limit).all()

    def get_by_filters(
        self,
        food_category: Optional[str] = None,
        max_calories_per_100g: Optional[float] = None,
        min_protein_per_100g: Optional[float] = None,
        limit: int = 30
    ) -> List[CentralFood]:
        """Filtered fetch — used to provide AI with food context during plan generation"""
        q = self.db.query(CentralFood).filter(CentralFood.is_active == True)
        if food_category:
            q = q.filter(CentralFood.food_category.ilike(f"%{food_category}%"))
        if max_calories_per_100g:
            q = q.filter(CentralFood.calories_per_100g <= max_calories_per_100g)
        if min_protein_per_100g:
            q = q.filter(CentralFood.protein_per_100g >= min_protein_per_100g)
        return q.limit(limit).all()

    def find_or_create(self, food_data: dict) -> CentralFood:
        """Find by USDA FDC ID first, then by name, or create if not found"""
        if food_data.get("usda_fdc_id"):
            existing = self.get_by_usda_id(food_data["usda_fdc_id"])
            if existing:
                return existing
        existing = self.get_by_name(food_data["food_name"])
        if existing:
            return existing
        food = CentralFood(**food_data)
        self.db.add(food)
        self.db.commit()
        self.db.refresh(food)
        return food
