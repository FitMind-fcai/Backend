import logging
from typing import Dict, Optional

from app.ai_services.ai_coach.dtos import UserProfileDTO
from app.profile_module.models.enums import (
    FitnessGoal,
    ActivityLevel,
    Gender as _Gender,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence-based constants (Mifflin-St Jeor / ACSM)
# ---------------------------------------------------------------------------

GOAL_ALIASES: Dict[str, str] = {
    FitnessGoal.LOSE_WEIGHT.value: "lose weight",
    FitnessGoal.GET_BULKS.value: "build muscle",
    FitnessGoal.IMPROVE_ENDURANCE.value: "improve fitness",
    FitnessGoal.TRY_AI_COACH.value: "maintain",
}

ACTIVITY_MULTIPLIERS: Dict[str, float] = {
    ActivityLevel.SEDENTARY.value: 1.20,
    ActivityLevel.LIGHTLY_ACTIVE.value: 1.375,
    ActivityLevel.MODERATELY_ACTIVE.value: 1.55,
    ActivityLevel.VERY_ACTIVE.value: 1.725,
    ActivityLevel.EXTRA_ACTIVE.value: 1.90,
}

GOAL_CALORIE_DELTA: Dict[str, int] = {
    "build muscle": +450,
    "lose weight": -400,
    "maintain": 0,
    "improve fitness": 0,
}

GOAL_PROTEIN_PER_KG: Dict[str, float] = {
    "build muscle": 1.8,
    "lose weight": 1.6,
    "maintain": 1.4,
    "improve fitness": 1.4,
}

GOAL_FAT_PCT: Dict[str, float] = {
    "build muscle": 0.28,
    "lose weight": 0.30,
    "maintain": 0.28,
    "improve fitness": 0.28,
}


# ---------------------------------------------------------------------------
# Pure calculation functions
# ---------------------------------------------------------------------------


def normalize_goal(raw_goal) -> str:
    val = raw_goal.value if hasattr(raw_goal, "value") else str(raw_goal or "")
    return GOAL_ALIASES.get(val, "maintain")


def calculate_tdee(user_profile: UserProfileDTO) -> float:
    weight = user_profile.weight or 70.0
    height = user_profile.height or 170.0
    age = user_profile.age or 25

    gender_val = user_profile.gender
    gender_val = (
        gender_val.value if hasattr(gender_val, "value") else str(gender_val or "")
    )
    if gender_val == _Gender.FEMALE.value:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5

    act_val = user_profile.activity_level
    act_val = act_val.value if hasattr(act_val, "value") else str(act_val or "")
    multiplier = ACTIVITY_MULTIPLIERS.get(act_val, 1.375)
    return round(bmr * multiplier, 1)


def calculate_target_calories(
    user_profile: UserProfileDTO,
    custom_target: Optional[int],
) -> int:
    if custom_target:
        return int(custom_target)

    tdee = calculate_tdee(user_profile)
    goal = normalize_goal(user_profile.fitness_goal)
    delta = GOAL_CALORIE_DELTA.get(goal, 0)
    target = int(tdee + delta)
    target = max(1200, min(target, 5000))

    logger.info(
        "🔢 Calorie guidance — goal=%s TDEE=%.0f delta=%+d target=%d kcal",
        goal,
        tdee,
        delta,
        target,
    )
    return target


def calculate_macro_guidance(
    user_profile: UserProfileDTO,
    target_calories: int,
) -> Dict[str, int]:
    goal = normalize_goal(user_profile.fitness_goal)
    weight = user_profile.weight or 70.0

    protein_g = round(weight * GOAL_PROTEIN_PER_KG.get(goal, 1.4))
    fat_pct = GOAL_FAT_PCT.get(goal, 0.28)
    fat_g = round((target_calories * fat_pct) / 9)
    carb_g = max(50, round((target_calories - protein_g * 4 - fat_g * 9) / 4))

    return {"protein_g": protein_g, "fat_g": fat_g, "carb_g": carb_g}
