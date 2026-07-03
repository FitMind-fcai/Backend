from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import desc
from typing import List, Optional
from datetime import date
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import (
    WorkoutPlan, WorkoutDay, WorkoutDayExercise
)


class WorkoutPlanRepository(BaseRepository[WorkoutPlan]):
    """Single repository for all workout plan operations (plan, days, exercise slots)"""

    def __init__(self, db: Session):
        super().__init__(WorkoutPlan, db)

    # ------------------------------------------------------------------
    # Plan queries
    # ------------------------------------------------------------------

    def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 10) -> List[WorkoutPlan]:
        return (
            self.db.query(WorkoutPlan)
            .filter(WorkoutPlan.user_id == user_id)
            .order_by(desc(WorkoutPlan.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_plan(self, user_id: int) -> Optional[WorkoutPlan]:
        today = date.today()
        return (
            self.db.query(WorkoutPlan)
            .filter(
                WorkoutPlan.user_id == user_id,
                WorkoutPlan.start_date <= today,
                (WorkoutPlan.end_date >= today) | (WorkoutPlan.end_date.is_(None))
            )
            .order_by(desc(WorkoutPlan.created_at))
            .first()
        )

    def get_with_full_details(self, plan_id: int) -> Optional[WorkoutPlan]:
        """Eagerly load plan -> days -> exercise slots -> central exercise"""
        return (
            self.db.query(WorkoutPlan)
            .options(
                selectinload(WorkoutPlan.workout_days)
                .selectinload(WorkoutDay.exercises)
                .joinedload(WorkoutDayExercise.central_exercise)
            )
            .filter(WorkoutPlan.id == plan_id)
            .first()
        )

    def create_plan(self, user_id: int, profile_id: int, plan_data: dict) -> WorkoutPlan:
        plan = WorkoutPlan(user_id=user_id, profile_id=profile_id, **plan_data)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def update_plan(self, plan_id: int, plan_data: dict) -> Optional[WorkoutPlan]:
        plan = self.get_by_id(plan_id)
        if plan:
            for key, value in plan_data.items():
                setattr(plan, key, value)
            self.db.commit()
            self.db.refresh(plan)
        return plan

    def delete_plan(self, plan_id: int) -> bool:
        plan = self.get_by_id(plan_id)
        if plan:
            self.db.delete(plan)
            self.db.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Day queries
    # ------------------------------------------------------------------

    def get_days_by_plan_id(self, plan_id: int) -> List[WorkoutDay]:
        return (
            self.db.query(WorkoutDay)
            .filter(WorkoutDay.workout_plan_id == plan_id)
            .order_by(WorkoutDay.day_number)
            .all()
        )

    def get_day_by_id(self, day_id: int) -> Optional[WorkoutDay]:
        return self.db.query(WorkoutDay).filter(WorkoutDay.id == day_id).first()

    def get_day_with_exercises(self, day_id: int) -> Optional[WorkoutDay]:
        return (
            self.db.query(WorkoutDay)
            .options(
                selectinload(WorkoutDay.exercises)
                .joinedload(WorkoutDayExercise.central_exercise)
            )
            .filter(WorkoutDay.id == day_id)
            .first()
        )

    def create_day(self, plan_id: int, day_data: dict, commit: bool = True) -> WorkoutDay:
        day = WorkoutDay(workout_plan_id=plan_id, **day_data)
        self.db.add(day)
        if commit:
            self.db.commit()
            self.db.refresh(day)
        else:
            # Flush only — assigns day.id without a round-trip commit, so
            # callers can batch many days/exercises into one final commit.
            self.db.flush()
        return day

    # ------------------------------------------------------------------
    # Exercise slot queries
    # ------------------------------------------------------------------

    def get_exercises_by_day_id(self, day_id: int) -> List[WorkoutDayExercise]:
        return (
            self.db.query(WorkoutDayExercise)
            .options(joinedload(WorkoutDayExercise.central_exercise))
            .filter(WorkoutDayExercise.workout_day_id == day_id)
            .order_by(WorkoutDayExercise.order_index)
            .all()
        )

    def create_exercise_slot(
        self, day_id: int, central_exercise_id: int, slot_data: dict, commit: bool = True
    ) -> WorkoutDayExercise:
        slot = WorkoutDayExercise(
            workout_day_id=day_id,
            central_exercise_id=central_exercise_id,
            **slot_data
        )
        self.db.add(slot)
        if commit:
            self.db.commit()
            self.db.refresh(slot)
        else:
            self.db.flush()
        return slot

    def delete_exercise_slots_by_day_id(self, day_id: int):
        self.db.query(WorkoutDayExercise).filter(
            WorkoutDayExercise.workout_day_id == day_id
        ).delete()
        self.db.commit()


