import logging
from datetime import date
from typing import List, Optional, Union

from fastapi import HTTPException, status

from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.hydration_log_repository import (
    HydrationLogRepository,
)
from app.shared.repositories.central_food_repository import CentralFoodRepository
from app.shared.repositories.central_exercise_repository import (
    CentralExerciseRepository,
)
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.tracking_module.schemas.tracking import (
    MealLogResponse,
    WorkoutLogResponse,
    WeightLogResponse,
    SleepLogResponse,
    HydrationLogResponse,
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
    MealLogUpdate,
    WorkoutLogUpdate,
    WeightLogUpdate,
    SleepLogUpdate,
    HydrationLogUpdate,
    DailyMacroSummary,
)
from app.ai_services.meal_scanner.dtos import MealScanRequestDTO
from app.ai_services.voice_transcriber.dtos import (
    TranscriptionRequestDTO,
    TranscriptionContextType,
)

logger = logging.getLogger(__name__)


class TrackingService:
    def __init__(
        self,
        workout_repo: WorkoutLogRepository,
        meal_repo: MealLogRepository,
        weight_repo: WeightLogRepository,
        sleep_repo: SleepLogRepository,
        hydration_repo: HydrationLogRepository,
        central_food_repo: CentralFoodRepository,
        central_exercise_repo: CentralExerciseRepository,
        profile_repo: ProfileRepository,
    ):
        self.workout_repo = workout_repo
        self.meal_repo = meal_repo
        self.weight_repo = weight_repo
        self.sleep_repo = sleep_repo
        self.hydration_repo = hydration_repo
        self.central_food_repo = central_food_repo
        self.central_exercise_repo = central_exercise_repo
        self.profile_repo = profile_repo

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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Central food not found.",
                )
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

    def _suggest_foods(
        self, query: Union[str, List[str]], limit: int = 10
    ) -> List[MatchedFoodResponse]:
        """
        Hybrid text + semantic search — top catalog foods for a free-text query
        (or a list of terms, e.g. food names + tags extracted by the AI
        scanner/transcriber).
        """
        rows = self.central_food_repo.hybrid_search_by_text(query, limit)
        return [
            MatchedFoodResponse(
                id=r["id"],
                food_name=r["food_name"],
                food_name_ar=r.get("food_name_ar"),
                food_category=r.get("food_category"),
                calories_per_100g=r.get("calories_per_100g"),
                protein_per_100g=r.get("protein_per_100g"),
                carbs_per_100g=r.get("carbs_per_100g"),
                fats_per_100g=r.get("fats_per_100g"),
                fiber_per_100g=r.get("fiber_per_100g"),
                serving_size_g=r.get("serving_size_g"),
                serving_description=r.get("serving_description"),
                similarity_score=r["similarity_score"],
            )
            for r in rows
        ]

    def _suggest_exercises(
        self, query: Union[str, List[str]], limit: int = 10
    ) -> List[MatchedExerciseResponse]:
        """
        Hybrid text + semantic search — top catalog exercises for a free-text
        query (or a list of terms).
        """
        rows = self.central_exercise_repo.hybrid_search_by_text(query, limit)
        return [
            MatchedExerciseResponse(
                id=r["id"],
                name=r["name"],
                exercise_type=r.get("exercise_type"),
                primary_muscle_group=r.get("primary_muscle_group"),
                secondary_muscles=r.get("secondary_muscles"),
                equipment_required=r.get("equipment_required"),
                difficulty_level=r.get("difficulty_level"),
                location=r.get("location"),
                similarity_score=r["similarity_score"],
            )
            for r in rows
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # Search  (public — used by GET search endpoints)
    # ──────────────────────────────────────────────────────────────────────────

    def search_foods(
        self, query: Union[str, List[str]], limit: int = 10
    ) -> List[MatchedFoodResponse]:
        return self._suggest_foods(query, limit)

    def search_exercises(
        self, query: Union[str, List[str]], limit: int = 10
    ) -> List[MatchedExerciseResponse]:
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
                calories, protein_g, carbs_g, fats_g, sg, desc = (
                    self._resolve_meal_macros(
                        central_food_id=entry.central_food_id,
                        servings=entry.servings,
                        fallback_cals=entry.calories or 0,
                        fallback_protein=entry.protein_g or 0,
                        fallback_carbs=entry.carbs_g or 0,
                        fallback_fats=entry.fats_g or 0,
                        fallback_desc=entry.serving_description_snapshot
                        or "manual serving",
                    )
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
            return SaveLogsResponse(
                category="meal", saved_count=len(saved), meal_logs=saved
            )

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
            return SaveLogsResponse(
                category="workout", saved_count=len(saved), workout_logs=saved
            )

        if request.category == "weight":
            saved = []
            for entry in request.weight_entries:
                log = self.weight_repo.create_log(
                    user_id=user_id,
                    log_date=request.log_date,
                    weight=entry.weight,
                    notes=entry.notes.strip() if entry.notes else None,
                )
                saved.append(WeightLogResponse.model_validate(log))
            return SaveLogsResponse(
                category="weight", saved_count=len(saved), weight_logs=saved
            )

        if request.category == "sleep":
            saved = []
            for entry in request.sleep_entries:
                log = self.sleep_repo.create_log(
                    user_id=user_id,
                    log_date=request.log_date,
                    sleep_hours=entry.sleep_hours,
                    sleep_quality=entry.sleep_quality,
                    notes=entry.notes.strip() if entry.notes else None,
                )
                saved.append(SleepLogResponse.model_validate(log))
            return SaveLogsResponse(
                category="sleep", saved_count=len(saved), sleep_logs=saved
            )

        # hydration
        saved = []
        for entry in request.hydration_entries:
            log = self.hydration_repo.create_log(
                user_id=user_id,
                log_date=request.log_date,
                water_ml=entry.water_ml,
                notes=entry.notes.strip() if entry.notes else None,
            )
            saved.append(HydrationLogResponse.model_validate(log))
        return SaveLogsResponse(
            category="hydration", saved_count=len(saved), hydration_logs=saved
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Get logs by date  (public — used by GET /tracking/logs/* endpoints)
    # ──────────────────────────────────────────────────────────────────────────

    def get_meal_logs(
        self, user_id: int, log_date: Optional[date] = None, limit: int = 50
    ):
        return self.meal_repo.list_logs(
            user_id=user_id, skip=0, limit=limit, log_date=log_date
        )

    def get_workout_logs(
        self, user_id: int, log_date: Optional[date] = None, limit: int = 50
    ):
        return self.workout_repo.list_logs(
            user_id=user_id, skip=0, limit=limit, log_date=log_date
        )

    def get_weight_logs(
        self, user_id: int, log_date: Optional[date] = None, limit: int = 50
    ):
        return self.weight_repo.list_logs(
            user_id=user_id, skip=0, limit=limit, log_date=log_date
        )

    def get_sleep_logs(
        self, user_id: int, log_date: Optional[date] = None, limit: int = 50
    ):
        return self.sleep_repo.list_logs(
            user_id=user_id, skip=0, limit=limit, log_date=log_date
        )

    def get_hydration_logs(
        self, user_id: int, log_date: Optional[date] = None, limit: int = 50
    ):
        return self.hydration_repo.list_logs(
            user_id=user_id, skip=0, limit=limit, log_date=log_date
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Update log
    # ──────────────────────────────────────────────────────────────────────────

    def _get_user_log(self, repo, log_id: int, user_id: int):
        log = repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Log not found."
            )
        return log

    def update_meal_log(self, log_id: int, user_id: int, data: MealLogUpdate):
        self._get_user_log(self.meal_repo, log_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
            )
        return self.meal_repo.update(log_id, updates)

    def update_workout_log(self, log_id: int, user_id: int, data: WorkoutLogUpdate):
        self._get_user_log(self.workout_repo, log_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
            )
        return self.workout_repo.update(log_id, updates)

    def update_weight_log(self, log_id: int, user_id: int, data: WeightLogUpdate):
        self._get_user_log(self.weight_repo, log_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
            )
        return self.weight_repo.update(log_id, updates)

    def update_sleep_log(self, log_id: int, user_id: int, data: SleepLogUpdate):
        self._get_user_log(self.sleep_repo, log_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
            )
        return self.sleep_repo.update(log_id, updates)

    def update_hydration_log(self, log_id: int, user_id: int, data: HydrationLogUpdate):
        self._get_user_log(self.hydration_repo, log_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
            )
        return self.hydration_repo.update(log_id, updates)

    # ──────────────────────────────────────────────────────────────────────────
    # Delete log
    # ──────────────────────────────────────────────────────────────────────────

    def delete_log(self, category: str, log_id: int, user_id: int):
        repo_map = {
            "meal": self.meal_repo,
            "workout": self.workout_repo,
            "weight": self.weight_repo,
            "sleep": self.sleep_repo,
            "hydration": self.hydration_repo,
        }
        repo = repo_map.get(category)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category."
            )
        self._get_user_log(repo, log_id, user_id)
        repo.delete(log_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Daily macro summary
    # ──────────────────────────────────────────────────────────────────────────

    def get_daily_macro_summary(
        self, user_id: int, log_date: date
    ) -> DailyMacroSummary:
        meals = self.meal_repo.list_logs(user_id=user_id, log_date=log_date, limit=200)

        total_cal = sum(m.calories or 0 for m in meals)
        total_prot = sum(m.protein_g or 0 for m in meals)
        total_carbs = sum(m.carbs_g or 0 for m in meals)
        total_fats = sum(m.fats_g or 0 for m in meals)

        if total_cal > 0:
            protein_pct = round(total_prot * 4 / total_cal * 100, 1)
            carbs_pct = round(total_carbs * 4 / total_cal * 100, 1)
            fats_pct = round(total_fats * 9 / total_cal * 100, 1)
        else:
            protein_pct = carbs_pct = fats_pct = 0.0

        return DailyMacroSummary(
            date=log_date,
            total_calories=round(total_cal, 1),
            total_protein_g=round(total_prot, 1),
            total_carbs_g=round(total_carbs, 1),
            total_fats_g=round(total_fats, 1),
            protein_pct=protein_pct,
            carbs_pct=carbs_pct,
            fats_pct=fats_pct,
            meal_count=len(meals),
        )

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

    def scan_meal(
        self,
        scanner,
        image_bytes: bytes,
        image_format: str,
        meal_type,
        language: str,
        user,
    ) -> MealScanResponse:
        # Allergies/dietary preference live on Profile, not User — fetch it explicitly
        # rather than reading (nonexistent) attributes off the auth User object.
        profile = self.profile_repo.get_by_user_id(user.id)
        dto = MealScanRequestDTO(
            image_bytes=image_bytes,
            image_format=image_format,
            user_dietary_preference=getattr(profile, "dietary_preference", None),
            user_allergies=getattr(profile, "allergies", None),
            language=language,
        )
        result = scanner.scan_meal(dto)
        food_names = [fi.name for fi in result.food_items if fi.name]
        matched_foods = (
            self._suggest_foods(food_names + result.tags)
            if (food_names or result.tags)
            else []
        )
        return MealScanResponse(
            meal_name=result.meal_name,
            meal_type=meal_type or result.meal_type,
            food_items=[
                ScannedFoodItemResponse(
                    name=fi.name,
                    portion_size=fi.portion_size,
                    calories=fi.calories,
                    protein_g=fi.protein_g,
                    carbs_g=fi.carbs_g,
                    fats_g=fi.fats_g,
                    fiber_g=fi.fiber_g,
                    confidence=fi.confidence,
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
            matched_foods=matched_foods,
            allergen_warnings=[w.model_dump() for w in result.allergen_warnings],
            scan_successful=result.scan_successful,
            error_message=result.error_message,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AI · Voice  (returns suggestions — does NOT save)
    # ──────────────────────────────────────────────────────────────────────────

    def voice_meal(
        self, transcriber, audio_bytes: bytes, audio_format: str, language, user
    ) -> MealVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            language=language,
            context_type=TranscriptionContextType.MEAL_LOG,
        )
        parsed = transcriber.transcribe_and_parse_meal_log(req)
        search_terms = parsed.food_items + parsed.tags
        matched_foods = self._suggest_foods(search_terms) if search_terms else []
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
            matched_foods=matched_foods,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_workout(
        self, transcriber, audio_bytes: bytes, audio_format: str, language, user
    ) -> WorkoutVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            language=language,
            context_type=TranscriptionContextType.WORKOUT_LOG,
        )
        parsed = transcriber.transcribe_and_parse_workout_log(req)
        exercises = [
            ParsedExerciseResponse(
                name=ex.name,
                sets=ex.sets,
                reps=ex.reps,
                weight_str=ex.weight_str,
                weight_kg=ex.weight_kg,
                duration_seconds=ex.duration_seconds,
                matched_exercises=self._suggest_exercises(ex.name) if ex.name else [],
            )
            for ex in parsed.exercises
        ]
        return WorkoutVoiceResponse(
            raw_text=parsed.raw_text,
            exercises=exercises,
            duration_mentioned=parsed.duration_mentioned,
            tags=parsed.tags,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_weight(
        self, transcriber, audio_bytes: bytes, audio_format: str, language, user
    ) -> WeightVoiceResponse:
        req = TranscriptionRequestDTO(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            language=language,
            context_type=TranscriptionContextType.GENERAL,
        )
        parsed = transcriber.transcribe_and_parse_weight_log(req)
        return WeightVoiceResponse(
            raw_text=parsed.raw_text,
            extracted_weight_kg=parsed.extracted_weight_kg,
            notes=parsed.notes,
            parse_successful=parsed.parse_successful,
        )
