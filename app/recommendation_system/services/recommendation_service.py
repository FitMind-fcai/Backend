import logging
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from app.ai_services.ai_coach.ai_coach_service import AICoachService
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.schemas.recommendations import (
    DailyNutritionTargets,
    DailySnapshot,
    DailySuggestionResponse,
    FitMindScore,
    NextMealResponse,
    NextPlanMeal,
    NextWorkoutResponse,
    PlanExerciseInfo,
    PlanMealIngredientInfo,
    ProgressFeatures,
    ProgressReport,
)
from app.recommendation_system.services.feature_engineering import FeatureEngineeringService
from app.recommendation_system.services.score_service import ScoreService
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)


_MEAL_TYPE_CENTERS: List[tuple] = [
    ("pre-workout",       time(9,  30)),
    ("post-workout",      time(16, 30)),
    ("morning snack",     time(10, 30)),
    ("afternoon snack",   time(16,  0)),
    ("evening snack",     time(21,  0)),
    ("breakfast",         time(7,  30)),
    ("lunch",             time(13,  0)),
    ("dinner",            time(19,  0)),
    ("snack",             time(15,  0)),
]


def _center_time_for_meal_type(meal_type: str) -> time:
    lower = meal_type.lower()
    for keyword, center in _MEAL_TYPE_CENTERS:
        if keyword in lower:
            return center
    return time(12, 0)


def _minutes_from_midnight(t: time) -> int:
    return t.hour * 60 + t.minute


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

        self._features = FeatureEngineeringService(
            meal_repo=meal_repo,
            workout_repo=workout_repo,
            weight_repo=weight_repo,
            nutrition_plan_repo=nutrition_plan_repo,
            workout_plan_repo=workout_plan_repo,
        )
        self._score = ScoreService(
            meal_repo=meal_repo,
            workout_repo=workout_repo,
            sleep_repo=sleep_repo,
            hydration_repo=hydration_repo,
            workout_plan_repo=workout_plan_repo,
            profile_repo=profile_repo,
        )

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

    # ── Next Meal ─────────────────────────────────────────────────────────────

    def get_next_meal(self, user_id: int, query_time: Optional[time] = None) -> NextMealResponse:
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
        day_number = today.weekday() + 1

        plan_days = self.nutrition_plan_repo.get_days_by_plan_id(nutrition_plan.id)
        if not plan_days:
            return NextMealResponse(
                has_plan=True,
                plan_name=nutrition_plan.plan_name,
                query_time=query_time_str,
                message="The nutrition plan has no days configured.",
            )

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

        def distance(meal) -> int:
            center = _center_time_for_meal_type(meal.meal_type or "")
            center_mins = _minutes_from_midnight(center)
            diff = abs(query_minutes - center_mins)
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

    # ── Next Workout ──────────────────────────────────────────────────────────

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

        days_since_start = max(0, (today - workout_plan.start_date).days)
        sorted_days = sorted(workout_days, key=lambda d: d.day_number)
        day_in_cycle = days_since_start % len(sorted_days)
        today_workout_day = sorted_days[day_in_cycle]

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

    # ── Daily AI Suggestion ───────────────────────────────────────────────────

    def get_daily_suggestion(self, user_id: int) -> DailySuggestionResponse:
        today = date.today()
        yesterday = today - timedelta(days=1)

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

    # ── Progress Report ───────────────────────────────────────────────────────

    def get_progress_report(self, user_id: int, period: str) -> ProgressReport:
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

        nutrition_features = self._features.engineer_nutrition_features(user_id, since, until, period_days)
        workout_features   = self._features.engineer_workout_features(user_id, since, until, period_days)
        weight_features    = self._features.engineer_weight_features(user_id, since, until)

        overall_score = self._features.compute_overall_consistency(
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

    # ── FitMind Score ─────────────────────────────────────────────────────────

    def get_fitmind_score(self, user_id: int) -> FitMindScore:
        return self._score.get_fitmind_score(user_id)
