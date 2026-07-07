from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, text
from typing import Dict, List, Optional, Union
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralExercise
from app.planning_module.models.enums import EquipmentAvailability, WorkoutDifficulty


def _ev(v) -> str:
    """Return the string value of an enum instance or a plain string."""
    return v.value if hasattr(v, "value") else str(v)


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
        limit: int = 25,
        goal: str = "maintain",
        injuries: str = "",
    ) -> str:
        """
        Fetch a structured constraint JSON of exercises matching preferences,
        ranked by goal alignment and injury compatibility.
        """
        from sqlalchemy import or_
        query = self.db.query(CentralExercise).filter(CentralExercise.is_active == True)

        # 1. Equipment Constraints
        equip = _ev(equipment_availability)
        if equip == EquipmentAvailability.NO_EQUIPMENT.value:
            query = query.filter(
                (CentralExercise.equipment_required.ilike('%body%')) |
                (CentralExercise.equipment_required.ilike('%none%'))
            )
        elif equip == EquipmentAvailability.BASIC_EQUIPMENT.value:
            basic_equip = ['body', 'none', 'dumbbell', 'band', 'kettlebell', 'medicine ball', 'foam roll']
            conditions = [CentralExercise.equipment_required.ilike(f'%{e}%') for e in basic_equip]
            query = query.filter(or_(*conditions))
        # EquipmentAvailability.FULL_GYM — no filter needed, all exercises allowed

        # 2. Difficulty Constraints
        diff = _ev(workout_difficulty)
        if diff == WorkoutDifficulty.BEGINNER.value:
            query = query.filter(CentralExercise.difficulty_level.ilike('%beginner%'))
        elif diff == WorkoutDifficulty.INTERMEDIATE.value:
            query = query.filter(
                (CentralExercise.difficulty_level.ilike('%beginner%')) |
                (CentralExercise.difficulty_level.ilike('%intermediate%'))
            )
        # WorkoutDifficulty.ADVANCED — no filter, all difficulties allowed

        exercises = query.all()

        if not exercises:
            return '{"error": "No exercises match the restrictive filters", "instruction": "Generate functional bodyweight variations as fallback."}'

        # Phase 2: Rank by goal alignment + injury compatibility before bucket selection
        ranked = self._rank_exercises_for_goal(exercises, goal=goal, injuries=injuries)
        top_exercises = self._select_balanced_exercises_for_prompt(ranked, limit, focus_areas)

        import json
        catalog = []
        for e in top_exercises:
            catalog.append({
                "id": e.id,
                "name": e.name,
                "muscle": e.primary_muscle_group,
                "equipment": e.equipment_required,
                "type": e.exercise_type,
                "level": e.difficulty_level,
            })

        constraints_block = {
            "MANDATORY_EXERCISE_CATALOG": catalog,
            "INSTRUCTION": (
                "You MUST ONLY generate workouts using the exact exercises and IDs from this catalog. "
                "Do not invent new exercises."
            ),
        }
        return json.dumps(constraints_block, indent=2)

    def _rank_exercises_for_goal(
        self,
        exercises: List[CentralExercise],
        goal: str = "maintain",
        injuries: str = "",
    ) -> List[CentralExercise]:
        """
        Score exercises by goal alignment, injury compatibility, and volume efficiency,
        then return them sorted highest-to-lowest so that bucket selection sees the best
        candidates first.

        Ranking factors and weights (matching the architecture upgrade plan):
          Goal Match            — High  (30 pts)
          Experience Match      — High  (20 pts, via compound/isolation preference)
          Equipment Match       — Medium (already handled upstream by SQL filter)
          Injury Compatibility  — High  (−25 pts penalty per risky exercise)
          Volume Compatibility  — Medium (15 pts for compound movements)
        """
        goal = (goal or "maintain").lower().replace(" ", "_")
        injury_text = (injuries or "").lower()

        _COMPOUND_KEYWORDS = [
            "squat", "deadlift", "bench press", "overhead press",
            "barbell row", "pull-up", "chin-up", "lunge", "hip thrust",
            "military press", "dumbbell press", "incline press",
            "leg press", "romanian deadlift", "front squat",
            "pendlay row", "t-bar row", "dip",
        ]

        def _is_compound(name: str, etype: str) -> bool:
            return "compound" in etype or any(k in name for k in _COMPOUND_KEYWORDS)

        def _score(e: CentralExercise) -> float:
            s = 0.0
            name  = (e.name or "").lower()
            etype = (e.exercise_type or "").lower()
            compound = _is_compound(name, etype)

            # ── Goal Match (30 pts) ──────────────────────────────────────────
            if goal == "build_muscle":
                if compound:
                    s += 30
                elif any(k in name for k in [
                    "curl", "extension", "fly", "raise", "pushdown",
                    "kickback", "cable", "machine",
                ]):
                    s += 12
                elif "stretching" in etype:
                    s += 3
                else:
                    s += 8
            elif goal == "lose_weight":
                if "cardio" in etype or any(k in name for k in [
                    "burpee", "jump", "circuit", "mountain climber",
                    "box jump", "sprint", "hiit",
                ]):
                    s += 30
                elif compound:
                    s += 22
                else:
                    s += 10
            elif goal == "improve_fitness":
                if "cardio" in etype or compound:
                    s += 25
                else:
                    s += 12
            else:  # maintain / general
                if compound:
                    s += 20
                else:
                    s += 10

            # ── Volume Compatibility (15 pts) ────────────────────────────────
            if compound:
                s += 15
            elif "isolation" in etype:
                s += 5

            # ── Injury Compatibility — penalties (−25 pts each) ──────────────
            if "shoulder" in injury_text or "impingement" in injury_text:
                overhead_kw = [
                    "overhead press", "military press", "arnold press",
                    "push press", "behind neck", "behind-neck",
                    "upright row",
                ]
                if any(k in name for k in overhead_kw):
                    s -= 25

            if "knee" in injury_text:
                if any(k in name for k in [
                    "jump squat", "box jump", "plyometric", "lunge jump",
                ]):
                    s -= 25

            if "lower back" in injury_text or "back pain" in injury_text:
                if any(k in name for k in [
                    "conventional deadlift", "good morning",
                    "roman chair", "hyperextension",
                ]):
                    s -= 25

            if "wrist" in injury_text:
                if any(k in name for k in ["barbell curl", "wrist curl"]):
                    s -= 15

            return s

        return sorted(exercises, key=lambda e: (_score(e), e.id), reverse=True)

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

    def hybrid_search_by_text(
        self, query: Union[str, List[str]], limit: int = 10
    ) -> List[dict]:
        """
        Shared catalog search: exact substring match first, falling back to
        vector/embedding similarity only if the text layer didn't fill the
        quota. Used by every entry point that needs "find exercises matching
        this text" — the manual search endpoint and the voice transcriber —
        so both agree on one search behavior instead of separate
        implementations drifting apart.

        query: a single search phrase (manual text search), or a list of
        terms (e.g. exercise names + tags from the voice AI). Each term is
        searched independently in both layers and results are merged/deduped
        — terms are NOT joined into one blended phrase (see
        CentralFoodRepository.hybrid_search_by_text for why).
        """
        from app.ai_services.embedding_utils import embed_texts

        if isinstance(query, (list, tuple)):
            terms = [t.strip() for t in query if t and t.strip()]
        else:
            terms = [query.strip()] if query and query.strip() else []
        if not terms:
            return []

        seen_ids: set = set()
        results: List[dict] = []

        # ── Layer 1: exact substring match — any term may match a row ──────
        try:
            or_clauses = " OR ".join(f"name ILIKE :t{i}" for i in range(len(terms)))
            params = {f"t{i}": f"%{term}%" for i, term in enumerate(terms)}
            text_rows = self.db.execute(
                text(f"""
                    SELECT id, name, exercise_type, primary_muscle_group,
                           secondary_muscles, equipment_required, difficulty_level, location
                    FROM central_exercises
                    WHERE is_active = true AND ({or_clauses})
                    LIMIT :lim
                """),
                {**params, "lim": limit},
            ).fetchall()
            for r in text_rows:
                if r.id in seen_ids:
                    continue
                seen_ids.add(r.id)
                row = dict(r._mapping)
                row["similarity_score"] = 1.0
                results.append(row)
        except Exception:
            pass

        if len(results) >= limit:
            return results[:limit]

        # ── Layer 2: vector similarity — per term, keep best score per row ──
        try:
            best_by_id: Dict[int, dict] = {}
            for vec in embed_texts(terms):
                for row in self.search_by_vector(vec, limit=limit * 2):
                    if row["id"] in seen_ids or row["similarity_score"] < 0.55:
                        continue
                    existing = best_by_id.get(row["id"])
                    if existing is None or row["similarity_score"] > existing["similarity_score"]:
                        best_by_id[row["id"]] = row
            for row in sorted(
                best_by_id.values(), key=lambda r: r["similarity_score"], reverse=True
            ):
                seen_ids.add(row["id"])
                results.append(row)
                if len(results) >= limit:
                    break
        except Exception:
            pass

        return results[:limit]

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
