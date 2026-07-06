import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np

from app.planning_module.repositories.nutrition_repository import (
    NutritionPlanRepository,
)
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.recommendation_system.schemas.recommendations import (
    ExerciseProgression,
    NutritionFeatures,
    ProgressFeatures,
    WeightFeatures,
    WorkoutFeatures,
)
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository

logger = logging.getLogger(__name__)


def _trend_slope(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope, _ = np.polyfit(x, values, 1)
    return float(slope)


def _parse_sessions_per_week(frequency: Optional[str]) -> Optional[int]:
    if not frequency:
        return None
    m = re.search(r"(\d+)", frequency)
    return int(m.group(1)) if m else None


class FeatureEngineeringService:
    def __init__(
        self,
        meal_repo: MealLogRepository,
        workout_repo: WorkoutLogRepository,
        weight_repo: WeightLogRepository,
        nutrition_plan_repo: NutritionPlanRepository,
        workout_plan_repo: WorkoutPlanRepository,
    ):
        self.meal_repo = meal_repo
        self.workout_repo = workout_repo
        self.weight_repo = weight_repo
        self.nutrition_plan_repo = nutrition_plan_repo
        self.workout_plan_repo = workout_plan_repo

    def engineer_nutrition_features(
        self,
        user_id: int,
        since: date,
        until: date,
        period_days: int,
    ) -> NutritionFeatures:
        logs = self.meal_repo.list_logs_since(user_id, since, until)

        daily: Dict[date, Dict[str, float]] = {}
        for log in logs:
            d = log.log_date
            if d not in daily:
                daily[d] = {"cals": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0}
            daily[d]["cals"] += log.calories
            daily[d]["protein"] += log.protein_g
            daily[d]["carbs"] += log.carbs_g
            daily[d]["fats"] += log.fats_g

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

        avg_cals = sum(cal_series) / days_with_logs
        avg_protein = sum(daily[d]["protein"] for d in sorted_days) / days_with_logs
        avg_carbs = sum(daily[d]["carbs"] for d in sorted_days) / days_with_logs
        avg_fats = sum(daily[d]["fats"] for d in sorted_days) / days_with_logs

        calorie_trend_slope = _trend_slope(cal_series)
        logging_consistency = (days_with_logs / period_days) * 100.0

        nutrition_plan = self.nutrition_plan_repo.get_active_plan(user_id)
        target_cals = nutrition_plan.daily_calories if nutrition_plan else None
        target_protein = nutrition_plan.daily_protein_g if nutrition_plan else None
        target_carbs = nutrition_plan.daily_carbs_g if nutrition_plan else None
        target_fats = nutrition_plan.daily_fats_g if nutrition_plan else None

        calorie_adherence = (avg_cals / target_cals * 100.0) if target_cals else None
        protein_adherence = (
            (avg_protein / target_protein * 100.0) if target_protein else None
        )

        macro_balance_score = 0.0
        if (
            target_cals
            and avg_cals > 0
            and target_protein
            and target_carbs
            and target_fats
        ):
            total_target_macros = (
                target_protein * 4 + target_carbs * 4 + target_fats * 9
            )
            actual_protein_pct = (avg_protein * 4 / (avg_cals or 1)) * 100
            actual_carbs_pct = (avg_carbs * 4 / (avg_cals or 1)) * 100
            actual_fats_pct = (avg_fats * 9 / (avg_cals or 1)) * 100
            target_protein_pct = (target_protein * 4 / (total_target_macros or 1)) * 100
            target_carbs_pct = (target_carbs * 4 / (total_target_macros or 1)) * 100
            target_fats_pct = (target_fats * 9 / (total_target_macros or 1)) * 100
            diff = (
                abs(actual_protein_pct - target_protein_pct)
                + abs(actual_carbs_pct - target_carbs_pct)
                + abs(actual_fats_pct - target_fats_pct)
            )
            macro_balance_score = max(0.0, 100.0 - diff)

        return NutritionFeatures(
            period_days=period_days,
            days_with_logs=days_with_logs,
            logging_consistency_pct=round(logging_consistency, 1),
            avg_daily_calories=round(avg_cals, 1),
            target_daily_calories=target_cals,
            calorie_adherence_pct=round(calorie_adherence, 1)
            if calorie_adherence is not None
            else None,
            avg_daily_protein_g=round(avg_protein, 1),
            target_daily_protein_g=target_protein,
            protein_adherence_pct=round(protein_adherence, 1)
            if protein_adherence is not None
            else None,
            avg_daily_carbs_g=round(avg_carbs, 1),
            avg_daily_fats_g=round(avg_fats, 1),
            calorie_trend_slope=round(calorie_trend_slope, 3),
            macro_balance_score=round(macro_balance_score, 1),
        )

    def engineer_workout_features(
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

        session_dates = sorted(set(log.log_date for log in logs))
        total_sessions = len(session_dates)

        total_volume = sum(
            log.sets_completed * log.reps_completed * (log.weight_used or 0.0)
            for log in logs
        )
        avg_sets = sum(log.sets_completed for log in logs) / len(logs)
        avg_reps = sum(log.reps_completed for log in logs) / len(logs)

        weekly: Dict[int, float] = {}
        for log in logs:
            week = log.log_date.isocalendar()[1]
            weekly[week] = weekly.get(week, 0.0) + (
                log.sets_completed * log.reps_completed * (log.weight_used or 0.0)
            )
        volume_series = [weekly[w] for w in sorted(weekly.keys())]
        volume_trend_slope = _trend_slope(volume_series)

        ex_groups: Dict[int, List[Any]] = {}
        for log in sorted(logs, key=lambda l: (l.log_date, l.id)):
            if log.central_exercise_id:
                ex_groups.setdefault(log.central_exercise_id, []).append(log)

        progressions: List[ExerciseProgression] = []
        for ex_id, ex_logs in ex_groups.items():
            sessions = len(set(l.log_date for l in ex_logs))
            first = ex_logs[0]
            last = ex_logs[-1]
            first_vol = (
                first.sets_completed * first.reps_completed * (first.weight_used or 1.0)
            )
            last_vol = (
                last.sets_completed * last.reps_completed * (last.weight_used or 1.0)
            )
            pct = ((last_vol - first_vol) / first_vol * 100.0) if first_vol else 0.0
            progressions.append(
                ExerciseProgression(
                    exercise_name=f"Exercise #{ex_id}",
                    sessions_logged=sessions,
                    first_volume=round(first_vol, 2),
                    latest_volume=round(last_vol, 2),
                    progression_pct=round(pct, 1),
                )
            )

        self._resolve_exercise_names(progressions, ex_groups)
        progressions.sort(key=lambda p: abs(p.progression_pct), reverse=True)

        workout_plan = self.workout_plan_repo.get_active_plan(user_id)
        planned_sessions = None
        frequency_adherence_pct = None
        if workout_plan:
            spw = _parse_sessions_per_week(workout_plan.frequency)
            if spw:
                weeks = max(1.0, period_days / 7.0)
                planned_sessions = round(spw * weeks)
                frequency_adherence_pct = round(
                    (total_sessions / planned_sessions) * 100.0, 1
                )

        unique_exercises = len(
            set(log.central_exercise_id for log in logs if log.central_exercise_id)
        )

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

    def engineer_weight_features(
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

        start_weight = weights[0]
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

    def compute_overall_consistency(
        self,
        nutrition: NutritionFeatures,
        workout: WorkoutFeatures,
        weight: WeightFeatures,
    ) -> float:
        n_score = min(1.0, (nutrition.calorie_adherence_pct or 80.0) / 100.0)
        w_score = (
            min(1.0, (workout.frequency_adherence_pct or 0.0) / 100.0)
            if workout.total_sessions > 0
            else 0.0
        )
        wt_score = min(
            1.0, weight.measurements_count / max(1, nutrition.period_days / 7)
        )

        return round(n_score * 0.40 + w_score * 0.40 + wt_score * 0.20, 3)
