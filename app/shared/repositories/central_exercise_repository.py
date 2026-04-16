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

    def get_equipment_friendly_exercises_for_ai(
        self,
        equipment_availability: str = "Full Gym Equipment",
        workout_difficulty: str = "Beginner",
        limit: int = 50
    ) -> str:
        """
        Fetch a list of exercises matching equipment availability and difficulty.
        Returns formatted text constraint for the LLM.
        """
        query = self.db.query(CentralExercise).filter(CentralExercise.is_active == True)
        
        # 1. Equipment Constraints
        equipment_availability = str(equipment_availability).lower()
        if equipment_availability == "no equipment":
            # Only allow bodyweight / no equipment
            query = query.filter(
                (CentralExercise.equipment_required.ilike('%body%')) | 
                (CentralExercise.equipment_required.ilike('%none%'))
            )
        elif equipment_availability == "basic equipment":
            # Allow basic equipment
            basic_equip = ['body', 'none', 'dumbbell', 'band', 'kettlebell', 'medicine ball', 'foam roll']
            conditions = [CentralExercise.equipment_required.ilike(f'%{e}%') for e in basic_equip]
            from sqlalchemy import or_
            query = query.filter(or_(*conditions))
        
        # 2. Difficulty Constraints
        # Advanced users can do beginner exercises, but beginners shouldn't do expert ones (usually).
        workout_difficulty = str(workout_difficulty).lower()
        if workout_difficulty == "beginner":
            query = query.filter(CentralExercise.difficulty_level.ilike('%beginner%'))
        elif workout_difficulty == "intermediate":
            query = query.filter(
                (CentralExercise.difficulty_level.ilike('%beginner%')) |
                (CentralExercise.difficulty_level.ilike('%intermediate%'))
            )
        
        # Get a diverse randomized selection of matching exercises
        exercises = query.order_by(sql_func.random()).limit(limit).all()
        
        if not exercises:
            return "Note: No strict exercise constraints applied due to restrictive filters. Generate generic functional workouts."

        prompt_str = f"=== MANDATORY EXERCISE DATABASE ({len(exercises)} ITEMS) ===\\n"
        prompt_str += "You MUST ONLY generate workouts using the exact exercises and IDs from this list below. Do not invent new exercises.\\n"
        prompt_str += "Select exercises creatively to form balanced workouts based on the user's focus.\\n\\n"
        
        for e in exercises:
            prompt_str += (
                f"- [ID: {e.id}] {e.name} "
                f"(Muscle: {e.primary_muscle_group} | Equipment: {e.equipment_required} | Type: {e.exercise_type} | Level: {e.difficulty_level})\\n"
            )
        
        return prompt_str

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
