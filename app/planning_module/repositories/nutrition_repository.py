from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional
from datetime import date
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import NutritionPlan, Meal


class NutritionPlanRepository(BaseRepository[NutritionPlan]):
    """Repository for nutrition plan operations"""
    
    def __init__(self, db: Session):
        super().__init__(NutritionPlan, db)
    
    def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 10) -> List[NutritionPlan]:
        """Get all nutrition plans for a user"""
        return (
            self.db.query(NutritionPlan)
            .filter(NutritionPlan.user_id == user_id)
            .order_by(desc(NutritionPlan.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_active_plan(self, user_id: int) -> Optional[NutritionPlan]:
        """Get user's active nutrition plan (current date within plan dates)"""
        today = date.today()
        return (
            self.db.query(NutritionPlan)
            .filter(
                NutritionPlan.user_id == user_id,
                NutritionPlan.start_date <= today,
                (NutritionPlan.end_date >= today) | (NutritionPlan.end_date.is_(None))
            )
            .order_by(desc(NutritionPlan.start_date))
            .first()
        )
    
    def get_with_meals(self, plan_id: int) -> Optional[NutritionPlan]:
        """Get nutrition plan with all meals loaded"""
        return (
            self.db.query(NutritionPlan)
            .options(joinedload(NutritionPlan.meals))
            .filter(NutritionPlan.id == plan_id)
            .first()
        )
    
    def create_plan(self, user_id: int, profile_id: int, plan_data: dict) -> NutritionPlan:
        """Create a new nutrition plan"""
        plan = NutritionPlan(
            user_id=user_id,
            profile_id=profile_id,
            **plan_data
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan
    
    def update_plan(self, plan_id: int, plan_data: dict) -> Optional[NutritionPlan]:
        """Update nutrition plan"""
        plan = self.get_by_id(plan_id)
        if plan:
            for key, value in plan_data.items():
                setattr(plan, key, value)
            self.db.commit()
            self.db.refresh(plan)
        return plan
    
    def delete_plan(self, plan_id: int) -> bool:
        """Delete nutrition plan (cascade deletes meals)"""
        plan = self.get_by_id(plan_id)
        if plan:
            self.db.delete(plan)
            self.db.commit()
            return True
        return False


class MealRepository(BaseRepository[Meal]):
    """Repository for meal operations"""
    
    def __init__(self, db: Session):
        super().__init__(Meal, db)
    
    def get_by_plan_id(self, plan_id: int) -> List[Meal]:
        """Get all meals for a nutrition plan"""
        return (
            self.db.query(Meal)
            .filter(Meal.nutrition_plan_id == plan_id)
            .order_by(Meal.order_index)
            .all()
        )
    
    def get_by_meal_type(self, plan_id: int, meal_type: str) -> List[Meal]:
        """Get meals by type (Breakfast, Lunch, etc.)"""
        return (
            self.db.query(Meal)
            .filter(
                Meal.nutrition_plan_id == plan_id,
                Meal.meal_type == meal_type
            )
            .order_by(Meal.order_index)
            .all()
        )
    
    def create_meal(self, plan_id: int, meal_data: dict) -> Meal:
        """Create a new meal"""
        meal = Meal(nutrition_plan_id=plan_id, **meal_data)
        self.db.add(meal)
        self.db.commit()
        self.db.refresh(meal)
        return meal
    
    def update_meal(self, meal_id: int, meal_data: dict) -> Optional[Meal]:
        """Update meal"""
        meal = self.get_by_id(meal_id)
        if meal:
            for key, value in meal_data.items():
                setattr(meal, key, value)
            self.db.commit()
            self.db.refresh(meal)
        return meal
    
    def delete_meal(self, meal_id: int) -> bool:
        """Delete meal"""
        meal = self.get_by_id(meal_id)
        if meal:
            self.db.delete(meal)
            self.db.commit()
            return True
        return False
