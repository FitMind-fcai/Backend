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
    MealLogResponse,
    WorkoutLogResponse,
    WeightLogResponse,
    SaveLogsRequest,
    SaveLogsResponse,
    ManualFoodCreate,
    ManualExerciseCreate,
    MealScanResponse,
    MatchedFoodResponse,
    ScannedFoodItemResponse,
    MealVoiceResponse,
    WorkoutVoiceResponse,
    WeightVoiceResponse,
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
    # Private helpers — macro resolution
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
        """Returns (calories, protein_g, carbs_g, fats_g, serving_size_g, serving_desc)."""
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

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers — single-row persistence
    # ──────────────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers — vector search
    # ──────────────────────────────────────────────────────────────────────────

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
                           1 - (name_embedding <=> CAST(:vec AS vector)) AS similarity
                    FROM central_foods
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> CAST(:vec AS vector)
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
                if r.similarity >= 0.55
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
                           1 - (name_embedding <=> CAST(:vec AS vector)) AS similarity
                    FROM central_exercises
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> CAST(:vec AS vector)
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
                if r.similarity >= 0.55
            ]
        except Exception as exc:
            logger.warning("Exercise vector search failed (returning empty): %s", exc)
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # Search  (public — used by GET search endpoints)
    # ──────────────────────────────────────────────────────────────────────────

    def search_foods(self, query: str, limit: int = 5) -> List[MatchedFoodResponse]:
        return self._suggest_foods(query, limit)

    def search_exercises(self, query: str, limit: int = 5) -> List[MatchedExerciseResponse]:
        return self._suggest_exercises(query, limit)

    # ──────────────────────────────────────────────────────────────────────────
    # Unified save  (public — used by POST /tracking/logs)
    # ──────────────────────────────────────────────────────────────────────────

    def save_logs(self, user_id: int, request: SaveLogsRequest) -> SaveLogsResponse:
        """
        Persist one or more log entries for any category in a single call.
        All entries are saved atomically — if one fails the request returns an error.
        """
        if request.category == "meal":
            saved = []
            for entry in request.meal_entries:
                meal_name = (entry.meal_name or "").strip() or None
                calories, protein_g, carbs_g, fats_g, sg, desc = self._resolve_meal_macros(
                    central_food_id=entry.central_food_id,
                    servings=entry.servings,
                    fallback_cals=entry.calories or 0,
                    fallback_protein=entry.protein_g or 0,
                    fallback_carbs=entry.carbs_g or 0,
                    fallback_fats=entry.fats_g or 0,
                    fallback_desc=entry.serving_description_snapshot or "manual serving",
                )
                if entry.central_food_id is not None and not meal_name:
                    food = self.central_food_repo.get_by_id(entry.central_food_id)
                    meal_name = food.food_name if food else None
                log = self._save_meal_log(
                    user_id=user_id,
                    central_food_id=entry.central_food_id,
                    log_date=request.log_date,
                    meal_type=entry.meal_type.strip(),
                    meal_name=meal_name,
                    servings=entry.servings,
                    calories=calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fats_g=fats_g,
                    log_method=request.log_method,
                    serving_size_g_snapshot=entry.serving_size_g_snapshot or sg,
                    serving_description_snapshot=desc,
                )
                saved.append(MealLogResponse.model_validate(log))
            return SaveLogsResponse(category="meal", saved_count=len(saved), meal_logs=saved)

        if request.category == "workout":
            saved = []
            for entry in request.workout_entries:
                log = self._save_workout_log(
                    user_id=user_id,
                    central_exercise_id=entry.central_exercise_id,
                    workout_day_exercise_id=entry.workout_day_exercise_id,
                    log_date=request.log_date,
                    sets_completed=entry.sets_completed,
                    reps_completed=entry.reps_completed,
                    weight_used=entry.weight_used,
                    duration_seconds=entry.duration_seconds,
                    notes=entry.notes.strip() if entry.notes else None,
                    log_method=request.log_method,
                )
                saved.append(WorkoutLogResponse.model_validate(log))
            return SaveLogsResponse(category="workout", saved_count=len(saved), workout_logs=saved)

        # weight
        saved = []
        for entry in request.weight_entries:
            log = self.weight_repo.create_log(
                user_id=user_id,
                log_date=request.log_date,
                weight=entry.weight,
                notes=entry.notes.strip() if entry.notes else None,
            )
            saved.append(WeightLogResponse.model_validate(log))
        return SaveLogsResponse(category="weight", saved_count=len(saved), weight_logs=saved)

    # ──────────────────────────────────────────────────────────────────────────
    # Get logs by date  (public — used by GET /tracking/logs/* endpoints)
    # ──────────────────────────────────────────────────────────────────────────

    def get_meal_logs(self, user_id: int, log_date: Optional[date] = None, limit: int = 50):
        return self.meal_repo.list_logs(user_id=user_id, skip=0, limit=limit, log_date=log_date)

    def get_workout_logs(self, user_id: int, log_date: Optional[date] = None, limit: int = 50):
        return self.workout_repo.list_logs(user_id=user_id, skip=0, limit=limit, log_date=log_date)

    def get_weight_logs(self, user_id: int, log_date: Optional[date] = None, limit: int = 50):
        return self.weight_repo.list_logs(user_id=user_id, skip=0, limit=limit, log_date=log_date)

    # ──────────────────────────────────────────────────────────────────────────
    # Catalog  (manual entries)
    # ──────────────────────────────────────────────────────────────────────────

    def create_manual_food(self, user_id: int, payload: ManualFoodCreate):
        factor = 100.0 / payload.serving_size_g
        return self.central_food_repo.create_manual_food(
            user_id=user_id,
            food_data={
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
            },
        )

    def create_manual_exercise(self, user_id: int, payload: ManualExerciseCreate):
        return self.central_exercise_repo.create_manual_exercise(
            user_id=user_id,
            exercise_data={
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
            },
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AI · Scanner  (returns suggestions — does NOT save)
    # ──────────────────────────────────────────────────────────────────────────

    def scan_meal(self, scanner, image_bytes: bytes, image_format: str, meal_type, language: str, user) -> MealScanResponse:
        dto = MealScanRequestDTO(
            image_bytes=image_bytes,
            image_format=image_format,
            user_dietary_preference=getattr(user, "dietary_preference", None),
            user_allergies=getattr(user, "allergies", None),
            language=language,
        )
        result = scanner.scan_meal(dto, db=self.meal_repo.db)
        return MealScanResponse(
            meal_name=result.meal_name,
            meal_type=meal_type or result.meal_type,
            food_items=[
                ScannedFoodItemResponse(
                    name=fi.name, portion_size=fi.portion_size, calories=fi.calories,
                    protein_g=fi.protein_g, carbs_g=fi.carbs_g, fats_g=fi.fats_g,
                    fiber_g=fi.fiber_g, confidence=fi.confidence,
                )
                for fi in result.food_items
            ],
            total_calories=result.total_calories,
            total_protein_g=result.total_protein_g,
            total_carbs_g=result.total_carbs_g,
            total_fats_g=result.total_fats_g,
            tags=result.tags,
            health_notes=result.health_notes,
            confidence_score=result.confidence_score,
            matched_foods=[
                MatchedFoodResponse(
                    id=m.id, food_name=m.food_name, food_category=m.food_category,
                    calories_per_100g=m.calories_per_100g, protein_per_100g=m.protein_per_100g,
                    carbs_per_100g=m.carbs_per_100g, fats_per_100g=m.fats_per_100g,
                    fiber_per_100g=m.fiber_per_100g, serving_size_g=m.serving_size_g,
                    serving_description=m.serving_description, similarity_score=m.similarity_score,
                )
                for m in result.matched_foods
            ],
            allergen_warnings=[w.model_dump() for w in result.allergen_warnings],
            scan_successful=result.scan_successful,
            error_message=result.error_message,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AI · Voice  (returns suggestions — does NOT save)
    # ──────────────────────────────────────────────────────────────────────────

    def voice_meal(self, transcriber, audio_bytes: bytes, audio_format: str, language, user) -> MealVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes, audio_format=audio_format,
            language=language, context_type=TranscriptionContextType.MEAL_LOG,
        )
        parsed = transcriber.transcribe_and_parse_meal_log(req, db=self.meal_repo.db)
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
            matched_foods=[
                MatchedFoodResponse(
                    id=m.id, food_name=m.food_name, food_category=m.food_category,
                    calories_per_100g=m.calories_per_100g, protein_per_100g=m.protein_per_100g,
                    carbs_per_100g=m.carbs_per_100g, fats_per_100g=m.fats_per_100g,
                    fiber_per_100g=m.fiber_per_100g, serving_size_g=m.serving_size_g,
                    serving_description=m.serving_description, similarity_score=m.similarity_score,
                )
                for m in parsed.matched_foods
            ],
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_workout(self, transcriber, audio_bytes: bytes, audio_format: str, language, user) -> WorkoutVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes, audio_format=audio_format,
            language=language, context_type=TranscriptionContextType.WORKOUT_LOG,
        )
        parsed = transcriber.transcribe_and_parse_workout_log(req, db=self.workout_repo.db)
        exercises = []
        for ex in parsed.exercises:
            exercises.append(ParsedExerciseResponse(
                name=ex.name, sets=ex.sets, reps=ex.reps,
                weight_str=ex.weight_str, weight_kg=ex.weight_kg,
                duration_seconds=ex.duration_seconds,
                matched_exercises=[
                    MatchedExerciseResponse(
                        id=m.id, name=m.name, exercise_type=m.exercise_type,
                        primary_muscle_group=m.primary_muscle_group,
                        secondary_muscles=m.secondary_muscles,
                        equipment_required=m.equipment_required,
                        difficulty_level=m.difficulty_level, location=m.location,
                        similarity_score=m.similarity_score,
                    )
                    for m in ex.matched_exercises
                ],
            ))
        return WorkoutVoiceResponse(
            raw_text=parsed.raw_text,
            exercises=exercises,
            duration_mentioned=parsed.duration_mentioned,
            tags=parsed.tags,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_weight(self, transcriber, audio_bytes: bytes, audio_format: str, language, user) -> WeightVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes, audio_format=audio_format,
            language=language, context_type=TranscriptionContextType.GENERAL,
        )
        parsed = transcriber.transcribe_and_parse_weight_log(req)
        return WeightVoiceResponse(
            raw_text=parsed.raw_text,
            extracted_weight_kg=parsed.extracted_weight_kg,
            notes=parsed.notes,
            parse_successful=parsed.parse_successful,
        )
