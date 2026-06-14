from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, text
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

    def search_for_tracking(self, query: str, user_id: int, limit: int = 20) -> List[CentralExercise]:
        """Search exercises visible to user: verified/public + user's private entries."""
        q = (
            self.db.query(CentralExercise)
            .filter(CentralExercise.is_active == True)
            .filter(CentralExercise.name.ilike(f"%{query}%"))
            .filter(
                (CentralExercise.is_verified == True)
                | (CentralExercise.is_public == True)
                | (CentralExercise.created_by_user_id == user_id)
            )
        )
        return q.order_by(CentralExercise.name.asc()).limit(limit).all()

    def create_manual_exercise(self, user_id: int, exercise_data: dict) -> CentralExercise:
        """Create a user-scoped manual exercise in central_exercises with governance flags."""
        payload = dict(exercise_data)
        payload.update(
            {
                "created_by_user_id": user_id,
                "is_verified": False,
                "is_public": False,
                "source": "ManualUser",
                "is_active": True,
            }
        )
        return self.create(payload)

    def get_equipment_friendly_exercises_for_ai(
        self,
        equipment_availability: str = "Full Gym Equipment",
        workout_difficulty: str = "Beginner",
        focus_areas: Optional[List[str]] = None,
        limit: int = 25
    ) -> str:
        """
        Fetch a structured constraint JSON of exercises matching preferences.
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
        workout_difficulty = str(workout_difficulty).lower()
        if workout_difficulty == "beginner":
            query = query.filter(CentralExercise.difficulty_level.ilike('%beginner%'))
        elif workout_difficulty == "intermediate":
            query = query.filter(
                (CentralExercise.difficulty_level.ilike('%beginner%')) |
                (CentralExercise.difficulty_level.ilike('%intermediate%'))
            )
        
        exercises = query.all()
        
        if not exercises:
            return '{"error": "No exercises match the restrictive filters", "instruction": "Generate functional bodyweight variations as fallback."}'

        top_exercises = self._select_balanced_exercises_for_prompt(exercises, limit, focus_areas)

        import json
        catalog = []
        for e in top_exercises:
            catalog.append({
                "id": e.id,
                "name": e.name,
                "muscle": e.primary_muscle_group,
                "equipment": e.equipment_required,
                "type": e.exercise_type,
                "level": e.difficulty_level
            })
            
        constraints_block = {
            "MANDATORY_EXERCISE_CATALOG": catalog,
            "INSTRUCTION": "You MUST ONLY generate workouts using the exact exercises and IDs from this catalog. Do not invent new exercises."
        }
        return json.dumps(constraints_block, indent=2)

    def _select_balanced_exercises_for_prompt(
        self,
        exercises: List[CentralExercise],
        limit: int,
        focus_areas: Optional[List[str]]
    ) -> List[CentralExercise]:
        """Build a deterministic, balanced exercise set for AI prompts, preventing starvation of specific muscle groups."""
        if not exercises:
            return []

        limit = max(12, int(limit or 25))
        
        buckets = {}
        for exercise in exercises:
            mg = str(exercise.primary_muscle_group or "Full Body").lower()
            if "chest" in mg or "pec" in mg:
                bucket = "Chest"
            elif "back" in mg or "lat" in mg or "trap" in mg:
                bucket = "Back"
            elif "leg" in mg or "quad" in mg or "ham" in mg or "calf" in mg or "glute" in mg:
                bucket = "Legs"
            elif "shoulder" in mg or "delt" in mg:
                bucket = "Shoulders"
            elif "arm" in mg or "bicep" in mg or "tricep" in mg or "forearm" in mg:
                bucket = "Arms"
            elif "ab" in mg or "core" in mg or "oblique" in mg:
                bucket = "Core"
            elif "cardio" in str(exercise.exercise_type).lower():
                bucket = "Cardio"
            else:
                bucket = "Other"
                
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(exercise)

        def score_exercise(e):
            score = 0
            if focus_areas and e.primary_muscle_group:
                if any(fa.lower() in str(e.primary_muscle_group).lower() for fa in focus_areas):
                    score += 20
            if e.exercise_type and "compound" in str(e.exercise_type).lower():
                score += 10
            if not focus_areas and e.exercise_type:
                if "core" in str(e.exercise_type).lower() or "cardio" in str(e.exercise_type).lower():
                    score += 5
            return score

        for bucket in buckets:
            buckets[bucket].sort(key=lambda e: (score_exercise(e), e.id), reverse=True)

        selected = []
        selected_ids = set()

        target_buckets = []
        if focus_areas:
            for fa in focus_areas:
                fa_lower = fa.lower()
                if "chest" in fa_lower: target_buckets.append("Chest")
                elif "back" in fa_lower: target_buckets.append("Back")
                elif "leg" in fa_lower: target_buckets.append("Legs")
                elif "shoulder" in fa_lower: target_buckets.append("Shoulders")
                elif "arm" in fa_lower: target_buckets.append("Arms")
                elif "core" in fa_lower: target_buckets.append("Core")
        
        target_buckets = list(set(target_buckets))
            
        bucket_indices = {b: 0 for b in buckets.keys()}
        target_limit = int(limit * 0.75) if target_buckets else 0
        
        # Phase 1: Fill primarily from target focus area buckets
        while len(selected) < target_limit:
            added_any = False
            for bucket in target_buckets:
                if bucket in buckets and bucket_indices[bucket] < len(buckets[bucket]):
                    e = buckets[bucket][bucket_indices[bucket]]
                    if e.id not in selected_ids:
                        selected.append(e)
                        selected_ids.add(e.id)
                        added_any = True
                    bucket_indices[bucket] += 1
                if len(selected) >= target_limit:
                    break
            if not added_any:
                break
                
        # Phase 2: Round-robin across ALL buckets for variety (or if no focus_areas specified)
        while len(selected) < limit:
            added_any = False
            for bucket in buckets.keys():
                if bucket_indices[bucket] < len(buckets[bucket]):
                    e = buckets[bucket][bucket_indices[bucket]]
                    if e.id not in selected_ids:
                        selected.append(e)
                        selected_ids.add(e.id)
                        added_any = True
                    bucket_indices[bucket] += 1
                if len(selected) >= limit:
                    break
            if not added_any:
                break
                
        # Phase 3: Add leftovers if limit still not reached
        if len(selected) < limit:
            leftovers = sorted(exercises, key=lambda e: (score_exercise(e), e.id), reverse=True)
            for e in leftovers:
                if len(selected) >= limit:
                    break
                if e.id not in selected_ids:
                    selected.append(e)
                    selected_ids.add(e.id)

        import random
        # Optional: deterministic shuffle to mix up the json array a bit so the LLM doesn't skew to the first items
        random.Random(42).shuffle(selected)
        return selected[:limit]

    def search_by_vector(
        self,
        embedding: List[float],
        limit: int = 5,
    ) -> List[dict]:
        """
        Cosine similarity search using pgvector.

        Returns up to *limit* central_exercises ordered by closeness to *embedding*.
        Each result is a plain dict with exercise fields plus `similarity_score`.
        Rows with no stored embedding are excluded.
        """
        from app.ai_services.embedding_utils import vec_to_pg_str
        vec_str = vec_to_pg_str(embedding)
        rows = self.db.execute(
            text("""
                SELECT
                    id, name, exercise_type, primary_muscle_group,
                    secondary_muscles, equipment_required, difficulty_level, location,
                    1 - (name_embedding <=> CAST(:vec AS vector)) AS similarity_score
                FROM central_exercises
                WHERE is_active = true
                  AND name_embedding IS NOT NULL
                ORDER BY name_embedding <=> CAST(:vec AS vector)
                LIMIT :limit
            """),
            {"vec": vec_str, "limit": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def set_embedding(self, exercise_id: int, embedding: List[float]) -> None:
        """Persist the *embedding* vector for a single central_exercise row."""
        from app.ai_services.embedding_utils import vec_to_pg_str
        self.db.execute(
            text("UPDATE central_exercises SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
            {"vec": vec_to_pg_str(embedding), "id": exercise_id},
        )
        self.db.commit()

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
