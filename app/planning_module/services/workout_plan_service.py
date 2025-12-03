from sqlalchemy.orm import Session
from typing import List, Optional
from app.planning_module.repositories.workout_repository import (
    WorkoutPlanRepository,
    WorkoutDayRepository,
    ExerciseRepository
)
from app.planning_module.models import WorkoutPlan, WorkoutDay, Exercise


class WorkoutPlanService:
    """Service layer for workout plan business logic"""
    
    def __init__(self, db: Session):
        self.db = db
        self.workout_plan_repo = WorkoutPlanRepository(db)
        self.workout_day_repo = WorkoutDayRepository(db)
        self.exercise_repo = ExerciseRepository(db)
    
    def get_user_plans(self, user_id: int, skip: int = 0, limit: int = 10) -> List[WorkoutPlan]:
        """Get all workout plans for a user"""
        return self.workout_plan_repo.get_by_user_id(user_id, skip, limit)
    
    def get_active_plan(self, user_id: int) -> Optional[WorkoutPlan]:
        """Get user's currently active workout plan"""
        return self.workout_plan_repo.get_active_plan(user_id)
    
    def get_plan_by_id(self, plan_id: int) -> Optional[WorkoutPlan]:
        """Get a specific workout plan"""
        return self.workout_plan_repo.get_by_id(plan_id)
    
    def get_plan_with_details(self, plan_id: int) -> Optional[WorkoutPlan]:
        """Get workout plan with all nested data (days and exercises)"""
        return self.workout_plan_repo.get_with_full_details(plan_id)
    
    def delete_plan(self, plan_id: int) -> bool:
        """Delete a workout plan"""
        return self.workout_plan_repo.delete_plan(plan_id)
    
    def get_workout_days(self, plan_id: int) -> List[WorkoutDay]:
        """Get all workout days for a plan"""
        return self.workout_day_repo.get_by_plan_id(plan_id)
    
    def get_workout_day_with_exercises(self, day_id: int) -> Optional[WorkoutDay]:
        """Get a workout day with all its exercises"""
        return self.workout_day_repo.get_with_exercises(day_id)
    
    def get_exercises(self, day_id: int) -> List[Exercise]:
        """Get all exercises for a workout day"""
        return self.exercise_repo.get_by_workout_day_id(day_id)
    
    def verify_plan_ownership(self, plan_id: int, user_id: int) -> bool:
        """Verify that a plan belongs to the specified user"""
        plan = self.workout_plan_repo.get_by_id(plan_id)
        return plan is not None and plan.user_id == user_id
    
    def verify_day_belongs_to_plan(self, day_id: int, plan_id: int) -> bool:
        """Verify that a workout day belongs to the specified plan"""
        day = self.workout_day_repo.get_by_id(day_id)
        return day is not None and day.workout_plan_id == plan_id
    
