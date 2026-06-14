from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Union

from app.profile_module.models.enums import FitnessGoal, ActivityLevel, Gender

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ev(v) -> str:
    """Return the string value of an enum instance or a plain string."""
    return v.value if hasattr(v, "value") else str(v)


# ---------------------------------------------------------------------------
# Lookup tables — keyed by exact enum .value strings, no lowercase guessing
# ---------------------------------------------------------------------------

GOAL_MAP: Dict[str, str] = {
    FitnessGoal.LOSE_WEIGHT.value:       "lose_weight",
    FitnessGoal.GET_BULKS.value:         "build_muscle",
    FitnessGoal.IMPROVE_ENDURANCE.value: "improve_fitness",
    FitnessGoal.TRY_AI_COACH.value:      "maintain",
}

ACTIVITY_MAP: Dict[str, float] = {
    ActivityLevel.SEDENTARY.value:         1.20,
    ActivityLevel.LIGHTLY_ACTIVE.value:    1.375,
    ActivityLevel.MODERATELY_ACTIVE.value: 1.55,
    ActivityLevel.VERY_ACTIVE.value:       1.725,
    ActivityLevel.EXTRA_ACTIVE.value:      1.90,
}

GOAL_CALORIE_DELTA: Dict[str, int] = {
    "build_muscle":    +450,
    "lose_weight":     -400,
    "maintain":           0,
    "improve_fitness":    0,
}

GOAL_PROTEIN_PER_KG: Dict[str, float] = {
    "build_muscle":    1.8,
    "lose_weight":     1.6,
    "maintain":        1.4,
    "improve_fitness": 1.4,
}

GOAL_FAT_PCT: Dict[str, float] = {
    "build_muscle":    0.28,
    "lose_weight":     0.30,
    "maintain":        0.28,
    "improve_fitness": 0.28,
}

# Recommended training days by goal (min, max)
GOAL_TRAINING_DAYS: Dict[str, tuple] = {
    "build_muscle":    (3, 5),
    "lose_weight":     (3, 5),
    "maintain":        (2, 4),
    "improve_fitness": (3, 5),
}

# Training split by goal + days/week
GOAL_SPLIT: Dict[str, Dict[int, str]] = {
    "build_muscle": {
        2: "full_body",
        3: "full_body",
        4: "upper_lower",
        5: "push_pull_legs",
        6: "push_pull_legs",
    },
    "lose_weight": {
        2: "full_body",
        3: "full_body",
        4: "full_body",
        5: "upper_lower",
        6: "upper_lower",
    },
    "maintain": {
        2: "full_body",
        3: "full_body",
        4: "upper_lower",
        5: "upper_lower",
        6: "upper_lower",
    },
    "improve_fitness": {
        2: "full_body",
        3: "full_body",
        4: "full_body",
        5: "upper_lower",
        6: "upper_lower",
    },
}

GOAL_VOLUME_SETS_PER_MUSCLE: Dict[str, int] = {
    "build_muscle":    16,
    "lose_weight":     10,
    "maintain":        10,
    "improve_fitness": 12,
}


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NutritionTargets:
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    meals_per_day: int
    tdee: float

    def to_prompt_block(self) -> str:
        protein_pct = round(self.protein_g * 4 / max(self.calories, 1) * 100)
        fat_pct     = round(self.fat_g     * 9 / max(self.calories, 1) * 100)
        carb_pct    = round(self.carbs_g   * 4 / max(self.calories, 1) * 100)
        return (
            "PRE-COMPUTED NUTRITION TARGETS (computed by Planning Engine — do NOT recalculate):\n"
            f"  TDEE               : {self.tdee:.0f} kcal/day (maintenance baseline)\n"
            f"  Target calories    : {self.calories} kcal/day\n"
            f"  Protein target     : {self.protein_g} g/day  ({protein_pct}% of calories)\n"
            f"  Fat target         : {self.fat_g} g/day  ({fat_pct}% of calories)\n"
            f"  Carbohydrate target: {self.carbs_g} g/day ({carb_pct}% of calories)\n"
            f"  Meals per day      : {self.meals_per_day}\n\n"
            "YOUR JOB: Choose ingredient amounts (amount_g) so that the daily total for each\n"
            "meal group lands within ±10% of these targets.\n"
            "Do NOT write calorie or macro numbers into JSON — the backend recomputes from DB records."
        )


@dataclass
class TrainingTargets:
    training_days: int
    split: str
    session_duration_minutes: int
    weekly_volume_sets_per_muscle: int
    goal: str

    def to_prompt_block(self) -> str:
        return (
            "PRE-COMPUTED TRAINING TARGETS (computed by Planning Engine — do NOT recalculate):\n"
            f"  Training days/week      : {self.training_days}\n"
            f"  Training split          : {self.split.replace('_', ' ').title()}\n"
            f"  Session duration        : {self.session_duration_minutes} minutes\n"
            f"  Weekly volume target    : ~{self.weekly_volume_sets_per_muscle} sets per muscle group\n\n"
            "Follow this split EXACTLY. Do NOT change the number of training days or the split type.\n"
            "YOUR JOB: Select exercises that fit this structure, write instructions, and explain decisions."
        )


@dataclass
class PlanningEngineOutput:
    goal: str
    nutrition: NutritionTargets
    training: TrainingTargets

    def to_dict(self) -> dict:
        return {
            "goal":          self.goal,
            "calories":      self.nutrition.calories,
            "protein_g":     self.nutrition.protein_g,
            "fat_g":         self.nutrition.fat_g,
            "carbs_g":       self.nutrition.carbs_g,
            "training_days": self.training.training_days,
            "split":         self.training.split,
        }


# ---------------------------------------------------------------------------
# Planning Engine
# ---------------------------------------------------------------------------

class PlanningEngine:
    """
    Deterministic planning engine that computes macro and training parameters
    from user profile data BEFORE the LLM is invoked.

    Accepts the actual profile enum types (FitnessGoal, ActivityLevel, Gender)
    directly — no string-lowercasing or alias guessing needed.
    """

    def compute(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        gender: Union[Gender, str],
        activity_level: Union[ActivityLevel, str],
        fitness_goal: Union[FitnessGoal, str],
        training_days_per_week: int = 4,
        session_duration_minutes: int = 60,
        custom_calorie_target: Optional[int] = None,
        meals_per_day: int = 3,
    ) -> PlanningEngineOutput:
        goal = self._normalize_goal(fitness_goal)
        tdee = self._calculate_tdee(weight_kg, height_cm, age, gender, activity_level)
        nutrition = self._compute_nutrition(
            weight_kg, tdee, goal, custom_calorie_target, meals_per_day
        )
        training = self._compute_training(goal, training_days_per_week, session_duration_minutes)

        logger.info(
            "PlanningEngine — goal=%s calories=%d protein=%dg fat=%dg carbs=%dg days=%d split=%s",
            goal,
            nutrition.calories,
            nutrition.protein_g,
            nutrition.fat_g,
            nutrition.carbs_g,
            training.training_days,
            training.split,
        )

        return PlanningEngineOutput(goal=goal, nutrition=nutrition, training=training)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_goal(self, raw_goal: Union[FitnessGoal, str]) -> str:
        """Map a FitnessGoal enum (or its string value) to an internal goal key."""
        val = _ev(raw_goal)
        goal = GOAL_MAP.get(val)
        if goal is None:
            logger.warning(
                "PlanningEngine: unknown fitness_goal value %r — defaulting to 'maintain'. "
                "Add it to GOAL_MAP in planning_engine.py.",
                val,
            )
            goal = "maintain"
        return goal

    def _calculate_tdee(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        gender: Union[Gender, str],
        activity_level: Union[ActivityLevel, str],
    ) -> float:
        """Mifflin-St Jeor BMR × activity multiplier."""
        gen_val = _ev(gender)
        if gen_val == Gender.FEMALE.value:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        else:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5

        act_val    = _ev(activity_level)
        multiplier = ACTIVITY_MAP.get(act_val)
        if multiplier is None:
            logger.warning(
                "PlanningEngine: unknown activity_level value %r — defaulting to 1.375. "
                "Add it to ACTIVITY_MAP in planning_engine.py.",
                act_val,
            )
            multiplier = 1.375

        return round(bmr * multiplier, 1)

    def _compute_nutrition(
        self,
        weight_kg: float,
        tdee: float,
        goal: str,
        custom_calorie_target: Optional[int],
        meals_per_day: int,
    ) -> NutritionTargets:
        if custom_calorie_target:
            calories = int(custom_calorie_target)
        else:
            delta    = GOAL_CALORIE_DELTA.get(goal, 0)
            calories = int(tdee + delta)
            calories = max(1200, min(calories, 5000))

        protein_g = round(weight_kg * GOAL_PROTEIN_PER_KG.get(goal, 1.4))
        fat_pct   = GOAL_FAT_PCT.get(goal, 0.28)
        fat_g     = round((calories * fat_pct) / 9)
        carbs_g   = max(50, round((calories - protein_g * 4 - fat_g * 9) / 4))

        return NutritionTargets(
            calories=calories,
            protein_g=protein_g,
            fat_g=fat_g,
            carbs_g=carbs_g,
            meals_per_day=meals_per_day,
            tdee=tdee,
        )

    def _compute_training(
        self,
        goal: str,
        training_days: int,
        session_duration_minutes: int,
    ) -> TrainingTargets:
        min_days, max_days = GOAL_TRAINING_DAYS.get(goal, (3, 5))
        training_days = max(min_days, min(max_days, training_days))

        split_map = GOAL_SPLIT.get(goal, {})
        split     = split_map.get(training_days, "full_body")

        weekly_volume = GOAL_VOLUME_SETS_PER_MUSCLE.get(goal, 10)

        return TrainingTargets(
            training_days=training_days,
            split=split,
            session_duration_minutes=session_duration_minutes,
            weekly_volume_sets_per_muscle=weekly_volume,
            goal=goal,
        )
