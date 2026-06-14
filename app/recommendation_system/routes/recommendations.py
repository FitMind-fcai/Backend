from datetime import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.auth_module.core.dependencies import get_current_verified_user
from app.auth_module.models.user import User
from app.recommendation_system.core.dependencies import get_recommendation_service
from app.recommendation_system.schemas.recommendations import (
    DailySuggestionResponse,
    FitMindScore,
    NextMealResponse,
    NextWorkoutResponse,
    ProgressReport,
)
from app.recommendation_system.services.recommendation_service import RecommendationService


recommendation_router = APIRouter(prefix="/recommendations")


# ──────────────────────────────────────────────────────────────────────────────
# Plan-based recommendations  (next item from active plan)
# ──────────────────────────────────────────────────────────────────────────────

@recommendation_router.get(
    "/next-meal",
    response_model=NextMealResponse,
    tags=["Recommendations · Plan"],
    summary="Get the meal that fits the current (or given) time of day",
    description=(
        "Picks the single meal from today's nutrition plan whose meal type best matches "
        "the provided time. No logging history is checked — this is purely time-based.\n\n"
        "**`time`** — optional, format `HH:MM` (24-hour). Defaults to the current server time "
        "if omitted.\n\n"
        "**Matching logic:** each meal type has a canonical centre time "
        "(Breakfast → 07:30, Lunch → 13:00, Dinner → 19:00, Snack → 15:00, etc.). "
        "The meal whose centre time is closest to the query time is returned.\n\n"
        "Requires an active nutrition plan — use **POST /v1/plan-generation/nutrition** to generate one."
    ),
)
def get_next_meal(
    at_time: Optional[str] = Query(
        default=None,
        alias="time",
        description="Time to base the recommendation on, format HH:MM (24-hour). Defaults to now.",
        pattern=r"^\d{2}:\d{2}$",
    ),
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> NextMealResponse:
    query_time: Optional[time] = None
    if at_time:
        h, m = at_time.split(":")
        query_time = time(int(h), int(m))
    return service.get_next_meal(user_id=current_user.id, query_time=query_time)


@recommendation_router.get(
    "/next-workout",
    response_model=NextWorkoutResponse,
    tags=["Recommendations · Plan"],
    summary="Get today's workout from your workout plan",
    description=(
        "Returns the workout session scheduled for today, determined by cycling through "
        "the plan's days relative to the plan's `start_date`.\n\n"
        "Each exercise in the session is flagged as `already_logged` if it was logged today "
        "via `POST /tracking/logs`.\n\n"
        "Requires an active workout plan — use **POST /v1/plan-generation/workout** to generate one."
    ),
)
def get_next_workout(
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> NextWorkoutResponse:
    return service.get_next_workout(user_id=current_user.id)


# ──────────────────────────────────────────────────────────────────────────────
# AI Suggestion  (last 24 hours)
# ──────────────────────────────────────────────────────────────────────────────

@recommendation_router.get(
    "/daily-suggestion",
    response_model=DailySuggestionResponse,
    tags=["Recommendations · AI"],
    summary="Get an AI coaching tip based on the last 24 hours",
    description=(
        "Analyses the last 24 hours of meal logs, workout logs, and weight logs against "
        "the active plan's targets, then asks the AI coach for a personalised, actionable tip.\n\n"
        "**Features engineered from raw logs before the LLM call:**\n"
        "- Calories consumed vs. target → `calorie_gap`\n"
        "- Protein consumed vs. target → `protein_gap`\n"
        "- Meal types logged\n"
        "- Workout sessions count\n"
        "- Weight recorded flag\n\n"
        "The `urgency` field is one of `on_track`, `needs_attention`, or `off_track`."
    ),
)
def get_daily_suggestion(
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> DailySuggestionResponse:
    return service.get_daily_suggestion(user_id=current_user.id)


# ──────────────────────────────────────────────────────────────────────────────
# Progress Report  (feature engineering + AI analysis)
# ──────────────────────────────────────────────────────────────────────────────

@recommendation_router.get(
    "/progress-report",
    response_model=ProgressReport,
    tags=["Recommendations · AI"],
    summary="Generate a full progress report with feature engineering",
    description=(
        "Runs a full feature-engineering pipeline over the selected period, then sends "
        "the derived feature vector to the AI coach for a structured coaching analysis.\n\n"
        "**`period` options:**\n"
        "- `week` — last 7 days\n"
        "- `month` — last 30 days\n"
        "- `full_plan` — from the active plan's `start_date` to today\n\n"
        "**Engineered features (computed from raw logs, not raw data):**\n\n"
        "*Nutrition*\n"
        "- `logging_consistency_pct` — days with meal logs / period length × 100\n"
        "- `calorie_adherence_pct` — avg daily calories / plan target × 100\n"
        "- `protein_adherence_pct` — avg daily protein / plan target × 100\n"
        "- `calorie_trend_slope` — linear regression slope on daily calorie series (kcal/day)\n"
        "- `macro_balance_score` — how close actual macro ratio is to plan ratio (0–100)\n\n"
        "*Workout*\n"
        "- `frequency_adherence_pct` — actual sessions / planned sessions × 100\n"
        "- `total_volume_kg` — Σ(sets × reps × weight_used) across all logs\n"
        "- `volume_trend_slope` — linear regression slope on weekly volume series\n"
        "- `exercise_progressions` — per-exercise: earliest vs. latest session volume, % change\n\n"
        "*Weight*\n"
        "- `weight_change_kg` — latest − first weight measurement\n"
        "- `weight_trend_slope` — linear regression slope on weight series (kg/day)\n"
        "- `trend_direction` — `losing` | `gaining` | `stable` | `no_data`\n\n"
        "The AI report includes: `assessment`, `positives`, `improvements`, `suggestions`, `projection`."
    ),
)
def get_progress_report(
    period: Literal["week", "month", "full_plan"] = "week",
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> ProgressReport:
    return service.get_progress_report(user_id=current_user.id, period=period)


# ──────────────────────────────────────────────────────────────────────────────
# FitMind Score  (radar chart)
# ──────────────────────────────────────────────────────────────────────────────

@recommendation_router.get(
    "/score",
    response_model=FitMindScore,
    tags=["Recommendations · Score"],
    summary="Get FitMind Score for the radar chart",
    description=(
        "Computes six axis scores (0–100) and three series arrays for the FitMind "
        "Score radar chart, plus a weighted `overall_score`.\n\n"
        "All scores are based on the **last 7 days** of logged data.\n\n"
        "**Axis scores:**\n"
        "- `nutrition` — calorie & protein adherence + logging consistency\n"
        "- `strength`  — total training volume + week-over-week progression\n"
        "- `agility`   — exercise variety + cardio proportion\n"
        "- `endurance` — workout frequency vs. planned sessions per week\n"
        "- `hydration` — average daily water intake vs. 2 500 ml target\n"
        "- `sleep`     — sleep duration (7–9 h = 100) + quality rating (1–10)\n\n"
        "**Series arrays** (6 values each, same axis order) drive the overlapping "
        "hexagons on the radar: `strength_series`, `agility_series`, `endurance_series`."
    ),
)
def get_fitmind_score(
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> FitMindScore:
    return service.get_fitmind_score(user_id=current_user.id)
