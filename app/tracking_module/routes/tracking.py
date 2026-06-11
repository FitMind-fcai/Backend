from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

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
    MealScanResponse,
    MealVoiceResponse,
    WorkoutVoiceResponse,
    MatchedFoodResponse,
    MatchedExerciseResponse,
)
from app.tracking_module.services.tracking_service import TrackingService
from app.ai_services.meal_scanner.meal_scanner_service import MealScannerService
from app.ai_services.voice_transcriber.voice_transcriber_service import VoiceTranscriberService


tracking_router = APIRouter(prefix="/tracking")

# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.get(
    "/foods/search",
    response_model=List[FoodSearchResult],
    tags=["Search"],
    summary="Text search — foods",
    description=(
        "Full-text search across the central food catalog. "
        "Returns per-serving macro breakdowns. "
        "Use the returned `id` as `central_food_id` when saving a meal log via `POST /tracking/meals`. "
        "For semantic / AI-powered search use `/foods/search/vector`."
    ),
)
def search_foods(
    q: str = Query(..., min_length=2, description="Search keyword (e.g. 'chicken breast')"),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_foods(user_id=current_user.id, query=q, limit=limit)


@tracking_router.get(
    "/foods/search/vector",
    response_model=List[MatchedFoodResponse],
    tags=["Search"],
    summary="Semantic search — foods (pgvector)",
    description=(
        "Semantic similarity search using pgvector embeddings (BAAI/bge-small-en-v1.5). "
        "Works best with natural-language queries like 'grilled fish with lemon'. "
        "Use the returned `id` as `central_food_id` when saving via `POST /tracking/meals`."
    ),
)
def search_foods_vector(
    q: str = Query(..., min_length=2, description="Natural-language query"),
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_foods_vector(query=q, limit=limit)


@tracking_router.get(
    "/exercises/search",
    response_model=List[ExerciseSearchResult],
    tags=["Search"],
    summary="Text search — exercises",
    description=(
        "Full-text search across the central exercise catalog. "
        "Use the returned `id` as `central_exercise_id` when saving a workout log via `POST /tracking/workouts`."
    ),
)
def search_exercises(
    q: str = Query(..., min_length=2, description="Search keyword (e.g. 'bench press')"),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_exercises(user_id=current_user.id, query=q, limit=limit)


@tracking_router.get(
    "/exercises/search/vector",
    response_model=List[MatchedExerciseResponse],
    tags=["Search"],
    summary="Semantic search — exercises (pgvector)",
    description=(
        "Semantic similarity search against the central exercise catalog. "
        "Use the returned `id` as `central_exercise_id` when saving via `POST /tracking/workouts`."
    ),
)
def search_exercises_vector(
    q: str = Query(..., min_length=2, description="Natural-language query (e.g. 'chest push barbell')"),
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_exercises_vector(query=q, limit=limit)


# ──────────────────────────────────────────────────────────────────────────────
# Catalog — manual entries
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/foods/manual",
    response_model=ManualCentralFoodResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Catalog"],
    summary="Add a custom food to the catalog",
    description=(
        "Creates a food entry in the central catalog attributed to the current user. "
        "Macros are stored per 100 g and auto-calculated from the provided per-serving values."
    ),
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
    tags=["Catalog"],
    summary="Add a custom exercise to the catalog",
    description="Creates an exercise entry in the central catalog attributed to the current user.",
)
def create_manual_exercise(
    payload: ManualExerciseCreate,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_manual_exercise(user_id=current_user.id, payload=payload)


# ──────────────────────────────────────────────────────────────────────────────
# AI · Meal Scanner  (suggest step)
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/scan",
    response_model=MealScanResponse,
    tags=["AI · Meal Scanner"],
    summary="Scan a meal photo — get nutrition estimate and catalog suggestions",
    description=(
        "Upload a meal photo. Qwen2.5-VL returns per-item calorie/macro estimates and semantic tags. "
        "pgvector then returns the top-5 most similar foods from the central catalog in `matched_foods`.\n\n"
        "**Next step:** pick a food from `matched_foods` (or use the estimated totals directly) "
        "and call `POST /tracking/meals` with `log_method=CAMERA` to save the log.\n\n"
        "Supported image formats: `jpeg`, `png`, `webp`. Accepts `multipart/form-data`."
    ),
)
async def scan_meal(
    file: UploadFile = File(..., description="Meal photo (jpeg / png / webp)"),
    image_format: str = Form(default="jpeg", description="jpeg | png | webp"),
    meal_type: Optional[str] = Form(default=None, description="Hint: Breakfast / Lunch / Dinner / Snack"),
    language: str = Form(default="en", description="Response language — `en` or `ar`"),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    scanner: MealScannerService = Depends(get_meal_scanner_service_dep),
):
    image_bytes = await file.read()
    return tracking_service.scan_meal(
        scanner=scanner,
        image_bytes=image_bytes,
        image_format=image_format,
        meal_type=meal_type,
        language=language,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# AI · Voice  (suggest step)
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/voice",
    response_model=MealVoiceResponse,
    tags=["AI · Voice"],
    summary="Transcribe a meal voice clip — get parsed data and catalog suggestions",
    description=(
        "Upload a voice recording describing a meal.\n\n"
        "**Pipeline:**\n"
        "1. Whisper (Groq) transcribes the audio\n"
        "2. LLM extracts meal name, food items, portions, estimated macros, and semantic tags\n"
        "3. pgvector returns top-5 best-matching foods from the catalog in `matched_foods`\n\n"
        "**Next step:** pick a food from `matched_foods` and call `POST /tracking/meals` "
        "with `log_method=VOICE` to save the log.\n\n"
        "Supported audio: `mp3`, `wav`, `m4a`, `webm`, `ogg`, `flac`. Accepts `multipart/form-data`."
    ),
)
async def voice_meal(
    file: UploadFile = File(..., description="Audio recording of a meal description"),
    audio_format: str = Form(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac"),
    language: Optional[str] = Form(default=None, description="Language code — auto-detected if omitted"),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    audio_bytes = await file.read()
    return tracking_service.voice_meal(
        transcriber=transcriber,
        audio_bytes=audio_bytes,
        audio_format=audio_format,
        language=language,
        user=current_user,
    )


@tracking_router.post(
    "/workouts/voice",
    response_model=WorkoutVoiceResponse,
    tags=["AI · Voice"],
    summary="Transcribe a workout voice clip — get parsed exercises and catalog suggestions",
    description=(
        "Upload a voice recording describing a workout.\n\n"
        "**Pipeline:**\n"
        "1. Whisper (Groq) transcribes the audio\n"
        "2. LLM extracts each exercise with sets, reps, and weight\n"
        "3. pgvector returns top-5 best-matching exercises per detected exercise in `matched_exercises`\n\n"
        "**Next step:** for each exercise, pick from `matched_exercises` and call "
        "`POST /tracking/workouts` with `log_method=VOICE` once per exercise to save.\n\n"
        "Accepts `multipart/form-data`."
    ),
)
async def voice_workout(
    file: UploadFile = File(..., description="Audio recording of a workout description"),
    audio_format: str = Form(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac"),
    language: Optional[str] = Form(default=None, description="Language code — auto-detected if omitted"),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    audio_bytes = await file.read()
    return tracking_service.voice_workout(
        transcriber=transcriber,
        audio_bytes=audio_bytes,
        audio_format=audio_format,
        language=language,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Meal Logs  (save step — shared by TEXT / CAMERA / VOICE)
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals",
    response_model=MealLogResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Meal Logs"],
    summary="Save a meal log",
    description=(
        "Persist a meal log regardless of how the meal was identified (text search, camera scan, or voice).\n\n"
        "**`log_method` values:** `TEXT` (default) | `CAMERA` | `VOICE`\n\n"
        "**Macro source precedence:**\n"
        "1. If `central_food_id` is provided → macros are calculated from the catalog entry × `servings`.\n"
        "2. Otherwise → the manually supplied calorie/macro fields are stored as-is.\n\n"
        "Typical flows:\n"
        "- **Text:** search `GET /foods/search` → pick `id` → POST here with `log_method=TEXT`\n"
        "- **Camera:** scan `POST /meals/scan` → pick from `matched_foods[].id` → POST here with `log_method=CAMERA`\n"
        "- **Voice:** transcribe `POST /meals/voice` → pick from `matched_foods[].id` → POST here with `log_method=VOICE`"
    ),
)
def create_meal_log(
    payload: MealLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_meal_log(user_id=current_user.id, payload=payload)


@tracking_router.get(
    "/meals",
    response_model=List[MealLogResponse],
    tags=["Meal Logs"],
    summary="List meal logs",
    description=(
        "Returns the authenticated user's meal logs, newest first. "
        "Filter by `log_date` (ISO date) or `meal_type` (Breakfast / Lunch / Dinner / Snack)."
    ),
)
def list_meal_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
    meal_type: Optional[str] = Query(default=None, description="Filter by meal type"),
):
    return tracking_service.list_meal_logs(
        user_id=current_user.id, skip=skip, limit=limit,
        log_date=log_date, meal_type=meal_type,
    )


@tracking_router.get(
    "/meals/{log_id}",
    response_model=MealLogResponse,
    tags=["Meal Logs"],
    summary="Get a meal log",
    description="Retrieve a single meal log by its ID. Returns 404 if it does not belong to the current user.",
)
def get_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_meal_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete(
    "/meals/{log_id}",
    tags=["Meal Logs"],
    summary="Delete a meal log",
    description="Permanently delete a meal log. Returns 404 if it does not belong to the current user.",
)
def delete_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_meal_log(user_id=current_user.id, log_id=log_id)


# ──────────────────────────────────────────────────────────────────────────────
# Workout Logs  (save step — shared by TEXT / VOICE)
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/workouts",
    response_model=WorkoutLogResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Workout Logs"],
    summary="Save a workout log",
    description=(
        "Persist a single exercise set regardless of how it was identified.\n\n"
        "**`log_method` values:** `TEXT` (default) | `VOICE`\n\n"
        "Typical flows:\n"
        "- **Text:** search `GET /exercises/search` → pick `id` → POST here with `log_method=TEXT`\n"
        "- **Voice:** transcribe `POST /workouts/voice` → pick from `exercises[i].matched_exercises[].id` "
        "→ POST here once per exercise with `log_method=VOICE`"
    ),
)
def create_workout_log(
    payload: WorkoutLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_workout_log(user_id=current_user.id, payload=payload)


@tracking_router.get(
    "/workouts",
    response_model=List[WorkoutLogResponse],
    tags=["Workout Logs"],
    summary="List workout logs",
    description="Returns the authenticated user's workout logs, newest first. Filter by `log_date`.",
)
def list_workout_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
):
    return tracking_service.list_workout_logs(
        user_id=current_user.id, skip=skip, limit=limit, log_date=log_date,
    )


@tracking_router.get(
    "/workouts/{log_id}",
    response_model=WorkoutLogResponse,
    tags=["Workout Logs"],
    summary="Get a workout log",
    description="Retrieve a single workout log by its ID. Returns 404 if it does not belong to the current user.",
)
def get_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_workout_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete(
    "/workouts/{log_id}",
    tags=["Workout Logs"],
    summary="Delete a workout log",
    description="Permanently delete a workout log. Returns 404 if it does not belong to the current user.",
)
def delete_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_workout_log(user_id=current_user.id, log_id=log_id)


# ──────────────────────────────────────────────────────────────────────────────
# Weight Logs
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/weights",
    response_model=WeightLogResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Weight Logs"],
    summary="Log a body weight entry",
    description="Record a body weight measurement in kilograms for a given date.",
)
def create_weight_log(
    payload: WeightLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_weight_log(user_id=current_user.id, payload=payload)


@tracking_router.get(
    "/weights",
    response_model=List[WeightLogResponse],
    tags=["Weight Logs"],
    summary="List weight logs",
    description="Returns the authenticated user's weight log entries, newest first.",
)
def list_weight_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
):
    return tracking_service.list_weight_logs(
        user_id=current_user.id, skip=skip, limit=limit, log_date=log_date,
    )


@tracking_router.get(
    "/weights/{log_id}",
    response_model=WeightLogResponse,
    tags=["Weight Logs"],
    summary="Get a weight log",
    description="Retrieve a single weight log entry by its ID.",
)
def get_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_weight_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete(
    "/weights/{log_id}",
    tags=["Weight Logs"],
    summary="Delete a weight log",
    description="Permanently delete a weight log entry.",
)
def delete_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_weight_log(user_id=current_user.id, log_id=log_id)
