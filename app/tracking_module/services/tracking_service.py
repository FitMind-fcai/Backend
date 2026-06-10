from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, status

from app.tracking_module.models.enums import LogMethod
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
    MealScanRequest,
    MealScanLogRequest,
    MealScanResponse,
    MealScanLogResponse,
    MatchedFoodResponse,
    ScannedFoodItemResponse,
    MealLogResponse,
    WorkoutLogResponse,
    MealVoiceRequest,
    MealVoiceLogRequest,
    MealVoiceResponse,
    MealVoiceLogResponse,
    WorkoutVoiceRequest,
    WorkoutVoiceLogRequest,
    WorkoutVoiceResponse,
    WorkoutVoiceLogResponse,
    MatchedExerciseResponse,
    ParsedExerciseResponse,
    LoggedWorkoutEntry,
)
from app.ai_services.meal_scanner.dtos import MealScanRequestDTO
from app.ai_services.voice_transcriber.dtos import TranscriptionRequestDTO, TranscriptionContextType


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

    def create_workout_log_text(self, user_id: int, payload: WorkoutLogCreateText):
        return self.workout_repo.create_log(
            user_id=user_id,
            central_exercise_id=payload.central_exercise_id,
            workout_day_exercise_id=payload.workout_day_exercise_id,
            log_date=payload.log_date,
            sets_completed=payload.sets_completed,
            reps_completed=payload.reps_completed,
            weight_used=payload.weight_used,
            duration_seconds=payload.duration_seconds,
            notes=payload.notes.strip() if payload.notes else None,
        )

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

    def create_meal_log_text(self, user_id: int, payload: MealLogCreateText):
        serving_size_g_snapshot = payload.serving_size_g_snapshot
        serving_description_snapshot = payload.serving_description_snapshot
        meal_name = payload.meal_name.strip() if payload.meal_name else None

        calories = payload.calories
        protein_g = payload.protein_g
        carbs_g = payload.carbs_g
        fats_g = payload.fats_g

        if payload.central_food_id is not None:
            food = self.central_food_repo.get_by_id(payload.central_food_id)
            if not food:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Central food not found.",
                )
            serving_size_g_snapshot = float(food.serving_size_g or 100.0)
            serving_description_snapshot = food.serving_description or f"{serving_size_g_snapshot:g} g"
            meal_name = meal_name or food.food_name

            # Auto-calculate totals from central per-100g values and consumed servings.
            grams_consumed = serving_size_g_snapshot * payload.servings
            multiplier = grams_consumed / 100.0
            calories = (food.calories_per_100g or 0) * multiplier
            protein_g = (food.protein_per_100g or 0) * multiplier
            carbs_g = (food.carbs_per_100g or 0) * multiplier
            fats_g = (food.fats_per_100g or 0) * multiplier
        elif not serving_description_snapshot:
            serving_description_snapshot = "manual serving"

        return self.meal_repo.create_log(
            user_id=user_id,
            central_food_id=payload.central_food_id,
            log_date=payload.log_date,
            meal_type=payload.meal_type.strip(),
            meal_name=meal_name,
            servings=payload.servings,
            serving_size_g_snapshot=serving_size_g_snapshot,
            serving_description_snapshot=serving_description_snapshot,
            calories=round(calories, 2),
            protein_g=round(protein_g, 2),
            carbs_g=round(carbs_g, 2),
            fats_g=round(fats_g, 2),
            log_method=LogMethod.TEXT.value,
            image_url=None,
        )

    def list_meal_logs(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
    ):
        return self.meal_repo.list_logs(
            user_id=user_id,
            skip=skip,
            limit=limit,
            log_date=log_date,
            meal_type=meal_type,
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

    def create_weight_log_text(self, user_id: int, payload: WeightLogCreateText):
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

    def search_foods(self, user_id: int, query: str, limit: int = 20):
        foods = self.central_food_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)
        results = []
        for food in foods:
            serving_size = float(food.serving_size_g or 100.0)
            multiplier = serving_size / 100.0
            results.append(
                {
                    "id": food.id,
                    "food_name": food.food_name,
                    "food_category": food.food_category,
                    "serving_size_g": serving_size,
                    "serving_description": food.serving_description or f"{serving_size:g} g",
                    "calories_per_serving": round((food.calories_per_100g or 0) * multiplier, 2),
                    "protein_g_per_serving": round((food.protein_per_100g or 0) * multiplier, 2),
                    "carbs_g_per_serving": round((food.carbs_per_100g or 0) * multiplier, 2),
                    "fats_g_per_serving": round((food.fats_per_100g or 0) * multiplier, 2),
                    "fiber_g_per_serving": round((food.fiber_per_100g or 0) * multiplier, 2),
                    "source": food.source,
                }
            )
        return results

    def search_exercises(self, user_id: int, query: str, limit: int = 20):
        return self.central_exercise_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)

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
    # Meal Scanner
    # ──────────────────────────────────────────────────────────────────────────

    def scan_meal(self, scanner, request_payload: MealScanRequest, user) -> MealScanResponse:
        """Run Qwen2.5-VL on the image; return nutrition + top-5 matched foods."""
        dto = MealScanRequestDTO(
            image_base64=request_payload.image_base64,
            image_format=request_payload.image_format,
            user_dietary_preference=getattr(user, "dietary_preference", None),
            user_allergies=getattr(user, "allergies", None),
            language=request_payload.language,
        )
        result = scanner.scan_meal(dto, db=self.meal_repo.db)

        matched = [
            MatchedFoodResponse(
                id=m.id,
                food_name=m.food_name,
                food_category=m.food_category,
                calories_per_100g=m.calories_per_100g,
                protein_per_100g=m.protein_per_100g,
                carbs_per_100g=m.carbs_per_100g,
                fats_per_100g=m.fats_per_100g,
                fiber_per_100g=m.fiber_per_100g,
                serving_size_g=m.serving_size_g,
                serving_description=m.serving_description,
                similarity_score=m.similarity_score,
            )
            for m in result.matched_foods
        ]
        food_items = [
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
        ]
        return MealScanResponse(
            meal_name=result.meal_name,
            meal_type=request_payload.meal_type or result.meal_type,
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

    def scan_and_log_meal(self, scanner, payload: MealScanLogRequest, user) -> MealScanLogResponse:
        """Scan image with Qwen2.5-VL then immediately persist a MealLog."""
        scan_request = MealScanRequest(
            image_base64=payload.image_base64,
            image_format=payload.image_format,
            meal_type=payload.meal_type,
            language=payload.language,
        )
        scan_response = self.scan_meal(scanner=scanner, request_payload=scan_request, user=user)

        if not scan_response.scan_successful:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Meal scan failed: {scan_response.error_message}",
            )

        # Determine macros: prefer selected central_food over AI estimates.
        calories = float(scan_response.total_calories)
        protein_g = scan_response.total_protein_g
        carbs_g = scan_response.total_carbs_g
        fats_g = scan_response.total_fats_g
        serving_size_g_snapshot = None
        serving_description_snapshot = "AI-estimated serving"

        if payload.central_food_id is not None:
            food = self.central_food_repo.get_by_id(payload.central_food_id)
            if not food:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Central food not found.")
            serving_size_g_snapshot = float(food.serving_size_g or 100.0)
            serving_description_snapshot = food.serving_description or f"{serving_size_g_snapshot:g} g"
            grams = serving_size_g_snapshot * payload.servings
            multiplier = grams / 100.0
            calories = (food.calories_per_100g or 0) * multiplier
            protein_g = (food.protein_per_100g or 0) * multiplier
            carbs_g = (food.carbs_per_100g or 0) * multiplier
            fats_g = (food.fats_per_100g or 0) * multiplier

        meal_log = self.meal_repo.create_log(
            user_id=user.id,
            central_food_id=payload.central_food_id,
            log_date=payload.log_date,
            meal_type=payload.meal_type,
            meal_name=scan_response.meal_name,
            servings=payload.servings,
            serving_size_g_snapshot=serving_size_g_snapshot,
            serving_description_snapshot=serving_description_snapshot,
            calories=round(calories, 2),
            protein_g=round(protein_g, 2),
            carbs_g=round(carbs_g, 2),
            fats_g=round(fats_g, 2),
            log_method=LogMethod.CAMERA.value,
            image_url=None,
        )

        return MealScanLogResponse(
            scan=scan_response,
            meal_log=MealLogResponse.model_validate(meal_log),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Voice — meals
    # ──────────────────────────────────────────────────────────────────────────

    def _build_meal_voice_response(self, parsed) -> MealVoiceResponse:
        """Convert MealLogTranscriptionDTO → MealVoiceResponse."""
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

    def voice_meal(self, transcriber, payload: MealVoiceRequest, user) -> MealVoiceResponse:
        """Transcribe + parse meal voice, return matches (no logging)."""
        req = TranscriptionRequestDTO(
            audio_base64=payload.audio_base64,
            audio_format=payload.audio_format,
            language=payload.language,
            context_type=TranscriptionContextType.MEAL_LOG,
        )
        parsed = transcriber.transcribe_and_parse_meal_log(req, db=self.meal_repo.db)
        return self._build_meal_voice_response(parsed)

    def voice_and_log_meal(self, transcriber, payload: MealVoiceLogRequest, user) -> MealVoiceLogResponse:
        """Transcribe + parse meal voice + persist MealLog."""
        req = TranscriptionRequestDTO(
            audio_base64=payload.audio_base64,
            audio_format=payload.audio_format,
            language=payload.language,
            context_type=TranscriptionContextType.MEAL_LOG,
        )
        parsed = transcriber.transcribe_and_parse_meal_log(req, db=self.meal_repo.db)
        voice_resp = self._build_meal_voice_response(parsed)

        if not parsed.parse_successful:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Voice parsing failed: {parsed.notes}",
            )

        meal_type = payload.meal_type or parsed.meal_type or "Snack"
        meal_name = parsed.meal_name or ", ".join(parsed.food_items) or "Voice meal"

        calories = float(parsed.estimated_calories or 0)
        protein_g = float(parsed.estimated_protein_g or 0)
        carbs_g = float(parsed.estimated_carbs_g or 0)
        fats_g = float(parsed.estimated_fats_g or 0)
        serving_size_g_snapshot = None
        serving_description_snapshot = "voice-estimated serving"

        if payload.central_food_id is not None:
            food = self.central_food_repo.get_by_id(payload.central_food_id)
            if not food:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Central food not found.")
            serving_size_g_snapshot = float(food.serving_size_g or 100.0)
            serving_description_snapshot = food.serving_description or f"{serving_size_g_snapshot:g} g"
            grams = serving_size_g_snapshot * payload.servings
            multiplier = grams / 100.0
            calories = (food.calories_per_100g or 0) * multiplier
            protein_g = (food.protein_per_100g or 0) * multiplier
            carbs_g = (food.carbs_per_100g or 0) * multiplier
            fats_g = (food.fats_per_100g or 0) * multiplier

        meal_log = self.meal_repo.create_log(
            user_id=user.id,
            central_food_id=payload.central_food_id,
            log_date=payload.log_date,
            meal_type=meal_type,
            meal_name=meal_name,
            servings=payload.servings,
            serving_size_g_snapshot=serving_size_g_snapshot,
            serving_description_snapshot=serving_description_snapshot,
            calories=round(calories, 2),
            protein_g=round(protein_g, 2),
            carbs_g=round(carbs_g, 2),
            fats_g=round(fats_g, 2),
            log_method=LogMethod.VOICE.value,
            image_url=None,
        )
        return MealVoiceLogResponse(
            voice=voice_resp,
            meal_log=MealLogResponse.model_validate(meal_log),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Voice — workouts
    # ──────────────────────────────────────────────────────────────────────────

    def _build_workout_voice_response(self, parsed) -> WorkoutVoiceResponse:
        """Convert WorkoutLogTranscriptionDTO → WorkoutVoiceResponse."""
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
            exercises.append(
                ParsedExerciseResponse(
                    name=ex.name, sets=ex.sets, reps=ex.reps,
                    weight_str=ex.weight_str, weight_kg=ex.weight_kg,
                    duration_seconds=ex.duration_seconds,
                    matched_exercises=matched,
                )
            )
        return WorkoutVoiceResponse(
            raw_text=parsed.raw_text,
            exercises=exercises,
            duration_mentioned=parsed.duration_mentioned,
            tags=parsed.tags,
            parse_successful=parsed.parse_successful,
            notes=parsed.notes,
        )

    def voice_workout(self, transcriber, payload: WorkoutVoiceRequest, user) -> WorkoutVoiceResponse:
        """Transcribe + parse workout voice, return matches (no logging)."""
        req = TranscriptionRequestDTO(
            audio_base64=payload.audio_base64,
            audio_format=payload.audio_format,
            language=payload.language,
            context_type=TranscriptionContextType.WORKOUT_LOG,
        )
        parsed = transcriber.transcribe_and_parse_workout_log(req, db=self.workout_repo.db)
        return self._build_workout_voice_response(parsed)

    def voice_and_log_workout(self, transcriber, payload: WorkoutVoiceLogRequest, user) -> WorkoutVoiceLogResponse:
        """Transcribe + parse workout voice + persist one WorkoutLog per exercise."""
        req = TranscriptionRequestDTO(
            audio_base64=payload.audio_base64,
            audio_format=payload.audio_format,
            language=payload.language,
            context_type=TranscriptionContextType.WORKOUT_LOG,
        )
        parsed = transcriber.transcribe_and_parse_workout_log(req, db=self.workout_repo.db)
        voice_resp = self._build_workout_voice_response(parsed)

        if not parsed.parse_successful:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Voice parsing failed: {parsed.notes}",
            )
        if not parsed.exercises:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No exercises detected in the voice clip.",
            )

        # Build override lookup: {exercise_index: central_exercise_id}
        overrides: dict = {}
        if payload.exercise_overrides:
            for ov in payload.exercise_overrides:
                overrides[ov.exercise_index] = ov.central_exercise_id

        logged_entries: list = []
        for idx, (ex_resp, ex_parsed) in enumerate(
            zip(voice_resp.exercises, parsed.exercises)
        ):
            # Determine central_exercise_id: override → top vector match → None
            central_exercise_id = overrides.get(idx)
            if central_exercise_id is None and ex_resp.matched_exercises:
                central_exercise_id = ex_resp.matched_exercises[0].id

            weight_kg = ex_parsed.weight_kg
            sets = ex_parsed.sets or 1
            reps = ex_parsed.reps or 1

            workout_log = self.workout_repo.create_log(
                user_id=user.id,
                central_exercise_id=central_exercise_id,
                log_date=payload.log_date,
                sets_completed=sets,
                reps_completed=reps,
                weight_used=weight_kg,
                duration_seconds=ex_parsed.duration_seconds,
                notes=None,
            )
            logged_entries.append(
                LoggedWorkoutEntry(
                    parsed_exercise=ex_resp,
                    workout_log=WorkoutLogResponse.model_validate(workout_log),
                )
            )

        return WorkoutVoiceLogResponse(voice=voice_resp, logged_exercises=logged_entries)
