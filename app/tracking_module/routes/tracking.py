from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.auth_module.core.dependencies import get_current_verified_user
from app.auth_module.models.user import User
from app.tracking_module.core.dependencies import (
    get_tracking_service,
    get_meal_scanner_service_dep,
    get_voice_transcriber_service_dep,
)
from app.tracking_module.schemas.tracking import (
    WorkoutLogCreateText,
    WorkoutLogResponse,
    MealLogCreateText,
    MealLogResponse,
    WeightLogCreateText,
    WeightLogResponse,
    FoodSearchResult,
    ExerciseSearchResult,
    ManualFoodCreate,
    ManualExerciseCreate,
    ManualCentralFoodResponse,
    ManualCentralExerciseResponse,
    MealScanRequest,
    MealScanResponse,
    MealScanLogRequest,
    MealScanLogResponse,
    MealVoiceRequest,
    MealVoiceResponse,
    MealVoiceLogRequest,
    MealVoiceLogResponse,
    WorkoutVoiceRequest,
    WorkoutVoiceResponse,
    WorkoutVoiceLogRequest,
    WorkoutVoiceLogResponse,
)
from app.tracking_module.services.tracking_service import TrackingService
from app.ai_services.meal_scanner.meal_scanner_service import MealScannerService
from app.ai_services.voice_transcriber.voice_transcriber_service import VoiceTranscriberService


tracking_router = APIRouter(prefix="/tracking", tags=["Tracking"])


@tracking_router.get("/foods/search", response_model=List[FoodSearchResult], summary="Search foods with serving nutrition")
def search_foods(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_foods(user_id=current_user.id, query=q, limit=limit)


@tracking_router.get("/exercises/search", response_model=List[ExerciseSearchResult], summary="Search exercises with details")
def search_exercises(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_exercises(user_id=current_user.id, query=q, limit=limit)


@tracking_router.post(
    "/foods/manual",
    response_model=ManualCentralFoodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual food in central catalog",
)
def create_manual_food(
    payload: ManualFoodCreate,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_manual_food(user_id=current_user.id, payload=payload)


@tracking_router.post(
    "/exercises/manual",
    response_model=ManualCentralExerciseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual exercise in central catalog",
)
def create_manual_exercise(
    payload: ManualExerciseCreate,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_manual_exercise(user_id=current_user.id, payload=payload)


@tracking_router.post(
    "/workouts/text",
    response_model=WorkoutLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workout log (text flow)",
)
def create_workout_log_text(
    payload: WorkoutLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_workout_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/workouts", response_model=List[WorkoutLogResponse], summary="List workout logs")
def list_workout_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
):
    return tracking_service.list_workout_logs(user_id=current_user.id, skip=skip, limit=limit, log_date=log_date)


@tracking_router.get("/workouts/{log_id}", response_model=WorkoutLogResponse, summary="Get workout log")
def get_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_workout_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/workouts/{log_id}", summary="Delete workout log")
def delete_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_workout_log(user_id=current_user.id, log_id=log_id)


@tracking_router.post(
    "/meals/text",
    response_model=MealLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create meal log (text flow)",
)
def create_meal_log_text(
    payload: MealLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_meal_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/meals", response_model=List[MealLogResponse], summary="List meal logs")
def list_meal_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
    meal_type: Optional[str] = Query(default=None),
):
    return tracking_service.list_meal_logs(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        log_date=log_date,
        meal_type=meal_type,
    )


@tracking_router.get("/meals/{log_id}", response_model=MealLogResponse, summary="Get meal log")
def get_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_meal_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/meals/{log_id}", summary="Delete meal log")
def delete_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_meal_log(user_id=current_user.id, log_id=log_id)


@tracking_router.post(
    "/weights/text",
    response_model=WeightLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create weight log (text flow)",
)
def create_weight_log_text(
    payload: WeightLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_weight_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/weights", response_model=List[WeightLogResponse], summary="List weight logs")
def list_weight_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
):
    return tracking_service.list_weight_logs(user_id=current_user.id, skip=skip, limit=limit, log_date=log_date)


@tracking_router.get("/weights/{log_id}", response_model=WeightLogResponse, summary="Get weight log")
def get_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_weight_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/weights/{log_id}", summary="Delete weight log")
def delete_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_weight_log(user_id=current_user.id, log_id=log_id)


# ──────────────────────────────────────────────────────────────────────────────
# Meal Scanner endpoints
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/scan",
    response_model=MealScanResponse,
    summary="Scan a meal photo with Qwen2.5-VL — returns nutrition + top-5 vector-matched foods",
)
def scan_meal(
    payload: MealScanRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    scanner: MealScannerService = Depends(get_meal_scanner_service_dep),
):
    """
    Analyse a base64-encoded meal photo using Qwen2.5-VL and return:

    * Full nutritional breakdown (calories, macros, per-item details)
    * Semantic tags extracted by the VL model
    * Up to 5 best-matching foods from the central food catalog via pgvector
      cosine similarity (use their `id` in the `/meals/scan/log` call)
    """
    return tracking_service.scan_meal(
        scanner=scanner,
        request_payload=payload,
        user=current_user,
    )


@tracking_router.post(
    "/meals/scan/log",
    response_model=MealScanLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Scan a meal photo and immediately save it as a meal log",
)
def scan_and_log_meal(
    payload: MealScanLogRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    scanner: MealScannerService = Depends(get_meal_scanner_service_dep),
):
    """
    One-shot endpoint: analyse the photo *and* create a MealLog in a single call.

    * If `central_food_id` is provided, macros are recalculated from that food × servings.
    * Otherwise the AI-estimated totals are stored directly.
    * `log_method` is always set to **CAMERA**.
    """
    return tracking_service.scan_and_log_meal(
        scanner=scanner,
        payload=payload,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Voice Meal endpoints
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/voice",
    response_model=MealVoiceResponse,
    summary="Transcribe a meal voice clip — returns parsed nutrition + top-5 matched foods",
)
def voice_meal(
    payload: MealVoiceRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    """
    Whisper transcribes the audio → LLaMA extracts meal name, food items, portions,
    estimated macros, and semantic tags → pgvector returns top-5 matching central_foods.

    Use the matched `id` values in `/meals/voice/log` to associate a catalogued food.
    """
    return tracking_service.voice_meal(
        transcriber=transcriber,
        payload=payload,
        user=current_user,
    )


@tracking_router.post(
    "/meals/voice/log",
    response_model=MealVoiceLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcribe a meal voice clip and immediately save it as a meal log",
)
def voice_and_log_meal(
    payload: MealVoiceLogRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    """
    One-shot: transcribe → parse → log.

    * If `central_food_id` is supplied, macros come from that food × servings.
    * Otherwise the LLM-estimated macros are saved directly.
    * `log_method` is always **VOICE**.
    """
    return tracking_service.voice_and_log_meal(
        transcriber=transcriber,
        payload=payload,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Voice Workout endpoints
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/workouts/voice",
    response_model=WorkoutVoiceResponse,
    summary="Transcribe a workout voice clip — returns parsed exercises + per-exercise top-5 matches",
)
def voice_workout(
    payload: WorkoutVoiceRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    """
    Whisper transcribes → LLaMA extracts each exercise with sets/reps/weight → pgvector
    returns top-5 matching central_exercises per exercise.

    Pass `exercise_overrides` in `/workouts/voice/log` to confirm which exercise IDs to log.
    """
    return tracking_service.voice_workout(
        transcriber=transcriber,
        payload=payload,
        user=current_user,
    )


@tracking_router.post(
    "/workouts/voice/log",
    response_model=WorkoutVoiceLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcribe a workout voice clip and log every detected exercise",
)
def voice_and_log_workout(
    payload: WorkoutVoiceLogRequest,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    """
    One WorkoutLog row is created per detected exercise.

    * `exercise_overrides` lets the user pin which `central_exercise_id` to attach to each
      exercise (by index). If omitted, the top vector-similarity match is used.
    * `log_method` is always **VOICE**.
    """
    return tracking_service.voice_and_log_workout(
        transcriber=transcriber,
        payload=payload,
        user=current_user,
    )
