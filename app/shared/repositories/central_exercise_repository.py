from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import List, Optional
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralExercise


class CentralExerciseRepository(BaseRepository[CentralExercise]):
    """Repository for the central exercise catalog (shared across all modules)"""

    def __init__(self, db: Session):
        super().__init__(CentralExercise, db)

    def get_by_name(self, name: str) -> Optional[CentralExercise]:
        """Get exercise by name (case-insensitive)"""
        return (
            self.db.query(CentralExercise)
            .filter(sql_func.lower(CentralExercise.name) == name.lower())
            .filter(CentralExercise.is_active == True)
            .first()
        )

    def get_by_filters(
        self,
        muscle_group: Optional[str] = None,
        equipment: Optional[str] = None,
        difficulty: Optional[str] = None,
        location: Optional[str] = None,
        exercise_type: Optional[str] = None,
        limit: int = 30
    ) -> List[CentralExercise]:
        """Get exercises filtered by attributes — used to build AI context"""
        query = self.db.query(CentralExercise).filter(CentralExercise.is_active == True)
        if muscle_group:
            query = query.filter(CentralExercise.primary_muscle_group.ilike(f"%{muscle_group}%"))
        if equipment:
            query = query.filter(CentralExercise.equipment_required.ilike(f"%{equipment}%"))
        if difficulty:
            query = query.filter(CentralExercise.difficulty_level.ilike(f"%{difficulty}%"))
        if location and location.lower() != "any":
            query = query.filter(
                (CentralExercise.location.ilike(f"%{location}%")) |
                (CentralExercise.location == "Any")
            )
        if exercise_type:
            query = query.filter(CentralExercise.exercise_type.ilike(f"%{exercise_type}%"))
        return query.limit(limit).all()

    def find_or_create(self, exercise_data: dict) -> CentralExercise:
        """Find exercise by name or create a new catalog entry if not found"""
        existing = self.get_by_name(exercise_data["name"])
        if existing:
            return existing
        exercise = CentralExercise(**exercise_data)
        self.db.add(exercise)
        self.db.commit()
        self.db.refresh(exercise)
        return exercise
