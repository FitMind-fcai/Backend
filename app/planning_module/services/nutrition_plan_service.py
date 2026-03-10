from sqlalchemy.orm import Session
from typing import List, Optional
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.shared.repositories.central_meal_repository import CentralMealRepository
from app.planning_module.models import NutritionPlan, NutritionPlanDay, NutritionPlanMeal


class NutritionPlanService:
    """Service layer for nutrition plan business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = NutritionPlanRepository(db)
        self.central_meal_repo = CentralMealRepository(db)

    def get_user_plans(self, user_id: int, skip: int = 0, limit: int = 10) -> List[NutritionPlan]:
        return self.repo.get_by_user_id(user_id, skip, limit)

    def get_active_plan(self, user_id: int) -> Optional[NutritionPlan]:
        return self.repo.get_active_plan(user_id)

    def get_plan_by_id(self, plan_id: int) -> Optional[NutritionPlan]:
        return self.repo.get_by_id(plan_id)

    def get_plan_with_full_details(self, plan_id: int) -> Optional[NutritionPlan]:
        return self.repo.get_with_full_details(plan_id)

    def delete_plan(self, plan_id: int) -> bool:
        return self.repo.delete_plan(plan_id)

    def get_days(self, plan_id: int) -> List[NutritionPlanDay]:
        return self.repo.get_days_by_plan_id(plan_id)

    def get_meals_for_day(self, day_id: int, meal_type: Optional[str] = None) -> List[NutritionPlanMeal]:
        if meal_type:
            return self.repo.get_meals_by_type(day_id, meal_type)
        return self.repo.get_meals_by_day_id(day_id)

    def get_meal_by_id(self, meal_id: int) -> Optional[NutritionPlanMeal]:
        return self.repo.get_meal_by_id(meal_id)

    def verify_plan_ownership(self, plan_id: int, user_id: int) -> bool:
        plan = self.repo.get_by_id(plan_id)
        return plan is not None and plan.user_id == user_id

    def verify_meal_belongs_to_plan(self, meal_id: int, plan_id: int) -> bool:
        meal = self.repo.get_meal_by_id(meal_id)
        if meal is None:
            return False
        day = self.repo.get_day_by_id(meal.nutrition_plan_day_id)
        return day is not None and day.nutrition_plan_id == plan_id