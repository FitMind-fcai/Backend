import logging
from datetime import date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text as sql_text

from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.shared.repositories.central_food_repository import CentralFoodRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository
from app.tracking_module.schemas.tracking import (
    WorkoutLogCreateText,
    MealLogCreateText,
    WeightLogCreateText,
    ManualFoodCreate,
    ManualExerciseCreate,
    MealLogResponse,
    WorkoutLogResponse,
    MealScanResponse,
    MatchedFoodResponse,
    ScannedFoodItemResponse,
    MealVoiceResponse,
    WorkoutVoiceResponse,
    MatchedExerciseResponse,
    ParsedExerciseResponse,
)
from app.ai_services.meal_scanner.dtos import MealScanRequestDTO
from app.ai_services.voice_transcriber.dtos import TranscriptionRequestDTO, TranscriptionContextType
from app.ai_services.embedding_utils import embed_text, vec_to_pg_str

logger = logging.getLogger(__name__)


class TrackingService:
    def __init__(
        self,
        workout_repo: WorkoutLogRepository,
        meal_repo: MealLogRepository,
        weight_repo: WeightLogRepository,
        central_food_repo: CentralFoodRepository,
        central_exercise_repo: CentralExerciseRepository,
    ):
        self.workout_repo = workout_repo
        self.meal_repo = meal_repo
        self.weight_repo = weight_repo
        self.central_food_repo = central_food_repo
        self.central_exercise_repo = central_exercise_repo

    # ──────────────────────────────────────────────────────────────────────────
    # Shared private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_meal_macros(
        self,
        central_food_id: Optional[int],
        servings: float,
        fallback_cals: float,
        fallback_protein: float,
        fallback_carbs: float,
        fallback_fats: float,
        fallback_desc: str = "manual serving",
    ):
        """
        Returns (calories, protein_g, carbs_g, fats_g, serving_size_g, serving_desc).
        If central_food_id is given, macros come from the catalog; otherwise fallback values are used.
        """
        if central_food_id is not None:
            food = self.central_food_repo.get_by_id(central_food_id)
            if not food:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Central food not found.")
            sg = float(food.serving_size_g or 100.0)
            desc = food.serving_description or f"{sg:g} g"
            m = (sg * servings) / 100.0
            return (
                round((food.calories_per_100g or 0) * m, 2),
                round((food.protein_per_100g or 0) * m, 2),
                round((food.carbs_per_100g or 0) * m, 2),
                round((food.fats_per_100g or 0) * m, 2),
                sg,
                desc,
            )
        return (
            round(fallback_cals, 2),
            round(fallback_protein, 2),
            round(fallback_carbs, 2),
            round(fallback_fats, 2),
            None,
            fallback_desc,
        )

    def _save_meal_log(
        self,
        user_id: int,
        central_food_id: Optional[int],
        log_date: date,
        meal_type: str,
        meal_name: str,
        servings: float,
        calories: float,
        protein_g: float,
        carbs_g: float,
        fats_g: float,
        log_method: str,
        serving_size_g_snapshot: Optional[float] = None,
        serving_description_snapshot: Optional[str] = None,
    ):
        """Single persistence point for all meal log flows (TEXT / CAMERA / VOICE)."""
        return self.meal_repo.create_log(
            user_id=user_id,
            central_food_id=central_food_id,
            log_date=log_date,
            meal_type=meal_type,
            meal_name=meal_name,
            servings=servings,
            serving_size_g_snapshot=serving_size_g_snapshot,
            serving_description_snapshot=serving_description_snapshot,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fats_g=fats_g,
            log_method=log_method,
            image_url=None,
        )

    def _save_workout_log(
        self,
        user_id: int,
        central_exercise_id: Optional[int],
        log_date: date,
        sets_completed: int,
        reps_completed: int,
        weight_used: Optional[float],
        duration_seconds: Optional[int],
        notes: Optional[str],
        log_method: str,
        workout_day_exercise_id: Optional[int] = None,
    ):
        """Single persistence point for all workout log flows (TEXT / CAMERA / VOICE)."""
        return self.workout_repo.create_log(
            user_id=user_id,
            central_exercise_id=central_exercise_id,
            workout_day_exercise_id=workout_day_exercise_id,
            log_date=log_date,
            sets_completed=sets_completed,
            reps_completed=reps_completed,
            weight_used=weight_used,
            duration_seconds=duration_seconds,
            notes=notes,
        )

    def _suggest_foods(self, query: str, limit: int = 5) -> List[MatchedFoodResponse]:
        """pgvector cosine search — top catalog foods for a free-text query."""
        if not query or not query.strip():
            return []
        try:
            vec = vec_to_pg_str(embed_text(query.strip()))
            rows = self.meal_repo.db.execute(
                sql_text("""
                    SELECT id, food_name, food_category,
                           calories_per_100g, protein_per_100g, carbs_per_100g,
                           fats_per_100g, fiber_per_100g, serving_size_g, serving_description,
                           1 - (name_embedding <=> :vec::vector) AS similarity
                    FROM central_foods
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> :vec::vector
                    LIMIT :lim
                """),
                {"vec": vec, "lim": limit},
            ).fetchall()
            return [
                MatchedFoodResponse(
                    id=r.id, food_name=r.food_name, food_category=r.food_category,
                    calories_per_100g=r.calories_per_100g, protein_per_100g=r.protein_per_100g,
                    carbs_per_100g=r.carbs_per_100g, fats_per_100g=r.fats_per_100g,
                    fiber_per_100g=r.fiber_per_100g, serving_size_g=r.serving_size_g,
                    serving_description=r.serving_description, similarity_score=float(r.similarity),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Food vector search failed (returning empty): %s", exc)
            return []

    def _suggest_exercises(self, query: str, limit: int = 5) -> List[MatchedExerciseResponse]:
        """pgvector cosine search — top catalog exercises for a free-text query."""
        if not query or not query.strip():
            return []
        try:
            vec = vec_to_pg_str(embed_text(query.strip()))
            rows = self.workout_repo.db.execute(
                sql_text("""
                    SELECT id, name, exercise_type, primary_muscle_group,
                           secondary_muscles, equipment_required, difficulty_level, location,
                           1 - (name_embedding <=> :vec::vector) AS similarity
                    FROM central_exercises
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> :vec::vector
                    LIMIT :lim
                """),
                {"vec": vec, "lim": limit},
            ).fetchall()
            return [
                MatchedExerciseResponse(
                    id=r.id, name=r.name, exercise_type=r.exercise_type,
                    primary_muscle_group=r.primary_muscle_group,
                    secondary_muscles=r.secondary_muscles,
                    equipment_required=r.equipment_required,
                    difficulty_level=r.difficulty_level, location=r.location,
                    similarity_score=float(r.similarity),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Exercise vector search failed (returning empty): %s", exc)
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # Meal Logs
    # ──────────────────────────────────────────────────────────────────────────

    def create_meal_log(self, user_id: int, payload: MealLogCreateText) -> MealLogResponse:
        """
        Save a meal log produced by any input method (TEXT / CAMERA / VOICE).
        The caller has already received suggestions and chosen a central_food_id.
        """
        meal_name = payload.meal_name.strip() if payload.meal_name else None

        calories, protein_g, carbs_g, fats_g, serving_size_g, serving_desc = self._resolve_meal_macros(
            central_food_id=payload.central_food_id,
            servings=payload.servings,
            fallback_cals=payload.calories or 0,
            fallback_protein=payload.protein_g or 0,
            fallback_carbs=payload.carbs_g or 0,
            fallback_fats=payload.fats_g or 0,
            fallback_desc=payload.serving_description_snapshot or "manual serving",
        )

        if payload.central_food_id is not None:
            food = self.central_food_repo.get_by_id(payload.central_food_id)
            meal_name = meal_name or (food.food_name if food else None)

        meal_log = self._save_meal_log(
            user_id=user_id,
            central_food_id=payload.central_food_id,
            log_date=payload.log_date,
            meal_type=payload.meal_type.strip(),
            meal_name=meal_name,
            servings=payload.servings,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fats_g=fats_g,
            log_method=payload.log_method,
            serving_size_g_snapshot=payload.serving_size_g_snapshot or serving_size_g,
            serving_description_snapshot=serving_desc,
        )
        return MealLogResponse.model_validate(meal_log)

    def list_meal_logs(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
    ):
        return self.meal_repo.list_logs(
            user_id=user_id, skip=skip, limit=limit,
            log_date=log_date, meal_type=meal_type,
        )

    def get_meal_log(self, user_id: int, log_id: int):
        log = self.meal_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal log not found.")
        return log

    def delete_meal_log(self, user_id: int, log_id: int):
        log = self.get_meal_log(user_id=user_id, log_id=log_id)
        self.meal_repo.delete(log.id)
        return {"message": "Meal log deleted successfully."}

    # ──────────────────────────────────────────────────────────────────────────
    # Workout Logs
    # ──────────────────────────────────────────────────────────────────────────

    def create_workout_log(self, user_id: int, payload: WorkoutLogCreateText) -> WorkoutLogResponse:
        """
        Save a workout log produced by any input method (TEXT / CAMERA / VOICE).
        The caller has already received suggestions and chosen a central_exercise_id.
        """
        workout_log = self._save_workout_log(
            user_id=user_id,
            central_exercise_id=payload.central_exercise_id,
            workout_day_exercise_id=payload.workout_day_exercise_id,
            log_date=payload.log_date,
            sets_completed=payload.sets_completed,
            reps_completed=payload.reps_completed,
            weight_used=payload.weight_used,
            duration_seconds=payload.duration_seconds,
            notes=payload.notes.strip() if payload.notes else None,
            log_method=payload.log_method,
        )
        return WorkoutLogResponse.model_validate(workout_log)

    def list_workout_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None):
        return self.workout_repo.list_logs(user_id=user_id, skip=skip, limit=limit, log_date=log_date)

    def get_workout_log(self, user_id: int, log_id: int):
        log = self.workout_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout log not found.")
        return log

    def delete_workout_log(self, user_id: int, log_id: int):
        log = self.get_workout_log(user_id=user_id, log_id=log_id)
        self.workout_repo.delete(log.id)
        return {"message": "Workout log deleted successfully."}

    # ──────────────────────────────────────────────────────────────────────────
    # Weight Logs
    # ──────────────────────────────────────────────────────────────────────────

    def create_weight_log(self, user_id: int, payload: WeightLogCreateText):
        return self.weight_repo.create_log(
            user_id=user_id,
            log_date=payload.log_date,
            weight=payload.weight,
            notes=payload.notes.strip() if payload.notes else None,
        )

    def list_weight_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None):
        return self.weight_repo.list_logs(user_id=user_id, skip=skip, limit=limit, log_date=log_date)

    def get_weight_log(self, user_id: int, log_id: int):
        log = self.weight_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weight log not found.")
        return log

    def delete_weight_log(self, user_id: int, log_id: int):
        log = self.get_weight_log(user_id=user_id, log_id=log_id)
        self.weight_repo.delete(log.id)
        return {"message": "Weight log deleted successfully."}

    # ──────────────────────────────────────────────────────────────────────────
    # Search — text
    # ──────────────────────────────────────────────────────────────────────────

    def search_foods(self, user_id: int, query: str, limit: int = 20):
        foods = self.central_food_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)
        results = []
        for food in foods:
            sg = float(food.serving_size_g or 100.0)
            m = sg / 100.0
            results.append({
                "id": food.id,
                "food_name": food.food_name,
                "food_category": food.food_category,
                "serving_size_g": sg,
                "serving_description": food.serving_description or f"{sg:g} g",
                "calories_per_serving": round((food.calories_per_100g or 0) * m, 2),
                "protein_g_per_serving": round((food.protein_per_100g or 0) * m, 2),
                "carbs_g_per_serving": round((food.carbs_per_100g or 0) * m, 2),
                "fats_g_per_serving": round((food.fats_per_100g or 0) * m, 2),
                "fiber_g_per_serving": round((food.fiber_per_100g or 0) * m, 2),
                "source": food.source,
            })
        return results

    def search_exercises(self, user_id: int, query: str, limit: int = 20):
        return self.central_exercise_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)

    # Search — semantic / vector (delegates to the shared helpers above)
    def search_foods_vector(self, query: str, limit: int = 5) -> List[MatchedFoodResponse]:
        return self._suggest_foods(query, limit)

    def search_exercises_vector(self, query: str, limit: int = 5) -> List[MatchedExerciseResponse]:
        return self._suggest_exercises(query, limit)

    # ──────────────────────────────────────────────────────────────────────────
    # Catalog — manual entries
    # ──────────────────────────────────────────────────────────────────────────

    def create_manual_food(self, user_id: int, payload: ManualFoodCreate):
        factor = 100.0 / payload.serving_size_g
        food_data = {
            "food_name": payload.food_name.strip(),
            "food_category": payload.food_category,
            "calories_per_100g": payload.calories_per_serving * factor,
            "protein_per_100g": payload.protein_g_per_serving * factor,
            "carbs_per_100g": payload.carbs_g_per_serving * factor,
            "fats_per_100g": payload.fats_g_per_serving * factor,
            "fiber_per_100g": (payload.fiber_g_per_serving or 0) * factor,
            "serving_size_g": payload.serving_size_g,
            "serving_description": payload.serving_description,
            "dietary_tags": [],
            "usda_fdc_id": None,
        }
        return self.central_food_repo.create_manual_food(user_id=user_id, food_data=food_data)

    def create_manual_exercise(self, user_id: int, payload: ManualExerciseCreate):
        exercise_data = {
            "name": payload.name.strip(),
            "exercise_type": payload.exercise_type,
            "primary_muscle_group": payload.primary_muscle_group,
            "secondary_muscles": payload.secondary_muscles,
            "equipment_required": payload.equipment_required,
            "difficulty_level": payload.difficulty_level,
            "location": payload.location,
            "instructions": payload.instructions,
            "video_url": None,
            "image_url": None,
        }
        return self.central_exercise_repo.create_manual_exercise(user_id=user_id, exercise_data=exercise_data)

    # ──────────────────────────────────────────────────────────────────────────
    # AI · Meal Scanner  (suggest step — does NOT save)
    # ──────────────────────────────────────────────────────────────────────────

    def scan_meal(
        self, scanner, image_bytes: bytes, image_format: str, meal_type, language: str, user
    ) -> MealScanResponse:
        """
        Analyse a meal photo and return scan results + top-5 catalog suggestions.
        The client then picks a central_food_id and calls POST /meals to save.
        """
        dto = MealScanRequestDTO(
            image_bytes=image_bytes,
            image_format=image_format,
            user_dietary_preference=getattr(user, "dietary_preference", None),
            user_allergies=getattr(user, "allergies", None),
            language=language,
        )
        result = scanner.scan_meal(dto, db=self.meal_repo.db)

        matched = [
            MatchedFoodResponse(
                id=m.id, food_name=m.food_name, food_category=m.food_category,
                calories_per_100g=m.calories_per_100g, protein_per_100g=m.protein_per_100g,
                carbs_per_100g=m.carbs_per_100g, fats_per_100g=m.fats_per_100g,
                fiber_per_100g=m.fiber_per_100g, serving_size_g=m.serving_size_g,
                serving_description=m.serving_description, similarity_score=m.similarity_score,
            )
            for m in result.matched_foods
        ]
        food_items = [
            ScannedFoodItemResponse(
                name=fi.name, portion_size=fi.portion_size, calories=fi.calories,
                protein_g=fi.protein_g, carbs_g=fi.carbs_g, fats_g=fi.fats_g,
                fiber_g=fi.fiber_g, confidence=fi.confidence,
            )
            for fi in result.food_items
        ]
        return MealScanResponse(
            meal_name=result.meal_name,
            meal_type=meal_type or result.meal_type,
            food_items=food_items,
            total_calories=result.total_calories,
            total_protein_g=result.total_protein_g,
            total_carbs_g=result.total_carbs_g,
            total_fats_g=result.total_fats_g,
            tags=result.tags,
            health_notes=result.health_notes,
            confidence_score=result.confidence_score,
            matched_foods=matched,
            allergen_warnings=[w.model_dump() for w in result.allergen_warnings],
            scan_successful=result.scan_successful,
            error_message=result.error_message,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AI · Voice  (suggest step — does NOT save)
    # ──────────────────────────────────────────────────────────────────────────

    def voice_meal(
        self, transcriber, audio_bytes: bytes, audio_format: str, language, user
    ) -> MealVoiceResponse:
        """
        Transcribe a meal voice clip and return parsed data + top-5 catalog suggestions.
        The client then picks a central_food_id and calls POST /meals to save.
        """
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes, audio_format=audio_format,
            language=language, context_type=TranscriptionContextType.MEAL_LOG,
        )
        parsed = transcriber.transcribe_and_parse_meal_log(req, db=self.meal_repo.db)

        matched = [
            MatchedFoodResponse(
                id=m.id, food_name=m.food_name, food_category=m.food_category,
                calories_per_100g=m.calories_per_100g, protein_per_100g=m.protein_per_100g,
                carbs_per_100g=m.carbs_per_100g, fats_per_100g=m.fats_per_100g,
                fiber_per_100g=m.fiber_per_100g, serving_size_g=m.serving_size_g,
                serving_description=m.serving_description, similarity_score=m.similarity_score,
            )
            for m in parsed.matched_foods
        ]
        return MealVoiceResponse(
            raw_text=parsed.raw_text,
            meal_name=parsed.meal_name,
            meal_type=parsed.meal_type,
            food_items=parsed.food_items,
            portions=parsed.portions,
            tags=parsed.tags,
            estimated_calories=parsed.estimated_calories,
            estimated_protein_g=parsed.estimated_protein_g,
            estimated_carbs_g=parsed.estimated_carbs_g,
            estimated_fats_g=parsed.estimated_fats_g,
            matched_foods=matched,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_workout(
        self, transcriber, audio_bytes: bytes, audio_format: str, language, user
    ) -> WorkoutVoiceResponse:
        """
        Transcribe a workout voice clip and return parsed exercises + top-5 catalog suggestions per exercise.
        The client then picks a central_exercise_id per exercise and calls POST /workouts once each to save.
        """
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes, audio_format=audio_format,
            language=language, context_type=TranscriptionContextType.WORKOUT_LOG,
        )
        parsed = transcriber.transcribe_and_parse_workout_log(req, db=self.workout_repo.db)

        exercises = []
        for ex in parsed.exercises:
            matched = [
                MatchedExerciseResponse(
                    id=m.id, name=m.name, exercise_type=m.exercise_type,
                    primary_muscle_group=m.primary_muscle_group,
                    secondary_muscles=m.secondary_muscles,
                    equipment_required=m.equipment_required,
                    difficulty_level=m.difficulty_level, location=m.location,
                    similarity_score=m.similarity_score,
                )
                for m in ex.matched_exercises
            ]
            exercises.append(ParsedExerciseResponse(
                name=ex.name, sets=ex.sets, reps=ex.reps,
                weight_str=ex.weight_str, weight_kg=ex.weight_kg,
                duration_seconds=ex.duration_seconds, matched_exercises=matched,
            ))

        return WorkoutVoiceResponse(
            raw_text=parsed.raw_text,
            exercises=exercises,
            duration_mentioned=parsed.duration_mentioned,
            tags=parsed.tags,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )
