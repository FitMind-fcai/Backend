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
    MealLogResponse,
    WorkoutLogResponse,
    WeightLogResponse,
    SleepLogResponse,
    HydrationLogResponse,
    SaveLogsRequest,
    SaveLogsResponse,
    ManualFoodCreate,
    ManualExerciseCreate,
    ManualCentralFoodResponse,
    ManualCentralExerciseResponse,
    MealScanResponse,
    MealVoiceResponse,
    WorkoutVoiceResponse,
    WeightVoiceResponse,
    MatchedFoodResponse,
    MatchedExerciseResponse,
    MealLogUpdate,
    WorkoutLogUpdate,
    WeightLogUpdate,
    SleepLogUpdate,
    HydrationLogUpdate,
    DailyMacroSummary,
)
from app.tracking_module.services.tracking_service import TrackingService
from app.ai_services.meal_scanner.meal_scanner_service import MealScannerService
from app.ai_services.voice_transcriber.voice_transcriber_service import VoiceTranscriberService


tracking_router = APIRouter(prefix="/tracking")


# ──────────────────────────────────────────────────────────────────────────────
# Search  ·  text → vector search → top catalog matches
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.get(
    "/meals/search",
    response_model=List[MatchedFoodResponse],
    tags=["Search"],
    summary="Search foods by text",
    description=(
        "Enter a free-text description of a food and get back the top catalog matches "
        "ranked by semantic (vector) similarity.\n\n"
        "Pick a result and pass its `id` as `central_food_id` when saving via `POST /tracking/logs`."
    ),
)
def search_meals(
    q: str = Query(..., min_length=2, description="e.g. 'grilled chicken with rice'"),
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.search_foods(query=q, limit=limit)


@tracking_router.get(
    "/workouts/search",
    response_model=List[MatchedExerciseResponse],
    tags=["Search"],
    summary="Search exercises by text",
    description=(
        "Enter a free-text description of an exercise and get back the top catalog matches "
        "ranked by semantic (vector) similarity.\n\n"
        "Pick a result and pass its `id` as `central_exercise_id` when saving via `POST /tracking/logs`."
    ),
)
def search_workouts(
    q: str = Query(..., min_length=2, description="e.g. 'chest push with barbell'"),
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.search_exercises(query=q, limit=limit)


# ──────────────────────────────────────────────────────────────────────────────
# AI · Scanner  ·  image → LLM tags → vector search → top catalog matches
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/scan",
    response_model=MealScanResponse,
    tags=["AI · Scanner"],
    summary="Scan a meal photo",
    description=(
        "Upload a meal photo. Qwen2.5-VL analyses it and extracts semantic tags, "
        "then pgvector returns the top-5 most similar foods from the catalog in `matched_foods`.\n\n"
        "**Next step:** pick a food from `matched_foods`, note its `id`, and call "
        "`POST /tracking/logs` with `category=meal` and `log_method=CAMERA` to save.\n\n"
        "Accepted image formats: `jpeg`, `png`, `webp`. Accepts `multipart/form-data`."
    ),
)
async def scan_meal(
    file: UploadFile = File(..., description="Meal photo (jpeg / png / webp)"),
    image_format: str = Form(default="jpeg", description="jpeg | png | webp"),
    meal_type: Optional[str] = Form(default=None, description="Hint: Breakfast / Lunch / Dinner / Snack"),
    language: str = Form(default="en", description="Response language — `en` or `ar`"),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
    scanner: MealScannerService = Depends(get_meal_scanner_service_dep),
):
    return service.scan_meal(
        scanner=scanner,
        image_bytes=await file.read(),
        image_format=image_format,
        meal_type=meal_type,
        language=language,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# AI · Voice  ·  audio → LLM parse → vector search → top catalog matches
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/meals/voice",
    response_model=MealVoiceResponse,
    tags=["AI · Voice"],
    summary="Identify a meal from voice",
    description=(
        "Upload a voice recording describing what you ate. The pipeline:\n"
        "1. **Whisper** transcribes the audio\n"
        "2. **LLM** extracts food items, portions, estimated macros, and semantic tags\n"
        "3. **pgvector** returns top-5 catalog matches in `matched_foods`\n\n"
        "**Next step:** pick a food from `matched_foods` and call `POST /tracking/logs` "
        "with `category=meal` and `log_method=VOICE` to save.\n\n"
        "Accepted audio: `mp3`, `wav`, `m4a`, `webm`, `ogg`, `flac`."
    ),
)
async def voice_meal(
    file: UploadFile = File(..., description="Audio recording of a meal description"),
    audio_format: str = Form(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac"),
    language: Optional[str] = Form(default=None, description="Language code — auto-detected if omitted"),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    return service.voice_meal(
        transcriber=transcriber,
        audio_bytes=await file.read(),
        audio_format=audio_format,
        language=language,
        user=current_user,
    )


@tracking_router.post(
    "/workouts/voice",
    response_model=WorkoutVoiceResponse,
    tags=["AI · Voice"],
    summary="Identify exercises from voice",
    description=(
        "Upload a voice recording describing your workout. The pipeline:\n"
        "1. **Whisper** transcribes the audio\n"
        "2. **LLM** extracts each exercise with sets, reps, and weight\n"
        "3. **pgvector** returns top-5 catalog matches per exercise in `matched_exercises`\n\n"
        "**Next step:** for each exercise pick from `matched_exercises` and call "
        "`POST /tracking/logs` with `category=workout` and `log_method=VOICE`. "
        "You can batch all exercises in one request's `workout_entries`.\n\n"
        "Accepted audio: `mp3`, `wav`, `m4a`, `webm`, `ogg`, `flac`."
    ),
)
async def voice_workout(
    file: UploadFile = File(..., description="Audio recording of a workout description"),
    audio_format: str = Form(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac"),
    language: Optional[str] = Form(default=None, description="Language code — auto-detected if omitted"),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    return service.voice_workout(
        transcriber=transcriber,
        audio_bytes=await file.read(),
        audio_format=audio_format,
        language=language,
        user=current_user,
    )


@tracking_router.post(
    "/weights/voice",
    response_model=WeightVoiceResponse,
    tags=["AI · Voice"],
    summary="Extract body weight from voice",
    description=(
        "Upload a voice recording saying your body weight (e.g. 'I weigh 75 kilos'). "
        "Whisper transcribes it and the LLM extracts the numeric value, auto-converting "
        "lbs → kg when needed.\n\n"
        "**Next step:** pass `extracted_weight_kg` as `weight` in `POST /tracking/logs` "
        "with `category=weight`."
    ),
)
async def voice_weight(
    file: UploadFile = File(..., description="Audio recording stating body weight"),
    audio_format: str = Form(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac"),
    language: Optional[str] = Form(default=None, description="Language code — auto-detected if omitted"),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
    transcriber: VoiceTranscriberService = Depends(get_voice_transcriber_service_dep),
):
    return service.voice_weight(
        transcriber=transcriber,
        audio_bytes=await file.read(),
        audio_format=audio_format,
        language=language,
        user=current_user,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Logs  ·  save
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/logs",
    response_model=SaveLogsResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Logs"],
    summary="Save log entries",
    description=(
        "Single endpoint for saving any type of log. Set `category` and fill the matching "
        "entries field. Multiple entries are saved in one call.\n\n"
        "**`category`** → **required entries field**\n"
        "- `meal` → `meal_entries` — each entry needs `meal_type`; use `central_food_id` "
        "(from search / scan / voice) for accurate macros, or supply raw calorie/macro values\n"
        "- `workout` → `workout_entries` — each entry needs `sets_completed` and `reps_completed`; "
        "use `central_exercise_id` (from search / voice) for structured tracking\n"
        "- `weight` → `weight_entries` — each entry needs `weight` (kg)\n\n"
        "**`log_method`:** `TEXT` | `VOICE` | `CAMERA` (default `TEXT`)\n\n"
        "**Example — save one meal:**\n"
        "```json\n"
        "{\n"
        '  "category": "meal",\n'
        '  "log_date": "2024-01-15",\n'
        '  "log_method": "CAMERA",\n'
        '  "meal_entries": [\n'
        '    {"central_food_id": 123, "meal_type": "Lunch", "servings": 1.0}\n'
        "  ]\n"
        "}\n"
        "```"
    ),
)
def save_logs(
    payload: SaveLogsRequest,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.save_logs(user_id=current_user.id, request=payload)


# ──────────────────────────────────────────────────────────────────────────────
# Logs  ·  get by date
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.get(
    "/logs/meals",
    response_model=List[MealLogResponse],
    tags=["Logs"],
    summary="Get meal logs",
    description=(
        "Returns the current user's meal logs, newest first. "
        "Pass `date` (YYYY-MM-DD) to filter by a specific day."
    ),
)
def get_meal_logs(
    log_date: Optional[date] = Query(default=None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.get_meal_logs(user_id=current_user.id, log_date=log_date, limit=limit)


@tracking_router.get(
    "/logs/workouts",
    response_model=List[WorkoutLogResponse],
    tags=["Logs"],
    summary="Get workout logs",
    description=(
        "Returns the current user's workout logs, newest first. "
        "Pass `date` (YYYY-MM-DD) to filter by a specific day."
    ),
)
def get_workout_logs(
    log_date: Optional[date] = Query(default=None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.get_workout_logs(user_id=current_user.id, log_date=log_date, limit=limit)


@tracking_router.get(
    "/logs/weights",
    response_model=List[WeightLogResponse],
    tags=["Logs"],
    summary="Get weight logs",
    description=(
        "Returns the current user's weight log entries, newest first. "
        "Pass `date` (YYYY-MM-DD) to filter by a specific day."
    ),
)
def get_weight_logs(
    log_date: Optional[date] = Query(default=None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.get_weight_logs(user_id=current_user.id, log_date=log_date, limit=limit)


@tracking_router.get(
    "/logs/sleep",
    response_model=List[SleepLogResponse],
    tags=["Logs"],
    summary="Get sleep logs",
    description=(
        "Returns the current user's sleep logs, newest first. "
        "Pass `date` (YYYY-MM-DD) to filter by a specific day."
    ),
)
def get_sleep_logs(
    log_date: Optional[date] = Query(default=None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.get_sleep_logs(user_id=current_user.id, log_date=log_date, limit=limit)


@tracking_router.get(
    "/logs/hydration",
    response_model=List[HydrationLogResponse],
    tags=["Logs"],
    summary="Get hydration logs",
    description=(
        "Returns the current user's water intake logs, newest first. "
        "Pass `date` (YYYY-MM-DD) to filter by a specific day."
    ),
)
def get_hydration_logs(
    log_date: Optional[date] = Query(default=None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.get_hydration_logs(user_id=current_user.id, log_date=log_date, limit=limit)


# ──────────────────────────────────────────────────────────────────────────────
# Logs  ·  daily macro summary
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.get(
    "/logs/meals/summary",
    response_model=DailyMacroSummary,
    tags=["Logs"],
    summary="Daily calorie & macro breakdown",
    description=(
        "Returns total calories, protein, carbs, fats and their percentage breakdown "
        "for a given day. Defaults to today if no date is passed."
    ),
)
def get_daily_macro_summary(
    log_date: Optional[date] = Query(default=None, alias="date", description="Date (YYYY-MM-DD), defaults to today"),
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    target_date = log_date or date.today()
    return service.get_daily_macro_summary(user_id=current_user.id, log_date=target_date)


# ──────────────────────────────────────────────────────────────────────────────
# Logs  ·  update
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.patch(
    "/logs/meals/{log_id}",
    response_model=MealLogResponse,
    tags=["Logs"],
    summary="Update a meal log",
)
def update_meal_log(
    log_id: int,
    payload: MealLogUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.update_meal_log(log_id=log_id, user_id=current_user.id, data=payload)


@tracking_router.patch(
    "/logs/workouts/{log_id}",
    response_model=WorkoutLogResponse,
    tags=["Logs"],
    summary="Update a workout log",
)
def update_workout_log(
    log_id: int,
    payload: WorkoutLogUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.update_workout_log(log_id=log_id, user_id=current_user.id, data=payload)


@tracking_router.patch(
    "/logs/weights/{log_id}",
    response_model=WeightLogResponse,
    tags=["Logs"],
    summary="Update a weight log",
)
def update_weight_log(
    log_id: int,
    payload: WeightLogUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.update_weight_log(log_id=log_id, user_id=current_user.id, data=payload)


@tracking_router.patch(
    "/logs/sleep/{log_id}",
    response_model=SleepLogResponse,
    tags=["Logs"],
    summary="Update a sleep log",
)
def update_sleep_log(
    log_id: int,
    payload: SleepLogUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.update_sleep_log(log_id=log_id, user_id=current_user.id, data=payload)


@tracking_router.patch(
    "/logs/hydration/{log_id}",
    response_model=HydrationLogResponse,
    tags=["Logs"],
    summary="Update a hydration log",
)
def update_hydration_log(
    log_id: int,
    payload: HydrationLogUpdate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.update_hydration_log(log_id=log_id, user_id=current_user.id, data=payload)


# ──────────────────────────────────────────────────────────────────────────────
# Logs  ·  delete
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.delete(
    "/logs/{category}/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Logs"],
    summary="Delete a log entry",
    description="Delete a log by category (`meal`, `workout`, `weight`, `sleep`, `hydration`) and ID.",
)
def delete_log(
    category: str,
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    service.delete_log(category=category, log_id=log_id, user_id=current_user.id)


# ──────────────────────────────────────────────────────────────────────────────
# Catalog  ·  manual food / exercise entries
# ──────────────────────────────────────────────────────────────────────────────

@tracking_router.post(
    "/foods/manual",
    response_model=ManualCentralFoodResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Catalog"],
    summary="Add a custom food",
    description=(
        "Create a food entry in the central catalog. "
        "Macros are stored per 100 g and auto-calculated from the provided per-serving values. "
        "Once added the food appears in search results."
    ),
)
def create_manual_food(
    payload: ManualFoodCreate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.create_manual_food(user_id=current_user.id, payload=payload)


@tracking_router.post(
    "/exercises/manual",
    response_model=ManualCentralExerciseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Catalog"],
    summary="Add a custom exercise",
    description=(
        "Create an exercise entry in the central catalog. "
        "Once added the exercise appears in search results."
    ),
)
def create_manual_exercise(
    payload: ManualExerciseCreate,
    current_user: User = Depends(get_current_verified_user),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.create_manual_exercise(user_id=current_user.id, payload=payload)
