from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# Shared building blocks
# ──────────────────────────────────────────────────────────────────────────────

class DailyNutritionTargets(BaseModel):
    calories: int
    protein_g: int
    carbs_g: int
    fats_g: int


# ──────────────────────────────────────────────────────────────────────────────
# Next Meal
# ──────────────────────────────────────────────────────────────────────────────

class PlanMealIngredientInfo(BaseModel):
    food_name: str
    amount_g: float


class NextPlanMeal(BaseModel):
    meal_id: int
    meal_type: str
    meal_name: str
    calories: int
    protein_g: float
    carbs_g: float
    fats_g: float
    fiber_g: Optional[float] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    ingredients: List[PlanMealIngredientInfo]


class NextMealResponse(BaseModel):
    has_plan: bool
    plan_name: Optional[str] = None
    today_day_name: Optional[str] = None
    query_time: Optional[str] = None        # HH:MM the recommendation was based on
    daily_targets: Optional[DailyNutritionTargets] = None
    recommended_meal: Optional[NextPlanMeal] = None
    message: str


# ──────────────────────────────────────────────────────────────────────────────
# Next Workout
# ──────────────────────────────────────────────────────────────────────────────

class PlanExerciseInfo(BaseModel):
    slot_id: int
    exercise_id: int
    exercise_name: str
    exercise_type: str
    primary_muscle_group: str
    equipment_required: str
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_kg: Optional[float] = None
    duration_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    instructions: Optional[str] = None
    order_index: int
    already_logged: bool


class NextWorkoutResponse(BaseModel):
    has_plan: bool
    plan_name: Optional[str] = None
    workout_day_name: Optional[str] = None
    focus_area: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None
    exercises: List[PlanExerciseInfo] = []
    sessions_logged_today: int = 0
    message: str


# ──────────────────────────────────────────────────────────────────────────────
# Daily AI Suggestion  (last 24 hours)
# ──────────────────────────────────────────────────────────────────────────────

class DailySnapshot(BaseModel):
    calories_consumed: float
    protein_consumed: float
    carbs_consumed: float
    fats_consumed: float
    calories_target: Optional[int] = None
    protein_target: Optional[int] = None
    calorie_gap: Optional[float] = None         # target - consumed (negative = over)
    protein_gap: Optional[float] = None
    meal_types_logged: List[str] = []
    workout_sessions_logged: int
    weight_logged: bool
    latest_weight_kg: Optional[float] = None


class DailySuggestionResponse(BaseModel):
    period: str = "last_24_hours"
    snapshot: DailySnapshot
    urgency: str                                # "on_track" | "needs_attention" | "off_track"
    suggestion: str                             # AI coaching tip (plain text)
    generated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Progress Report  (feature engineering output)
# ──────────────────────────────────────────────────────────────────────────────

class ExerciseProgression(BaseModel):
    exercise_name: str
    sessions_logged: int
    first_volume: float          # sets × reps × weight of earliest session
    latest_volume: float         # sets × reps × weight of most recent session
    progression_pct: float       # ((latest - first) / first) * 100; 0 if no weight


class NutritionFeatures(BaseModel):
    period_days: int
    days_with_logs: int
    logging_consistency_pct: float              # days_with_logs / period_days * 100
    avg_daily_calories: float
    target_daily_calories: Optional[int] = None
    calorie_adherence_pct: Optional[float] = None   # avg / target * 100
    avg_daily_protein_g: float
    target_daily_protein_g: Optional[int] = None
    protein_adherence_pct: Optional[float] = None
    avg_daily_carbs_g: float
    avg_daily_fats_g: float
    calorie_trend_slope: float                  # kcal/day change over the period (polyfit slope)
    macro_balance_score: float                  # 0-100: how close actual ratio is to target ratio


class WorkoutFeatures(BaseModel):
    period_days: int
    total_sessions: int
    planned_sessions: Optional[int] = None
    frequency_adherence_pct: Optional[float] = None
    avg_sets_per_session: float
    avg_reps_per_session: float
    total_volume_kg: float                      # Σ(sets × reps × weight_used)
    volume_trend_slope: float                   # change in weekly volume (polyfit slope)
    unique_exercises_count: int
    exercise_progressions: List[ExerciseProgression]


class WeightFeatures(BaseModel):
    measurements_count: int
    start_weight_kg: Optional[float] = None
    latest_weight_kg: Optional[float] = None
    weight_change_kg: Optional[float] = None
    weight_trend_slope: Optional[float] = None  # kg/day (polyfit slope)
    trend_direction: str                        # "losing" | "gaining" | "stable" | "no_data"
    goal_weight_kg: Optional[float] = None


class ProgressFeatures(BaseModel):
    """Fully engineered feature vector — derived from raw logs, not raw data."""
    period_label: str                           # "Last 7 Days" | "Last 30 Days" | "Full Plan"
    period_days: int
    period_start: str                           # ISO date string
    period_end: str
    user_goal: str
    overall_consistency_score: float            # weighted composite 0.0–1.0
    on_track: bool                              # rule-based quick flag
    nutrition: NutritionFeatures
    workout: WorkoutFeatures
    weight: WeightFeatures


class ProgressReport(BaseModel):
    features: ProgressFeatures
    assessment: str                             # 1-2 sentence overall verdict
    positives: List[str]                        # what is going well
    improvements: List[str]                     # what needs work
    suggestions: List[str]                      # specific, actionable next steps
    projection: str                             # what happens if this trend continues
    generated_at: datetime
