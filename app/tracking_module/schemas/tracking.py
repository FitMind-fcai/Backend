from datetime import date, datetime
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Log response schemas  (returned after saving)
# ──────────────────────────────────────────────────────────────────────────────

class MealLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    central_food_id: Optional[int]
    log_date: date
    meal_type: str
    meal_name: str
    servings: float
    serving_size_g_snapshot: Optional[float]
    serving_description_snapshot: Optional[str]
    calories: float
    protein_g: float
    carbs_g: float
    fats_g: float
    log_method: str
    image_url: Optional[str]
    created_at: datetime


class WorkoutLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    central_exercise_id: Optional[int]
    workout_day_exercise_id: Optional[int]
    exercise_name: Optional[str] = None
    log_date: date
    sets_completed: int
    reps_completed: int
    weight_used: Optional[float]
    duration_seconds: Optional[int]
    notes: Optional[str]
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _inject_exercise_name(cls, data: Any) -> Any:
        """
        WorkoutLog has no stored exercise-name column (unlike MealLog.meal_name,
        which IS a snapshot column) — it only has central_exercise_id. The name
        is only reachable via the already-eager-loaded `central_exercise`
        relationship (see WorkoutLog.central_exercise, lazy="joined"), so pull
        it in here rather than leaving API consumers with a bare ID.
        """
        if isinstance(data, dict):
            return data
        result = {name: getattr(data, name, None) for name in cls.model_fields if name != "exercise_name"}
        central_exercise = getattr(data, "central_exercise", None)
        result["exercise_name"] = central_exercise.name if central_exercise else None
        return result


class WeightLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    log_date: date
    weight: float
    notes: Optional[str]
    created_at: datetime


class SleepLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    log_date: date
    sleep_hours: float
    sleep_quality: int
    notes: Optional[str]
    created_at: datetime


class HydrationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    log_date: date
    water_ml: float
    notes: Optional[str]
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Update schemas  (PATCH per log type)
# ──────────────────────────────────────────────────────────────────────────────

class MealLogUpdate(BaseModel):
    meal_type: Optional[str] = Field(default=None, min_length=2, max_length=50)
    meal_name: Optional[str] = Field(default=None, max_length=255)
    servings: Optional[float] = Field(default=None, gt=0)
    calories: Optional[float] = Field(default=None, ge=0)
    protein_g: Optional[float] = Field(default=None, ge=0)
    carbs_g: Optional[float] = Field(default=None, ge=0)
    fats_g: Optional[float] = Field(default=None, ge=0)


class WorkoutLogUpdate(BaseModel):
    sets_completed: Optional[int] = Field(default=None, ge=1)
    reps_completed: Optional[int] = Field(default=None, ge=1)
    weight_used: Optional[float] = Field(default=None, ge=0)
    duration_seconds: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class WeightLogUpdate(BaseModel):
    weight: Optional[float] = Field(default=None, gt=0)
    notes: Optional[str] = None


class SleepLogUpdate(BaseModel):
    sleep_hours: Optional[float] = Field(default=None, gt=0, le=24)
    sleep_quality: Optional[int] = Field(default=None, ge=1, le=10)
    notes: Optional[str] = None


class HydrationLogUpdate(BaseModel):
    water_ml: Optional[float] = Field(default=None, gt=0)
    notes: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Daily calorie / macro summary
# ──────────────────────────────────────────────────────────────────────────────

class DailyMacroSummary(BaseModel):
    date: date
    total_calories: float
    total_protein_g: float
    total_carbs_g: float
    total_fats_g: float
    protein_pct: float = Field(description="Percentage of calories from protein")
    carbs_pct: float = Field(description="Percentage of calories from carbs")
    fats_pct: float = Field(description="Percentage of calories from fats")
    meal_count: int


# ──────────────────────────────────────────────────────────────────────────────
# Unified save endpoint schemas
# ──────────────────────────────────────────────────────────────────────────────

class MealLogEntry(BaseModel):
    """One meal item to log. Use central_food_id (from search) for accurate macros."""
    central_food_id: Optional[int] = None
    meal_type: str = Field(..., min_length=2, max_length=50, description="Breakfast | Lunch | Dinner | Snack")
    meal_name: Optional[str] = Field(default=None, max_length=255)
    servings: float = Field(default=1.0, gt=0)
    serving_size_g_snapshot: Optional[float] = Field(default=None, gt=0)
    serving_description_snapshot: Optional[str] = Field(default=None, max_length=100)
    # Fallback macros — ignored when central_food_id is set
    calories: Optional[float] = Field(default=None, ge=0)
    protein_g: Optional[float] = Field(default=None, ge=0)
    carbs_g: Optional[float] = Field(default=None, ge=0)
    fats_g: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_macros(self):
        if self.central_food_id is None:
            missing = [f for f in ["calories", "protein_g", "carbs_g", "fats_g"]
                       if getattr(self, f) is None]
            if missing:
                raise ValueError(
                    "When central_food_id is not provided, the following macro fields are required: "
                    + ", ".join(missing)
                )
        return self


class WorkoutLogEntry(BaseModel):
    """One exercise set to log. Use central_exercise_id (from search) for structured tracking."""
    central_exercise_id: Optional[int] = None
    workout_day_exercise_id: Optional[int] = None
    sets_completed: int = Field(..., ge=1)
    reps_completed: int = Field(..., ge=1)
    weight_used: Optional[float] = Field(default=None, ge=0)
    duration_seconds: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class WeightLogEntry(BaseModel):
    """One body-weight measurement to log."""
    weight: float = Field(..., gt=0, description="Body weight in kilograms")
    notes: Optional[str] = None


class SleepLogEntry(BaseModel):
    """One sleep session to log."""
    sleep_hours: float = Field(..., gt=0, le=24, description="Total hours slept")
    sleep_quality: int = Field(..., ge=1, le=10, description="Sleep quality rating 1–10")
    notes: Optional[str] = None


class HydrationLogEntry(BaseModel):
    """One water intake entry to log."""
    water_ml: float = Field(..., gt=0, description="Water consumed in millilitres")
    notes: Optional[str] = None


class SaveLogsRequest(BaseModel):
    """
    Unified log-save request for all categories.

    Set `category` to `meal`, `workout`, `weight`, `sleep`, or `hydration`
    and populate the matching `*_entries` field.

    **`log_method`:** `TEXT` (default) | `VOICE` | `CAMERA`
    """
    category: Literal["meal", "workout", "weight", "sleep", "hydration"]
    log_date: date
    log_method: str = Field(default="TEXT", description="TEXT | VOICE | CAMERA")
    meal_entries: Optional[List[MealLogEntry]] = None
    workout_entries: Optional[List[WorkoutLogEntry]] = None
    weight_entries: Optional[List[WeightLogEntry]] = None
    sleep_entries: Optional[List[SleepLogEntry]] = None
    hydration_entries: Optional[List[HydrationLogEntry]] = None

    @model_validator(mode="after")
    def check_entries_present(self):
        field = f"{self.category}_entries"
        if not getattr(self, field):
            raise ValueError(
                f"'{field}' is required and cannot be empty when category='{self.category}'."
            )
        return self


class SaveLogsResponse(BaseModel):
    category: str
    saved_count: int
    meal_logs: List[MealLogResponse] = Field(default_factory=list)
    workout_logs: List[WorkoutLogResponse] = Field(default_factory=list)
    weight_logs: List[WeightLogResponse] = Field(default_factory=list)
    sleep_logs: List[SleepLogResponse] = Field(default_factory=list)
    hydration_logs: List[HydrationLogResponse] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Catalog  (manual entries)
# ──────────────────────────────────────────────────────────────────────────────

class ManualFoodCreate(BaseModel):
    food_name: str = Field(..., min_length=2, max_length=255)
    food_category: Optional[str] = Field(default=None, max_length=100)
    serving_size_g: float = Field(..., gt=0)
    serving_description: Optional[str] = Field(default="1 serving", max_length=100)
    calories_per_serving: float = Field(..., ge=0)
    protein_g_per_serving: float = Field(..., ge=0)
    carbs_g_per_serving: float = Field(..., ge=0)
    fats_g_per_serving: float = Field(..., ge=0)
    fiber_g_per_serving: Optional[float] = Field(default=0, ge=0)


class ManualExerciseCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    exercise_type: str = Field(default="Strength", max_length=50)
    primary_muscle_group: str = Field(default="Full Body", max_length=100)
    secondary_muscles: Optional[str] = Field(default=None, max_length=255)
    equipment_required: str = Field(default="Bodyweight", max_length=100)
    difficulty_level: str = Field(default="Beginner", max_length=50)
    location: str = Field(default="Any", max_length=50)
    instructions: Optional[str] = None


class ManualCentralFoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_name: str
    food_category: Optional[str] = None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fats_per_100g: float
    fiber_per_100g: Optional[float] = None
    serving_size_g: Optional[float] = None
    serving_description: Optional[str] = None
    source: str
    is_verified: bool
    is_public: bool


class ManualCentralExerciseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    instructions: Optional[str] = None
    source: str
    is_verified: bool
    is_public: bool


# ──────────────────────────────────────────────────────────────────────────────
# Search result schemas  (returned by search + AI endpoints)
# ──────────────────────────────────────────────────────────────────────────────

class MatchedFoodResponse(BaseModel):
    """
    A food from the central catalog matched by vector similarity.
    Use `id` as `central_food_id` in `SaveLogsRequest.meal_entries`.
    """
    id: int
    food_name: str
    food_name_ar: Optional[str] = None
    food_category: Optional[str] = None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fats_per_100g: float
    fiber_per_100g: Optional[float] = None
    serving_size_g: Optional[float] = None
    serving_description: Optional[str] = None
    similarity_score: float = Field(..., description="Cosine similarity 0–1 (higher = more similar)")


class MatchedExerciseResponse(BaseModel):
    """
    An exercise from the central catalog matched by vector similarity.
    Use `id` as `central_exercise_id` in `SaveLogsRequest.workout_entries`.
    """
    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    similarity_score: float = Field(..., description="Cosine similarity 0–1")


# ──────────────────────────────────────────────────────────────────────────────
# AI · Scanner schemas
# ──────────────────────────────────────────────────────────────────────────────

class ScannedFoodItemResponse(BaseModel):
    name: str
    portion_size: str
    calories: int
    protein_g: float
    carbs_g: float
    fats_g: float
    fiber_g: Optional[float] = None
    confidence: float


class MealScanResponse(BaseModel):
    """
    Image scan result. `matched_foods` contains top-5 catalog suggestions.
    Pick one and pass its `id` as `central_food_id` in `POST /tracking/logs`.
    """
    meal_name: str
    meal_type: str
    food_items: List[ScannedFoodItemResponse]
    total_calories: int
    total_protein_g: float
    total_carbs_g: float
    total_fats_g: float
    tags: List[str]
    health_notes: Optional[str] = None
    confidence_score: float
    matched_foods: List[MatchedFoodResponse]
    allergen_warnings: List[dict] = Field(default_factory=list)
    scan_successful: bool
    error_message: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# AI · Voice schemas
# ──────────────────────────────────────────────────────────────────────────────

class MealVoiceResponse(BaseModel):
    """
    Meal voice transcription result. `matched_foods` contains top-5 catalog suggestions.
    Pick one and pass its `id` as `central_food_id` in `POST /tracking/logs`.
    """
    raw_text: str
    meal_name: Optional[str] = None
    meal_type: Optional[str] = None
    food_items: List[str]
    portions: List[str]
    tags: List[str]
    estimated_calories: Optional[float] = None
    estimated_protein_g: Optional[float] = None
    estimated_carbs_g: Optional[float] = None
    estimated_fats_g: Optional[float] = None
    matched_foods: List[MatchedFoodResponse]
    parse_successful: bool
    notes: Optional[str] = None


class ParsedExerciseResponse(BaseModel):
    """One exercise parsed from a workout voice clip."""
    name: str
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_str: Optional[str] = None
    weight_kg: Optional[float] = None
    duration_seconds: Optional[int] = None
    matched_exercises: List[MatchedExerciseResponse]


class WorkoutVoiceResponse(BaseModel):
    """
    Workout voice transcription result. Each exercise in `exercises` contains
    `matched_exercises` — top-5 catalog suggestions.
    Pick `id` values and pass them as `central_exercise_id` in `POST /tracking/logs`
    (one request per exercise, or batch them all in one request's `workout_entries`).
    """
    raw_text: str
    exercises: List[ParsedExerciseResponse]
    duration_mentioned: Optional[str] = None
    tags: List[str]
    parse_successful: bool
    notes: Optional[str] = None


class WeightVoiceResponse(BaseModel):
    """
    Weight voice transcription result.
    Pass `extracted_weight_kg` directly to `POST /tracking/logs` as the `weight` field.
    """
    raw_text: str
    extracted_weight_kg: Optional[float] = None
    notes: Optional[str] = None
    parse_successful: bool
