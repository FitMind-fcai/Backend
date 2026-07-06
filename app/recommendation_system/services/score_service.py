import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.schemas.recommendations import FitMindScore
from app.recommendation_system.services.feature_engineering import (
    _parse_sessions_per_week,
)
from app.tracking_module.repositories.hydration_log_repository import (
    HydrationLogRepository,
)
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)


class ScoreService:
    def __init__(
        self,
        meal_repo: MealLogRepository,
        workout_repo: WorkoutLogRepository,
        sleep_repo: SleepLogRepository,
        hydration_repo: HydrationLogRepository,
        workout_plan_repo: WorkoutPlanRepository,
        profile_repo: ProfileRepository,
    ):
        self.meal_repo = meal_repo
        self.workout_repo = workout_repo
        self.sleep_repo = sleep_repo
        self.hydration_repo = hydration_repo
        self.workout_plan_repo = workout_plan_repo
        self.profile_repo = profile_repo

    def get_fitmind_score(self, user_id: int) -> FitMindScore:
        today = date.today()
        since_7 = today - timedelta(days=7)

        nutrition_score = self._calc_nutrition_score(user_id, since_7, today)
        strength_score, agility_score, endurance_score = self._calc_workout_scores(
            user_id, since_7, today
        )
        hydration_score = self._calc_hydration_score(user_id, since_7, today)
        sleep_score = self._calc_sleep_score(user_id, since_7, today)

        overall_score = int(
            nutrition_score * 0.25
            + strength_score * 0.20
            + agility_score * 0.15
            + endurance_score * 0.20
            + hydration_score * 0.10
            + sleep_score * 0.10
        )

        axes = [
            nutrition_score,
            strength_score,
            agility_score,
            endurance_score,
            hydration_score,
            sleep_score,
        ]

        strength_series = [
            int(axes[0] * 0.5),
            axes[1],
            int(axes[2] * 0.3),
            int(axes[3] * 0.7),
            int(axes[4] * 0.3),
            int(axes[5] * 0.4),
        ]
        agility_series = [
            int(axes[0] * 0.3),
            int(axes[1] * 0.3),
            axes[2],
            int(axes[3] * 0.5),
            int(axes[4] * 0.5),
            int(axes[5] * 0.5),
        ]
        endurance_series = [
            int(axes[0] * 0.4),
            int(axes[1] * 0.4),
            int(axes[2] * 0.5),
            axes[3],
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

    def _calc_nutrition_score(self, user_id: int, since: date, until: date) -> int:
        meal_logs = self.meal_repo.list_logs_since(user_id, since, until)
        profile = self.profile_repo.get_by_user_id(user_id)
        calorie_target = getattr(profile, "daily_calories", None) if profile else None
        protein_target = getattr(profile, "protein_target", None) if profile else None

        days_with_meals: Dict[date, List[Any]] = {}
        for log in meal_logs:
            days_with_meals.setdefault(log.log_date, []).append(log)

        logging_consistency = len(days_with_meals) / 7 * 100

        calorie_adherence = 0.0
        protein_adherence = 0.0
        if days_with_meals and calorie_target:
            day_cals = [
                sum(l.calories or 0 for l in logs) for logs in days_with_meals.values()
            ]
            avg_cals = sum(day_cals) / len(day_cals)
            ratio = avg_cals / calorie_target
            calorie_adherence = max(0.0, 100.0 - abs(1.0 - ratio) * 100)
        if days_with_meals and protein_target:
            day_prot = [
                sum(l.protein_g or 0 for l in logs) for logs in days_with_meals.values()
            ]
            avg_prot = sum(day_prot) / len(day_prot)
            ratio = avg_prot / protein_target
            protein_adherence = max(0.0, 100.0 - abs(1.0 - ratio) * 100)

        return int(
            logging_consistency * 0.4
            + calorie_adherence * 0.35
            + protein_adherence * 0.25
        )

    def _calc_workout_scores(
        self, user_id: int, since: date, until: date
    ) -> tuple[int, int, int]:
        workout_logs = self.workout_repo.list_logs_since(user_id, since, until)

        total_volume = sum(
            (log.sets_completed or 0)
            * (log.reps_completed or 0)
            * (log.weight_used or 0)
            for log in workout_logs
        )
        since_14 = since - timedelta(days=7)
        prev_logs = self.workout_repo.list_logs_since(user_id, since_14, since)
        prev_volume = sum(
            (log.sets_completed or 0)
            * (log.reps_completed or 0)
            * (log.weight_used or 0)
            for log in prev_logs
        )

        cardio_types = {"cardio", "plyometrics", "stretching"}
        session_dates = {log.log_date for log in workout_logs}
        sessions_count = len(session_dates)

        def _exercise_type(log: Any) -> str:
            ce = log.central_exercise
            return (ce.exercise_type or "").lower() if ce else ""

        cardio_logs = [l for l in workout_logs if _exercise_type(l) in cardio_types]
        unique_exercises = len(
            {l.central_exercise_id for l in workout_logs if l.central_exercise_id}
        )

        # Strength
        volume_score = (
            min(100.0, total_volume / 5000 * 100) if total_volume > 0 else 0.0
        )
        progression_bonus = 0.0
        if prev_volume > 0 and total_volume > prev_volume:
            progression_bonus = min(
                20.0, (total_volume - prev_volume) / prev_volume * 100
            )
        strength_score = int(min(100, volume_score * 0.8 + progression_bonus))

        # Agility
        variety_score = min(100.0, unique_exercises / 10 * 100)
        cardio_ratio = (
            len(cardio_logs) / len(workout_logs) * 100 if workout_logs else 0.0
        )
        agility_score = int(variety_score * 0.6 + cardio_ratio * 0.4)

        # Endurance
        workout_plan = self.workout_plan_repo.get_active_plan(user_id)
        planned_sessions_per_week: Optional[int] = None
        if workout_plan:
            planned_sessions_per_week = _parse_sessions_per_week(
                getattr(workout_plan, "frequency", None)
            )
        target_sessions = planned_sessions_per_week or 4
        frequency_score = min(100.0, sessions_count / target_sessions * 100)
        endurance_score = int(frequency_score)

        return strength_score, agility_score, endurance_score

    def _calc_hydration_score(self, user_id: int, since: date, until: date) -> int:
        DAILY_WATER_TARGET_ML = 2500.0
        hydration_logs = self.hydration_repo.list_logs_since(user_id, since, until)
        if not hydration_logs:
            return 0

        days_with_hydration: Dict[date, float] = {}
        for log in hydration_logs:
            days_with_hydration[log.log_date] = days_with_hydration.get(
                log.log_date, 0.0
            ) + (log.water_ml or 0.0)
        avg_daily_water = sum(days_with_hydration.values()) / len(days_with_hydration)
        return int(min(100.0, avg_daily_water / DAILY_WATER_TARGET_ML * 100))

    def _calc_sleep_score(self, user_id: int, since: date, until: date) -> int:
        sleep_logs = self.sleep_repo.list_logs_since(user_id, since, until)
        if not sleep_logs:
            return 0

        hours_scores: List[float] = []
        for log in sleep_logs:
            h = log.sleep_hours or 0.0
            if 7 <= h <= 9:
                hours_scores.append(100.0)
            elif h < 7:
                hours_scores.append(max(0.0, h / 7 * 100))
            else:
                hours_scores.append(max(0.0, 100.0 - (h - 9) / 3 * 100))
        avg_hours_score = sum(hours_scores) / len(hours_scores)
        avg_quality_score = (
            sum((log.sleep_quality or 5) for log in sleep_logs)
            / len(sleep_logs)
            / 10
            * 100
        )
        return int(avg_hours_score * 0.6 + avg_quality_score * 0.4)
