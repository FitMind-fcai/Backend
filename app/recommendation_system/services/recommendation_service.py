import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.ai_services.ai_coach.ai_coach_service import AICoachService
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.schemas.recommendations import (
    DailyNutritionTargets,
    DailySnapshot,
    DailySuggestionResponse,
    ExerciseProgression,
    FitMindScore,
    NextMealResponse,
    NextPlanMeal,
    NextWorkoutResponse,
    NutritionFeatures,
    PlanExerciseInfo,
    PlanMealIngredientInfo,
    ProgressFeatures,
    ProgressReport,
    WeightFeatures,
    WorkoutFeatures,
)
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository

logger = logging.getLogger(__name__)


# Maps a normalised meal_type keyword to its "ideal" centre time.
# Matching is done by checking whether the keyword appears anywhere in the
# meal_type string (case-insensitive), so "Morning Snack" matches "snack"
# and also "morning snack".  More-specific keys must come first so they win.
_MEAL_TYPE_CENTERS: List[tuple] = [
    ("pre-workout",       time(9,  30)),
    ("post-workout",      time(16, 30)),
    ("morning snack",     time(10, 30)),
    ("afternoon snack",   time(16,  0)),
    ("evening snack",     time(21,  0)),
    ("breakfast",         time(7,  30)),
    ("lunch",             time(13,  0)),
    ("dinner",            time(19,  0)),
    ("snack",             time(15,  0)),   # generic fallback for any "snack"
]


def _center_time_for_meal_type(meal_type: str) -> time:
    """Return the ideal centre time for a given meal_type string."""
    lower = meal_type.lower()
    for keyword, center in _MEAL_TYPE_CENTERS:
        if keyword in lower:
            return center
    return time(12, 0)   # noon as a safe fallback


def _minutes_from_midnight(t: time) -> int:
    return t.hour * 60 + t.minute


def _trend_slope(values: List[float]) -> float:
    """Linear regression slope via numpy polyfit. Returns 0.0 for < 2 points."""
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope, _ = np.polyfit(x, values, 1)
    return float(slope)


class RecommendationService:
    def __init__(
        self,
        meal_repo: MealLogRepository,
        workout_repo: WorkoutLogRepository,
        weight_repo: WeightLogRepository,
        sleep_repo: SleepLogRepository,
        hydration_repo: HydrationLogRepository,
        nutrition_plan_repo: NutritionPlanRepository,
        workout_plan_repo: WorkoutPlanRepository,
        profile_repo: ProfileRepository,
        ai_coach: AICoachService,
    ):
        self.meal_repo          = meal_repo
        self.workout_repo       = workout_repo
        self.weight_repo        = weight_repo
        self.sleep_repo         = sleep_repo
        self.hydration_repo     = hydration_repo
        self.nutrition_plan_repo = nutrition_plan_repo
        self.workout_plan_repo  = workout_plan_repo
        self.profile_repo       = profile_repo
        self.ai_coach           = ai_coach

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _profile_context(self, user_id: int) -> str:
        profile = self.profile_repo.get_by_user_id(user_id)
        if not profile:
            return "No user profile available."
        return (
            f"Profile: age={profile.age}, gender={profile.gender.value if hasattr(profile.gender, 'value') else profile.gender}, "
            f"weight={profile.weight}kg, height={profile.height}cm, "
            f"goal={profile.fitness_goal.value if hasattr(profile.fitness_goal, 'value') else profile.fitness_goal}, "
            f"activity={profile.activity_level.value if hasattr(profile.activity_level, 'value') else profile.activity_level}, "
            f"dietary={profile.dietary_preference}, "
            f"medical={profile.medical_conditions or 'none'}, "
            f"injuries={profile.injuries or 'none'}"
        )

    def _user_goal(self, user_id: int) -> str:
        profile = self.profile_repo.get_by_user_id(user_id)
        if not profile:
            return "maintain"
        g = profile.fitness_goal
        return g.value if hasattr(g, "value") else str(g)

    def _parse_sessions_per_week(self, frequency: Optional[str]) -> Optional[int]:
        if not frequency:
            return None
        m = re.search(r"(\d+)", frequency)
        return int(m.group(1)) if m else None

    # ──────────────────────────────────────────────────────────────────────────
    # Feature engineering helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _engineer_nutrition_features(
        self,
        user_id: int,
        since: date,
        until: date,
        period_days: int,
    ) -> NutritionFeatures:
        logs = self.meal_repo.list_logs_since(user_id, since, until)

        # Group by day
        daily: Dict[date, Dict[str, float]] = {}
        for log in logs:
            d = log.log_date
            if d not in daily:
                daily[d] = {"cals": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0}
            daily[d]["cals"]    += log.calories
            daily[d]["protein"] += log.protein_g
            daily[d]["carbs"]   += log.carbs_g
            daily[d]["fats"]    += log.fats_g

        days_with_logs = len(daily)
        if days_with_logs == 0:
            return NutritionFeatures(
                period_days=period_days,
                days_with_logs=0,
                logging_consistency_pct=0.0,
                avg_daily_calories=0.0,
                avg_daily_protein_g=0.0,
                avg_daily_carbs_g=0.0,
                avg_daily_fats_g=0.0,
                calorie_trend_slope=0.0,
                macro_balance_score=0.0,
            )

        sorted_days = sorted(daily.keys())
        cal_series = [daily[d]["cals"] for d in sorted_days]

        avg_cals    = sum(cal_series) / days_with_logs
        avg_protein = sum(daily[d]["protein"] for d in sorted_days) / days_with_logs
        avg_carbs   = sum(daily[d]["carbs"]   for d in sorted_days) / days_with_logs
        avg_fats    = sum(daily[d]["fats"]    for d in sorted_days) / days_with_logs

        calorie_trend_slope = _trend_slope(cal_series)
        logging_consistency = (days_with_logs / period_days) * 100.0

        # Compare vs active nutrition plan
        nutrition_plan = self.nutrition_plan_repo.get_active_plan(user_id)
        target_cals    = nutrition_plan.daily_calories    if nutrition_plan else None
        target_protein = nutrition_plan.daily_protein_g   if nutrition_plan else None
        target_carbs   = nutrition_plan.daily_carbs_g     if nutrition_plan else None
        target_fats    = nutrition_plan.daily_fats_g      if nutrition_plan else None

        calorie_adherence = (avg_cals / target_cals * 100.0)    if target_cals  else None
        protein_adherence = (avg_protein / target_protein * 100.0) if target_protein else None

        # Macro balance score: how close actual ratio is to target ratio (0-100)
        macro_balance_score = 0.0
        if target_cals and avg_cals > 0 and target_protein and target_carbs and target_fats:
            total_target_macros = target_protein * 4 + target_carbs * 4 + target_fats * 9
            actual_protein_pct  = (avg_protein * 4 / (avg_cals or 1)) * 100
            actual_carbs_pct    = (avg_carbs   * 4 / (avg_cals or 1)) * 100
            actual_fats_pct     = (avg_fats    * 9 / (avg_cals or 1)) * 100
            target_protein_pct  = (target_protein * 4 / (total_target_macros or 1)) * 100
            target_carbs_pct    = (target_carbs   * 4 / (total_target_macros or 1)) * 100
            target_fats_pct     = (target_fats    * 9 / (total_target_macros or 1)) * 100
            diff = (
                abs(actual_protein_pct - target_protein_pct)
                + abs(actual_carbs_pct - target_carbs_pct)
                + abs(actual_fats_pct  - target_fats_pct)
            )
            macro_balance_score = max(0.0, 100.0 - diff)

        return NutritionFeatures(
            period_days=period_days,
            days_with_logs=days_with_logs,
            logging_consistency_pct=round(logging_consistency, 1),
            avg_daily_calories=round(avg_cals, 1),
            target_daily_calories=target_cals,
            calorie_adherence_pct=round(calorie_adherence, 1) if calorie_adherence is not None else None,
            avg_daily_protein_g=round(avg_protein, 1),
            target_daily_protein_g=target_protein,
            protein_adherence_pct=round(protein_adherence, 1) if protein_adherence is not None else None,
            avg_daily_carbs_g=round(avg_carbs, 1),
            avg_daily_fats_g=round(avg_fats, 1),
            calorie_trend_slope=round(calorie_trend_slope, 3),
            macro_balance_score=round(macro_balance_score, 1),
        )

    def _engineer_workout_features(
        self,
        user_id: int,
        since: date,
        until: date,
        period_days: int,
    ) -> WorkoutFeatures:
        logs = self.workout_repo.list_logs_since(user_id, since, until)

        if not logs:
            return WorkoutFeatures(
                period_days=period_days,
                total_sessions=0,
                avg_sets_per_session=0.0,
                avg_reps_per_session=0.0,
                total_volume_kg=0.0,
                volume_trend_slope=0.0,
                unique_exercises_count=0,
                exercise_progressions=[],
            )

        # Sessions = distinct dates with at least one log
        session_dates = sorted(set(log.log_date for log in logs))
        total_sessions = len(session_dates)

        total_volume = sum(
            log.sets_completed * log.reps_completed * (log.weight_used or 0.0)
            for log in logs
        )
        avg_sets = sum(log.sets_completed for log in logs) / len(logs)
        avg_reps = sum(log.reps_completed for log in logs) / len(logs)

        # Weekly volume series for trend slope
        weekly: Dict[int, float] = {}
        for log in logs:
            week = log.log_date.isocalendar()[1]
            weekly[week] = weekly.get(week, 0.0) + (
                log.sets_completed * log.reps_completed * (log.weight_used or 0.0)
            )
        volume_series = [weekly[w] for w in sorted(weekly.keys())]
        volume_trend_slope = _trend_slope(volume_series)

        # Exercise progressions — group by central_exercise_id, earliest vs latest
        ex_groups: Dict[int, List[Any]] = {}
        for log in sorted(logs, key=lambda l: (l.log_date, l.id)):
            if log.central_exercise_id:
                ex_groups.setdefault(log.central_exercise_id, []).append(log)

        progressions: List[ExerciseProgression] = []
        for ex_id, ex_logs in ex_groups.items():
            sessions = len(set(l.log_date for l in ex_logs))
            first = ex_logs[0]
            last  = ex_logs[-1]
            first_vol = first.sets_completed * first.reps_completed * (first.weight_used or 1.0)
            last_vol  = last.sets_completed  * last.reps_completed  * (last.weight_used  or 1.0)
            pct = ((last_vol - first_vol) / first_vol * 100.0) if first_vol else 0.0
            progressions.append(ExerciseProgression(
                exercise_name=f"Exercise #{ex_id}",  # name resolved below
                sessions_logged=sessions,
                first_volume=round(first_vol, 2),
                latest_volume=round(last_vol, 2),
                progression_pct=round(pct, 1),
            ))

        # Resolve exercise names from the DB in a single query
        self._resolve_exercise_names(progressions, ex_groups)

        # Sort by absolute progression change descending
        progressions.sort(key=lambda p: abs(p.progression_pct), reverse=True)

        # Planned sessions from active workout plan
        workout_plan = self.workout_plan_repo.get_active_plan(user_id)
        planned_sessions = None
        frequency_adherence_pct = None
        if workout_plan:
            spw = self._parse_sessions_per_week(workout_plan.frequency)
            if spw:
                weeks = max(1.0, period_days / 7.0)
                planned_sessions = round(spw * weeks)
                frequency_adherence_pct = round(
                    (total_sessions / planned_sessions) * 100.0, 1
                )

        unique_exercises = len(set(
            log.central_exercise_id for log in logs if log.central_exercise_id
        ))

        return WorkoutFeatures(
            period_days=period_days,
            total_sessions=total_sessions,
            planned_sessions=planned_sessions,
            frequency_adherence_pct=frequency_adherence_pct,
            avg_sets_per_session=round(avg_sets, 1),
            avg_reps_per_session=round(avg_reps, 1),
            total_volume_kg=round(total_volume, 1),
            volume_trend_slope=round(volume_trend_slope, 2),
            unique_exercises_count=unique_exercises,
            exercise_progressions=progressions,
        )

    def _resolve_exercise_names(
        self,
        progressions: List[ExerciseProgression],
        ex_groups: Dict[int, List[Any]],
    ) -> None:
        """Fetch exercise names from the DB and patch the progression objects in-place."""
        from sqlalchemy import text as sql_text
        ids = list(ex_groups.keys())
        if not ids:
            return
        try:
            rows = self.workout_repo.db.execute(
                sql_text("SELECT id, name FROM central_exercises WHERE id = ANY(:ids)"),
                {"ids": ids},
            ).fetchall()
            name_map = {r.id: r.name for r in rows}
            for p in progressions:
                ex_id_str = p.exercise_name.replace("Exercise #", "")
                try:
                    ex_id = int(ex_id_str)
                    if ex_id in name_map:
                        p.exercise_name = name_map[ex_id]
                except ValueError:
                    pass
        except Exception as exc:
            logger.warning("Could not resolve exercise names: %s", exc)

    def _engineer_weight_features(
        self,
        user_id: int,
        since: date,
        until: date,
    ) -> WeightFeatures:
        logs = self.weight_repo.list_logs_since(user_id, since, until)

        if not logs:
            return WeightFeatures(measurements_count=0, trend_direction="no_data")

        sorted_logs = sorted(logs, key=lambda l: (l.log_date, l.id))
        weights = [l.weight for l in sorted_logs]

        start_weight  = weights[0]
        latest_weight = weights[-1]
        weight_change = latest_weight - start_weight

        trend_slope = _trend_slope(weights)
        if abs(trend_slope) < 0.01:
            direction = "stable"
        elif trend_slope > 0:
            direction = "gaining"
        else:
            direction = "losing"

        return WeightFeatures(
            measurements_count=len(logs),
            start_weight_kg=round(start_weight, 2),
            latest_weight_kg=round(latest_weight, 2),
            weight_change_kg=round(weight_change, 2),
            weight_trend_slope=round(trend_slope, 4),
            trend_direction=direction,
        )

    def _compute_overall_consistency(
        self,
        nutrition: NutritionFeatures,
        workout: WorkoutFeatures,
        weight: WeightFeatures,
    ) -> float:
        """
        Weighted composite score 0.0–1.0.
        Nutrition adherence (40%) + workout frequency adherence (40%) + weight logging (20%).
        Falls back gracefully when targets are unavailable.
        """
        n_score = min(1.0, (nutrition.calorie_adherence_pct or 80.0) / 100.0)
        w_score = min(1.0, (workout.frequency_adherence_pct or 0.0) / 100.0) if workout.total_sessions > 0 else 0.0
        wt_score = min(1.0, weight.measurements_count / max(1, nutrition.period_days / 7))

        return round(n_score * 0.40 + w_score * 0.40 + wt_score * 0.20, 3)

    # ──────────────────────────────────────────────────────────────────────────
    # Public API — Next Meal  (time-based recommendation)
    # ──────────────────────────────────────────────────────────────────────────

    def get_next_meal(self, user_id: int, query_time: Optional[time] = None) -> NextMealResponse:
        """
        Return the single meal from the active nutrition plan that best fits the
        given time of day.  When query_time is None the current server time is used.

        Matching is purely time-based — no dependency on what the user has already
        logged.  We compute the absolute minute-distance between query_time and the
        canonical centre-time of each meal type, then return the closest match.
        """
        nutrition_plan = self.nutrition_plan_repo.get_active_plan(user_id)
        if not nutrition_plan:
            return NextMealResponse(
                has_plan=False,
                message="No active nutrition plan found. Generate a nutrition plan first.",
            )

        if query_time is None:
            now = datetime.now()
            query_time = now.time().replace(second=0, microsecond=0)

        query_minutes = _minutes_from_midnight(query_time)
        query_time_str = query_time.strftime("%H:%M")

        today = date.today()
        # day_number: Monday=1 … Sunday=7
        day_number = today.weekday() + 1

        plan_days = self.nutrition_plan_repo.get_days_by_plan_id(nutrition_plan.id)
        if not plan_days:
            return NextMealResponse(
                has_plan=True,
                plan_name=nutrition_plan.plan_name,
                query_time=query_time_str,
                message="The nutrition plan has no days configured.",
            )

        # Resolve today's plan day (with cyclic fallback)
        today_plan_day = next((d for d in plan_days if d.day_number == day_number), None)
        if today_plan_day is None:
            day_in_cycle = (day_number - 1) % len(plan_days)
            today_plan_day = sorted(plan_days, key=lambda d: d.day_number)[day_in_cycle]

        planned_meals = self.nutrition_plan_repo.get_meals_by_day_id(today_plan_day.id)
        if not planned_meals:
            return NextMealResponse(
                has_plan=True,
                plan_name=nutrition_plan.plan_name,
                today_day_name=today_plan_day.day_name,
                query_time=query_time_str,
                message="No meals are configured for today in the plan.",
            )

        # Score each meal by |query_minutes − center_minutes| (wrap-around safe)
        def distance(meal) -> int:
            center = _center_time_for_meal_type(meal.meal_type or "")
            center_mins = _minutes_from_midnight(center)
            diff = abs(query_minutes - center_mins)
            # Handle midnight wrap-around (e.g. query 23:50 vs center 00:10)
            return min(diff, 1440 - diff)

        best_meal = min(planned_meals, key=distance)

        ingredients = []
        for ing in (best_meal.ingredients or []):
            food_name = ing.food.food_name if ing.food else f"Food #{ing.central_food_id}"
            ingredients.append(PlanMealIngredientInfo(food_name=food_name, amount_g=ing.amount_g))

        recommended = NextPlanMeal(
            meal_id=best_meal.id,
            meal_type=best_meal.meal_type,
            meal_name=best_meal.meal_name,
            calories=best_meal.calories,
            protein_g=best_meal.protein_g,
            carbs_g=best_meal.carbs_g,
            fats_g=best_meal.fats_g,
            fiber_g=best_meal.fiber_g,
            instructions=best_meal.instructions,
            prep_time_minutes=best_meal.prep_time_minutes,
            cook_time_minutes=best_meal.cook_time_minutes,
            ingredients=ingredients,
        )

        return NextMealResponse(
            has_plan=True,
            plan_name=nutrition_plan.plan_name,
            today_day_name=today_plan_day.day_name,
            query_time=query_time_str,
            daily_targets=DailyNutritionTargets(
                calories=nutrition_plan.daily_calories,
                protein_g=nutrition_plan.daily_protein_g,
                carbs_g=nutrition_plan.daily_carbs_g,
                fats_g=nutrition_plan.daily_fats_g,
            ),
            recommended_meal=recommended,
            message=(
                f"Recommended {best_meal.meal_type} for {query_time_str}: "
                f"{best_meal.meal_name}."
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Public API — Next Workout
    # ──────────────────────────────────────────────────────────────────────────

    def get_next_workout(self, user_id: int) -> NextWorkoutResponse:
        workout_plan = self.workout_plan_repo.get_active_plan(user_id)
        if not workout_plan:
            return NextWorkoutResponse(
                has_plan=False,
                message="No active workout plan found. Generate a workout plan first.",
            )

        today = date.today()
        workout_days = self.workout_plan_repo.get_days_by_plan_id(workout_plan.id)
        if not workout_days:
            return NextWorkoutResponse(
                has_plan=True,
                plan_name=workout_plan.plan_name,
                message="The workout plan has no days configured.",
            )

        # Determine today's position in the plan cycle
        days_since_start = max(0, (today - workout_plan.start_date).days)
        sorted_days = sorted(workout_days, key=lambda d: d.day_number)
        day_in_cycle = days_since_start % len(sorted_days)
        today_workout_day = sorted_days[day_in_cycle]

        # Today's workout log check
        today_logs = self.workout_repo.list_logs(user_id=user_id, log_date=today)
        sessions_logged_today = len(set(l.log_date for l in today_logs))
        logged_slot_ids = {l.workout_day_exercise_id for l in today_logs if l.workout_day_exercise_id}
        logged_exercise_ids = {l.central_exercise_id for l in today_logs if l.central_exercise_id}

        exercise_slots = self.workout_plan_repo.get_exercises_by_day_id(today_workout_day.id)
        exercises: List[PlanExerciseInfo] = []
        for slot in exercise_slots:
            ce = slot.central_exercise
            exercises.append(PlanExerciseInfo(
                slot_id=slot.id,
                exercise_id=slot.central_exercise_id,
                exercise_name=ce.name if ce else f"Exercise #{slot.central_exercise_id}",
                exercise_type=ce.exercise_type if ce else "Unknown",
                primary_muscle_group=ce.primary_muscle_group if ce else "Unknown",
                equipment_required=ce.equipment_required if ce else "Unknown",
                sets=slot.sets,
                reps=slot.reps,
                weight_kg=slot.weight_kg,
                duration_seconds=slot.duration_seconds,
                rest_seconds=slot.rest_seconds,
                instructions=ce.instructions if ce else slot.notes,
                order_index=slot.order_index,
                already_logged=(
                    slot.id in logged_slot_ids
                    or slot.central_exercise_id in logged_exercise_ids
                ),
            ))

        logged_count = sum(1 for e in exercises if e.already_logged)
        if not exercises:
            message = f"Today's session: {today_workout_day.day_name}. No exercises configured for this day."
        elif logged_count == len(exercises):
            message = f"Today's workout ({today_workout_day.day_name}) is complete! All {len(exercises)} exercises logged."
        else:
            remaining = len(exercises) - logged_count
            message = f"Today's workout: {today_workout_day.day_name}. {remaining} of {len(exercises)} exercises remaining."

        return NextWorkoutResponse(
            has_plan=True,
            plan_name=workout_plan.plan_name,
            workout_day_name=today_workout_day.day_name,
            focus_area=today_workout_day.focus_area,
            estimated_duration_minutes=today_workout_day.estimated_duration,
            exercises=exercises,
            sessions_logged_today=sessions_logged_today,
            message=message,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Public API — Daily AI Suggestion  (last 24 h)
    # ──────────────────────────────────────────────────────────────────────────

    def get_daily_suggestion(self, user_id: int) -> DailySuggestionResponse:
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Fetch last 24 h of logs (yesterday + today covers the rolling window)
        meal_logs    = self.meal_repo.list_logs_since(user_id, yesterday, today)
        workout_logs = self.workout_repo.list_logs_since(user_id, yesterday, today)
        weight_logs  = self.weight_repo.list_logs_since(user_id, yesterday, today)

        cals_consumed    = sum(l.calories  for l in meal_logs)
        protein_consumed = sum(l.protein_g for l in meal_logs)
        carbs_consumed   = sum(l.carbs_g   for l in meal_logs)
        fats_consumed    = sum(l.fats_g    for l in meal_logs)
        meal_types_logged = list({
            l.meal_type.value if hasattr(l.meal_type, "value") else l.meal_type
            for l in meal_logs
        })
        workout_sessions = len(set(l.log_date for l in workout_logs))
        latest_weight    = weight_logs[-1].weight if weight_logs else None

        nutrition_plan = self.nutrition_plan_repo.get_active_plan(user_id)
        target_cals    = nutrition_plan.daily_calories  if nutrition_plan else None
        target_protein = nutrition_plan.daily_protein_g if nutrition_plan else None
        calorie_gap    = (target_cals - cals_consumed)    if target_cals    else None
        protein_gap    = (target_protein - protein_consumed) if target_protein else None

        snapshot = DailySnapshot(
            calories_consumed=round(cals_consumed, 1),
            protein_consumed=round(protein_consumed, 1),
            carbs_consumed=round(carbs_consumed, 1),
            fats_consumed=round(fats_consumed, 1),
            calories_target=target_cals,
            protein_target=target_protein,
            calorie_gap=round(calorie_gap, 1) if calorie_gap is not None else None,
            protein_gap=round(protein_gap, 1) if protein_gap is not None else None,
            meal_types_logged=meal_types_logged,
            workout_sessions_logged=workout_sessions,
            weight_logged=bool(weight_logs),
            latest_weight_kg=latest_weight,
        )

        user_goal = self._user_goal(user_id)
        profile_ctx = self._profile_context(user_id)

        ai_result = self.ai_coach.analyze_daily_progress(
            snapshot_data=snapshot.model_dump(),
            user_goal=user_goal,
            user_profile_context=profile_ctx,
        )

        return DailySuggestionResponse(
            snapshot=snapshot,
            urgency=ai_result["urgency"],
            suggestion=ai_result["suggestion"],
            generated_at=datetime.utcnow(),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Public API — Progress Report  (feature engineering + LLM analysis)
    # ──────────────────────────────────────────────────────────────────────────

    def get_progress_report(self, user_id: int, period: str) -> ProgressReport:
        """
        period: "week" (7 days) | "month" (30 days) | "full_plan" (since active plan start)
        """
        today = date.today()

        if period == "week":
            since       = today - timedelta(days=7)
            period_days = 7
            label       = "Last 7 Days"
        elif period == "month":
            since       = today - timedelta(days=30)
            period_days = 30
            label       = "Last 30 Days"
        else:
            # full_plan: use the earliest plan start date across both plan types
            nutrition_plan = self.nutrition_plan_repo.get_active_plan(user_id)
            workout_plan   = self.workout_plan_repo.get_active_plan(user_id)
            dates = [p.start_date for p in [nutrition_plan, workout_plan] if p]
            if dates:
                since = min(dates)
            else:
                since = today - timedelta(days=30)
            period_days = max(1, (today - since).days)
            label = "Full Plan Duration"

        until = today

        # ── Feature extraction ─────────────────────────────────────────────
        nutrition_features = self._engineer_nutrition_features(user_id, since, until, period_days)
        workout_features   = self._engineer_workout_features(user_id, since, until, period_days)
        weight_features    = self._engineer_weight_features(user_id, since, until)

        overall_score = self._compute_overall_consistency(
            nutrition_features, workout_features, weight_features
        )
        on_track = (
            overall_score >= 0.65
            and (nutrition_features.calorie_adherence_pct or 80.0) >= 75.0
        )

        features = ProgressFeatures(
            period_label=label,
            period_days=period_days,
            period_start=since.isoformat(),
            period_end=until.isoformat(),
            user_goal=self._user_goal(user_id),
            overall_consistency_score=overall_score,
            on_track=on_track,
            nutrition=nutrition_features,
            workout=workout_features,
            weight=weight_features,
        )

        # ── LLM analysis via AICoachService ───────────────────────────────
        profile_ctx = self._profile_context(user_id)
        ai_result   = self.ai_coach.generate_progress_report(
            features_data=features.model_dump(),
            user_profile_context=profile_ctx,
        )

        return ProgressReport(
            features=features,
            assessment=ai_result["assessment"],
            positives=ai_result["positives"],
            improvements=ai_result["improvements"],
            suggestions=ai_result["suggestions"],
            projection=ai_result["projection"],
            generated_at=datetime.utcnow(),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # FitMind Score  (radar chart data)
    # ──────────────────────────────────────────────────────────────────────────

    def get_fitmind_score(self, user_id: int) -> FitMindScore:
        today = date.today()
        since_7  = today - timedelta(days=7)
        since_30 = today - timedelta(days=30)

        # ── Nutrition (0-100) ────────────────────────────────────────────────
        meal_logs = self.meal_repo.list_logs_since(user_id, since_7, today)
        profile   = self.profile_repo.get_by_user_id(user_id)
        calorie_target  = getattr(profile, "daily_calories", None) if profile else None
        protein_target  = getattr(profile, "protein_target", None) if profile else None

        days_with_meals: Dict[date, List[Any]] = {}
        for log in meal_logs:
            days_with_meals.setdefault(log.log_date, []).append(log)

        logging_consistency = len(days_with_meals) / 7 * 100

        calorie_adherence = 100.0
        protein_adherence = 100.0
        if days_with_meals and calorie_target:
            day_cals = [sum(l.calories or 0 for l in logs) for logs in days_with_meals.values()]
            avg_cals = sum(day_cals) / len(day_cals)
            ratio = avg_cals / calorie_target
            # penalise both over and under; perfect = 1.0
            calorie_adherence = max(0.0, 100.0 - abs(1.0 - ratio) * 100)
        if days_with_meals and protein_target:
            day_prot = [sum(l.protein_g or 0 for l in logs) for logs in days_with_meals.values()]
            avg_prot = sum(day_prot) / len(day_prot)
            ratio = avg_prot / protein_target
            protein_adherence = max(0.0, 100.0 - abs(1.0 - ratio) * 100)

        nutrition_score = int(
            logging_consistency * 0.4
            + calorie_adherence  * 0.35
            + protein_adherence  * 0.25
        )

        # ── Workout logs (shared by strength / agility / endurance) ──────────
        workout_logs = self.workout_repo.list_logs_since(user_id, since_7, today)

        # total volume this week
        total_volume = sum(
            (log.sets_completed or 0) * (log.reps_completed or 0) * (log.weight_used_kg or 0)
            for log in workout_logs
        )
        # prior week for progression
        since_14 = today - timedelta(days=14)
        prev_logs = self.workout_repo.list_logs_since(user_id, since_14, since_7)
        prev_volume = sum(
            (log.sets_completed or 0) * (log.reps_completed or 0) * (log.weight_used_kg or 0)
            for log in prev_logs
        )

        # exercise type breakdown
        cardio_types = {"cardio", "plyometrics", "stretching"}
        strength_types = {"strength", "powerlifting", "olympic weightlifting", "strongman"}
        session_dates = {log.log_date for log in workout_logs}
        sessions_count = len(session_dates)

        cardio_logs   = [l for l in workout_logs if (l.exercise_type or "").lower() in cardio_types]
        strength_logs = [l for l in workout_logs if (l.exercise_type or "").lower() in strength_types]
        unique_exercises = len({l.central_exercise_id or l.exercise_name for l in workout_logs})

        # ── Strength (0-100) ─────────────────────────────────────────────────
        # based on volume and week-over-week progression
        volume_score = min(100.0, total_volume / 5000 * 100) if total_volume > 0 else 0.0
        progression_bonus = 0.0
        if prev_volume > 0 and total_volume > prev_volume:
            progression_bonus = min(20.0, (total_volume - prev_volume) / prev_volume * 100)
        strength_score = int(min(100, volume_score * 0.8 + progression_bonus))

        # ── Agility (0-100) ──────────────────────────────────────────────────
        # exercise variety (unique exercises) + cardio proportion
        variety_score = min(100.0, unique_exercises / 10 * 100)
        cardio_ratio  = len(cardio_logs) / len(workout_logs) * 100 if workout_logs else 0.0
        agility_score = int(variety_score * 0.6 + cardio_ratio * 0.4)

        # ── Endurance (0-100) ────────────────────────────────────────────────
        # workout frequency vs target (3–4 sessions/week default)
        workout_plan = self.workout_plan_repo.get_active_plan(user_id)
        planned_sessions_per_week: Optional[int] = None
        if workout_plan:
            planned_sessions_per_week = self._parse_sessions_per_week(
                getattr(workout_plan, "frequency", None)
            )
        target_sessions = planned_sessions_per_week or 4
        frequency_score = min(100.0, sessions_count / target_sessions * 100)
        endurance_score = int(frequency_score)

        # ── Hydration (0-100) ────────────────────────────────────────────────
        DAILY_WATER_TARGET_ML = 2500.0
        hydration_logs = self.hydration_repo.list_logs_since(user_id, since_7, today)
        if hydration_logs:
            days_with_hydration: Dict[date, float] = {}
            for log in hydration_logs:
                days_with_hydration[log.log_date] = (
                    days_with_hydration.get(log.log_date, 0.0) + (log.water_ml or 0.0)
                )
            avg_daily_water = sum(days_with_hydration.values()) / len(days_with_hydration)
            hydration_score = int(min(100.0, avg_daily_water / DAILY_WATER_TARGET_ML * 100))
        else:
            hydration_score = 0

        # ── Sleep (0-100) ────────────────────────────────────────────────────
        # hours score: 7-9h → 100, penalise linearly outside
        # quality score: 1-10 → 0-100
        sleep_logs = self.sleep_repo.list_logs_since(user_id, since_7, today)
        if sleep_logs:
            hours_scores: List[float] = []
            for log in sleep_logs:
                h = log.sleep_hours or 0.0
                if 7 <= h <= 9:
                    hours_scores.append(100.0)
                elif h < 7:
                    hours_scores.append(max(0.0, h / 7 * 100))
                else:
                    hours_scores.append(max(0.0, 100.0 - (h - 9) / 3 * 100))
            avg_hours_score   = sum(hours_scores) / len(hours_scores)
            avg_quality_score = sum((log.sleep_quality or 5) for log in sleep_logs) / len(sleep_logs) / 10 * 100
            sleep_score = int(avg_hours_score * 0.6 + avg_quality_score * 0.4)
        else:
            sleep_score = 0

        # ── Overall (weighted average) ────────────────────────────────────────
        overall_score = int(
            nutrition_score * 0.25
            + strength_score  * 0.20
            + agility_score   * 0.15
            + endurance_score * 0.20
            + hydration_score * 0.10
            + sleep_score     * 0.10
        )

        # ── Series arrays (same 6-axis order: nutrition/strength/agility/endurance/hydration/sleep) ──
        axes = [nutrition_score, strength_score, agility_score, endurance_score, hydration_score, sleep_score]

        # STRENGTH series: biased toward strength + endurance
        strength_series = [
            int(axes[0] * 0.5),            # nutrition — partial influence
            axes[1],                        # strength — full
            int(axes[2] * 0.3),            # agility  — low
            int(axes[3] * 0.7),            # endurance — moderate
            int(axes[4] * 0.3),            # hydration — low
            int(axes[5] * 0.4),            # sleep     — moderate
        ]
        # AGILITY series: biased toward agility + endurance
        agility_series = [
            int(axes[0] * 0.3),
            int(axes[1] * 0.3),
            axes[2],                        # agility  — full
            int(axes[3] * 0.5),
            int(axes[4] * 0.5),
            int(axes[5] * 0.5),
        ]
        # ENDURANCE series: biased toward endurance + cardio-adjacent axes
        endurance_series = [
            int(axes[0] * 0.4),
            int(axes[1] * 0.4),
            int(axes[2] * 0.5),
            axes[3],                        # endurance — full
            int(axes[4] * 0.6),
            int(axes[5] * 0.6),
        ]

        return FitMindScore(
            overall_score=overall_score,
            nutrition=nutrition_score,
            strength=strength_score,
            agility=agility_score,
            endurance=endurance_score,
            hydration=hydration_score,
            sleep=sleep_score,
            strength_series=strength_series,
            agility_series=agility_series,
            endurance_series=endurance_series,
            generated_at=datetime.utcnow(),
        )
