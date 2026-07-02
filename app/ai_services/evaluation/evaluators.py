"""
evaluators.py — Rule-based + LLM-judge evaluation for each plan type.

evaluate_workout_plan(plan, profile, prefs, groq_client, model) → EvalReport
evaluate_nutrition_plan(plan, profile, prefs, groq_client, model) → EvalReport

Each function runs fast rule-based checks first (no API call), then one LLM
judge call per plan that semantically verifies the remaining constraints.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.ai_services.ai_coach.dtos import (
    NutritionPlanDTO,
    NutritionPreferencesDTO,
    UserProfileDTO,
    WorkoutPlanDTO,
    WorkoutPreferencesDTO,
)
from app.ai_services.evaluation.judge import judge_nutrition_plan, judge_workout_plan
from app.ai_services.evaluation.models import CheckResult, EvalReport


# ---------------------------------------------------------------------------
# Workout
# ---------------------------------------------------------------------------

def evaluate_workout_plan(
    plan: WorkoutPlanDTO,
    profile: UserProfileDTO,
    prefs: WorkoutPreferencesDTO,
    groq_client,
    model: str,
) -> EvalReport:
    checks: List[CheckResult] = []

    # ── Rule-based: days count (±1 day tolerance — scheduling quirks aren't safety issues) ──
    actual_days = len(plan.workout_days)
    day_diff = abs(actual_days - prefs.workout_days_per_week)
    days_ok = day_diff <= 1
    checks.append(CheckResult(
        name="days_count_match",
        applicable=True,
        passed=days_ok,
        score=1.0 if days_ok else max(0.0, 1.0 - (day_diff - 1) / max(prefs.workout_days_per_week, 1)),
        weight=10,
        violations=[] if days_ok else [
            f"Expected {prefs.workout_days_per_week} days, got {actual_days}"
        ],
        reasoning=f"Plan has {actual_days} days, {prefs.workout_days_per_week} requested.",
    ))

    # ── LLM judge ─────────────────────────────────────────────────────
    judge = judge_workout_plan(plan, profile, prefs, groq_client, model)
    judge_prompt = judge.pop("_judge_prompt", "")
    judge_raw_response = judge.pop("_judge_raw_response", "")

    def _add(name: str, applicable: bool, weight: float) -> None:
        chk = judge.get(name, {})
        passed = chk.get("passed", True)
        checks.append(CheckResult(
            name=name,
            applicable=applicable,
            passed=passed,
            score=1.0 if passed else 0.0,
            weight=weight,
            violations=chk.get("violations", []),
            reasoning=chk.get("reasoning", judge.get("_judge_error", "")),
        ))

    has_injury = bool(
        profile.injuries
        and profile.injuries.strip()
        and profile.injuries.lower() != "none"
    )
    has_condition = bool(
        profile.medical_conditions
        and profile.medical_conditions.strip()
        and profile.medical_conditions.lower() != "none"
    )

    _add("injury_safety",            applicable=has_injury,    weight=30)
    _add("medical_condition_safety", applicable=has_condition, weight=30)
    _add("equipment_compliance",     applicable=True,          weight=25)
    _add("goal_alignment",           applicable=True,          weight=15)

    return EvalReport(checks=checks, judge_prompt=judge_prompt, judge_raw_response=judge_raw_response)


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------

def evaluate_nutrition_plan(
    plan: NutritionPlanDTO,
    profile: UserProfileDTO,
    prefs: NutritionPreferencesDTO,
    groq_client,
    model: str,
) -> EvalReport:
    checks: List[CheckResult] = []

    # ── Rule-based: meals count per day (±1 meal tolerance) ───────────
    # NutritionPlanDTO stores meals inside days (plan.days[i].meals).
    # Check the first day as representative of the daily meal structure.
    first_day_meals = plan.days[0].meals if plan.days else []
    actual_meals = len(first_day_meals)
    meal_diff = abs(actual_meals - prefs.meals_per_day)
    meals_ok = meal_diff <= 1
    checks.append(CheckResult(
        name="meals_count_match",
        applicable=True,
        passed=meals_ok,
        score=1.0 if meals_ok else max(0.0, 1.0 - (meal_diff - 1) / max(prefs.meals_per_day, 1)),
        weight=10,
        violations=[] if meals_ok else [
            f"Expected {prefs.meals_per_day} meals per day, got {actual_meals}"
        ],
        reasoning=f"Day 1 has {actual_meals} meals, {prefs.meals_per_day} requested.",
    ))

    # ── Rule-based: calorie accuracy (±20%) ───────────────────────────
    base_calories = 2000
    if profile.fitness_goal == "Lose Weight":
        base_calories -= 300
    elif profile.fitness_goal == "Build Muscle":
        base_calories += 300
    target_cal = prefs.custom_calorie_target or base_calories

    # Use the plan's pre-computed daily_calories if set; otherwise sum first-day meals
    if plan.daily_calories is not None:
        total_cal = plan.daily_calories
    else:
        total_cal = sum(m.calories or 0 for m in first_day_meals)

    cal_diff_pct = abs(total_cal - target_cal) / max(target_cal, 1)
    cal_ok = cal_diff_pct <= 0.20
    checks.append(CheckResult(
        name="calorie_accuracy",
        applicable=True,
        passed=cal_ok,
        score=1.0 if cal_ok else max(0.0, 1.0 - cal_diff_pct),
        weight=15,
        violations=[] if cal_ok else [
            f"Target {target_cal} kcal, got {total_cal:.0f} kcal "
            f"({cal_diff_pct * 100:.1f}% off)"
        ],
        reasoning=f"Daily calories: {total_cal:.0f} kcal, target: {target_cal} kcal.",
    ))

    # ── LLM judge ─────────────────────────────────────────────────────
    judge = judge_nutrition_plan(plan, profile, prefs, groq_client, model)
    judge_prompt = judge.pop("_judge_prompt", "")
    judge_raw_response = judge.pop("_judge_raw_response", "")

    def _add(name: str, applicable: bool, weight: float) -> None:
        chk = judge.get(name, {})
        passed = chk.get("passed", True)
        checks.append(CheckResult(
            name=name,
            applicable=applicable,
            passed=passed,
            score=1.0 if passed else 0.0,
            weight=weight,
            violations=chk.get("violations", []),
            reasoning=chk.get("reasoning", judge.get("_judge_error", "")),
        ))

    has_allergy = bool(
        profile.allergies
        and profile.allergies.strip()
        and profile.allergies.lower() != "none"
    )
    has_diet_pref = bool(
        profile.dietary_preference
        and profile.dietary_preference.strip()
        and profile.dietary_preference.lower() not in ("none", "any")
    )
    has_exclusions = bool(prefs.exclude_ingredients)

    _add("allergen_safety",              applicable=has_allergy,     weight=35)
    _add("dietary_preference_respected", applicable=has_diet_pref,   weight=25)
    _add("exclusion_compliance",         applicable=has_exclusions,  weight=20)
    _add("goal_alignment",               applicable=True,            weight=15)

    return EvalReport(checks=checks, judge_prompt=judge_prompt, judge_raw_response=judge_raw_response)
