from sqlalchemy.orm import Session
from typing import List, Optional
from app.planning_module.repositories.nutrition_repository import (
    NutritionPlanRepository,
    MealRepository
)
from app.planning_module.models import NutritionPlan, Meal


class NutritionPlanService:
    """Service layer for nutrition plan business logic"""
    
    def __init__(self, db: Session):
        self.db = db
        self.nutrition_plan_repo = NutritionPlanRepository(db)
        self.meal_repo = MealRepository(db)
    
    def get_user_plans(self, user_id: int, skip: int = 0, limit: int = 10) -> List[NutritionPlan]:
        """Get all nutrition plans for a user"""
        return self.nutrition_plan_repo.get_by_user_id(user_id, skip, limit)
    
    def get_active_plan(self, user_id: int) -> Optional[NutritionPlan]:
        """Get user's currently active nutrition plan"""
        return self.nutrition_plan_repo.get_active_plan(user_id)
    
    def get_plan_by_id(self, plan_id: int) -> Optional[NutritionPlan]:
        """Get a specific nutrition plan"""
        return self.nutrition_plan_repo.get_by_id(plan_id)
    
    def get_plan_with_meals(self, plan_id: int) -> Optional[NutritionPlan]:
        """Get nutrition plan with all meals"""
        return self.nutrition_plan_repo.get_with_meals(plan_id)
    
    def delete_plan(self, plan_id: int) -> bool:
        """Delete a nutrition plan"""
        return self.nutrition_plan_repo.delete_plan(plan_id)
    
    def get_meals(self, plan_id: int, meal_type: Optional[str] = None) -> List[Meal]:
        """Get all meals for a plan, optionally filtered by meal type"""
        if meal_type:
            return self.meal_repo.get_by_meal_type(plan_id, meal_type)
        return self.meal_repo.get_by_plan_id(plan_id)
    
    def get_meal_by_id(self, meal_id: int) -> Optional[Meal]:
        """Get a specific meal"""
        return self.meal_repo.get_by_id(meal_id)
    
    def verify_plan_ownership(self, plan_id: int, user_id: int) -> bool:
        """Verify that a plan belongs to the specified user"""
        plan = self.nutrition_plan_repo.get_by_id(plan_id)
        return plan is not None and plan.user_id == user_id
    
    def verify_meal_belongs_to_plan(self, meal_id: int, plan_id: int) -> bool:
        """Verify that a meal belongs to the specified plan"""
        meal = self.meal_repo.get_by_id(meal_id)
        return meal is not None and meal.nutrition_plan_id == plan_id
    
    # TODO: AI Generation methods will be added here
    # def generate_nutrition_plan(self, user_id: int, profile_id: int, preferences: dict) -> NutritionPlan:
    #     """Generate a new nutrition plan using AI Coach service"""
    #     pass
