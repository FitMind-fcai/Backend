from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional
from datetime import date
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import WorkoutPlan, WorkoutDay, Exercise


class WorkoutPlanRepository(BaseRepository[WorkoutPlan]):
    """Repository for workout plan operations"""
    
    def __init__(self, db: Session):
        super().__init__(WorkoutPlan, db)
    
    def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 10) -> List[WorkoutPlan]:
        """Get all workout plans for a user"""
        return (
            self.db.query(WorkoutPlan)
            .filter(WorkoutPlan.user_id == user_id)
            .order_by(desc(WorkoutPlan.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_active_plan(self, user_id: int) -> Optional[WorkoutPlan]:
        """Get user's active workout plan (current date within plan dates)"""
        today = date.today()
        return (
            self.db.query(WorkoutPlan)
            .filter(
                WorkoutPlan.user_id == user_id,
                WorkoutPlan.start_date <= today,
                (WorkoutPlan.end_date >= today) | (WorkoutPlan.end_date.is_(None))
            )
            .order_by(desc(WorkoutPlan.start_date))
            .first()
        )
    
    def get_with_days(self, plan_id: int) -> Optional[WorkoutPlan]:
        """Get workout plan with all workout days loaded"""
        return (
            self.db.query(WorkoutPlan)
            .options(joinedload(WorkoutPlan.workout_days))
            .filter(WorkoutPlan.id == plan_id)
            .first()
        )
    
    def get_with_full_details(self, plan_id: int) -> Optional[WorkoutPlan]:
        """Get workout plan with all nested data (days and exercises)"""
        return (
            self.db.query(WorkoutPlan)
            .options(
                joinedload(WorkoutPlan.workout_days).joinedload(WorkoutDay.exercises)
            )
            .filter(WorkoutPlan.id == plan_id)
            .first()
        )
    
    def create_plan(self, user_id: int, profile_id: int, plan_data: dict) -> WorkoutPlan:
        """Create a new workout plan"""
        plan = WorkoutPlan(
            user_id=user_id,
            profile_id=profile_id,
            **plan_data
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan
    
    def update_plan(self, plan_id: int, plan_data: dict) -> Optional[WorkoutPlan]:
        """Update workout plan"""
        plan = self.get_by_id(plan_id)
        if plan:
            for key, value in plan_data.items():
                setattr(plan, key, value)
            self.db.commit()
            self.db.refresh(plan)
        return plan
    
    def delete_plan(self, plan_id: int) -> bool:
        """Delete workout plan (cascade deletes days and exercises)"""
        plan = self.get_by_id(plan_id)
        if plan:
            self.db.delete(plan)
            self.db.commit()
            return True
        return False


class WorkoutDayRepository(BaseRepository[WorkoutDay]):
    """Repository for workout day operations"""
    
    def __init__(self, db: Session):
        super().__init__(WorkoutDay, db)
    
    def get_by_plan_id(self, plan_id: int) -> List[WorkoutDay]:
        """Get all workout days for a plan"""
        return (
            self.db.query(WorkoutDay)
            .filter(WorkoutDay.workout_plan_id == plan_id)
            .order_by(WorkoutDay.day_number)
            .all()
        )
    
    def get_with_exercises(self, day_id: int) -> Optional[WorkoutDay]:
        """Get workout day with all exercises loaded"""
        return (
            self.db.query(WorkoutDay)
            .options(joinedload(WorkoutDay.exercises))
            .filter(WorkoutDay.id == day_id)
            .first()
        )
    
    def create_workout_day(self, plan_id: int, day_data: dict) -> WorkoutDay:
        """Create a new workout day"""
        day = WorkoutDay(workout_plan_id=plan_id, **day_data)
        self.db.add(day)
        self.db.commit()
        self.db.refresh(day)
        return day
    
    def update_workout_day(self, day_id: int, day_data: dict) -> Optional[WorkoutDay]:
        """Update workout day"""
        day = self.get_by_id(day_id)
        if day:
            for key, value in day_data.items():
                setattr(day, key, value)
            self.db.commit()
            self.db.refresh(day)
        return day
    
    def delete_workout_day(self, day_id: int) -> bool:
        """Delete workout day (cascade deletes exercises)"""
        day = self.get_by_id(day_id)
        if day:
            self.db.delete(day)
            self.db.commit()
            return True
        return False


class ExerciseRepository(BaseRepository[Exercise]):
    """Repository for exercise operations"""
    
    def __init__(self, db: Session):
        super().__init__(Exercise, db)
    
    def get_by_workout_day_id(self, day_id: int) -> List[Exercise]:
        """Get all exercises for a workout day"""
        return (
            self.db.query(Exercise)
            .filter(Exercise.workout_day_id == day_id)
            .order_by(Exercise.order_index)
            .all()
        )
    
    def create_exercise(self, day_id: int, exercise_data: dict) -> Exercise:
        """Create a new exercise"""
        exercise = Exercise(workout_day_id=day_id, **exercise_data)
        self.db.add(exercise)
        self.db.commit()
        self.db.refresh(exercise)
        return exercise
    
    def update_exercise(self, exercise_id: int, exercise_data: dict) -> Optional[Exercise]:
        """Update exercise"""
        exercise = self.get_by_id(exercise_id)
        if exercise:
            for key, value in exercise_data.items():
                setattr(exercise, key, value)
            self.db.commit()
            self.db.refresh(exercise)
        return exercise
    
    def delete_exercise(self, exercise_id: int) -> bool:
        """Delete exercise"""
        exercise = self.get_by_id(exercise_id)
        if exercise:
            self.db.delete(exercise)
            self.db.commit()
            return True
        return False
