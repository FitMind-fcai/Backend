from sqlalchemy.orm import Session
from typing import List, Optional
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository
from app.planning_module.models import WorkoutPlan, WorkoutDay, WorkoutDayExercise


class WorkoutPlanService:
    """Service layer for workout plan business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = WorkoutPlanRepository(db)
        self.central_exercise_repo = CentralExerciseRepository(db)

    def get_user_plans(self, user_id: int, skip: int = 0, limit: int = 10) -> List[WorkoutPlan]:
        return self.repo.get_by_user_id(user_id, skip, limit)

    def get_active_plan(self, user_id: int) -> Optional[WorkoutPlan]:
        return self.repo.get_active_plan(user_id)

    def get_plan_by_id(self, plan_id: int) -> Optional[WorkoutPlan]:
        return self.repo.get_by_id(plan_id)

    def get_plan_with_details(self, plan_id: int) -> Optional[WorkoutPlan]:
        return self.repo.get_with_full_details(plan_id)

    def delete_plan(self, plan_id: int) -> bool:
        return self.repo.delete_plan(plan_id)

    def get_workout_days(self, plan_id: int) -> List[WorkoutDay]:
        return self.repo.get_days_by_plan_id(plan_id)

    def get_workout_day_with_exercises(self, day_id: int) -> Optional[WorkoutDay]:
        return self.repo.get_day_with_exercises(day_id)

    def get_exercises(self, day_id: int) -> List[WorkoutDayExercise]:
        return self.repo.get_exercises_by_day_id(day_id)

    def verify_plan_ownership(self, plan_id: int, user_id: int) -> bool:
        plan = self.repo.get_by_id(plan_id)
        return plan is not None and plan.user_id == user_id

    def verify_day_belongs_to_plan(self, day_id: int, plan_id: int) -> bool:
        day = self.repo.get_day_by_id(day_id)
        return day is not None and day.workout_plan_id == plan_id
