"""
Plan validation — schema conformance and semantic safety checks.

Two layers:
  1. Schema validation  — Pydantic model_validate on the raw LLM JSON dict.
  2. Semantic gate      — Dynamic allergen scan on the final NutritionPlanDTO.

Both are pure functions with no I/O or LLM calls.
"""
import logging
import re
from typing import Any, Dict, List

from pydantic import ValidationError

from app.ai_services.ai_coach.dtos import (
    NutritionPlanDTO,
    UserProfileDTO,
    WorkoutPlanDTO,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allergen family expansions
# ---------------------------------------------------------------------------

_FAMILY_EXPANSIONS: Dict[str, List[str]] = {
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "clam", "oyster", "mussel", "scallop", "crawfish"],
    "tree nut":  ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut"],
    "treenut":   ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut"],
    "dairy":     ["milk", "cheese", "butter", "cream", "yogurt", "whey", "lactose", "casein"],
    "milk":      ["milk", "cheese", "butter", "cream", "yogurt", "whey", "lactose", "casein"],
    "gluten":    ["wheat", "barley", "rye", "spelt", "kamut", "triticale"],
    "soy":       ["soy", "tofu", "edamame", "tempeh", "miso"],
    "peanut":    ["peanut"],
    "egg":       ["egg"],
    "fish":      ["salmon", "tuna", "cod", "tilapia", "mackerel", "sardine", "herring", "trout", "bass", "halibut"],
    "sesame":    ["sesame", "tahini"],
    "mustard":   ["mustard"],
    "celery":    ["celery"],
    "lupin":     ["lupin", "lupine"],
    "mollusc":   ["squid", "octopus", "snail", "clam", "oyster", "mussel", "scallop"],
    "sulphite":  ["wine", "dried fruit", "pickled"],
}


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _format_validation_error(error: ValidationError) -> str:
    details = []
    for item in error.errors():
        loc = ".".join(str(p) for p in item.get("loc", []))
        msg = item.get("msg", "invalid value")
        details.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(details)


def validate_nutrition_plan(plan_data: Dict[str, Any]) -> NutritionPlanDTO:
    if not isinstance(plan_data, dict):
        raise ValueError("Nutrition plan response must be a JSON object")
    try:
        return NutritionPlanDTO.model_validate(plan_data)
    except ValidationError as err:
        raise ValueError(
            f"Nutrition plan schema validation failed: {_format_validation_error(err)}"
        ) from err


def validate_workout_plan(plan_data: Dict[str, Any]) -> WorkoutPlanDTO:
    if not isinstance(plan_data, dict):
        raise ValueError("Workout plan response must be a JSON object")
    try:
        return WorkoutPlanDTO.model_validate(plan_data)
    except ValidationError as err:
        raise ValueError(
            f"Workout plan schema validation failed: {_format_validation_error(err)}"
        ) from err


# ---------------------------------------------------------------------------
# Semantic allergy gate
# ---------------------------------------------------------------------------

def validate_nutrition_semantics(
    plan: NutritionPlanDTO,
    user_profile: UserProfileDTO,
) -> None:
    """
    Dynamic allergen scan on the finalised plan.

    Parses the free-text allergies field (any format, any allergen),
    expands umbrella terms to their constituent ingredients, then checks
    every ingredient's food_name in the plan. Raises ValueError on any hit.

    This runs after schema validation as a last-resort safety net;
    the primary enforcement happens at generation time via the prompt.
    Macro/calorie accuracy is NOT checked here — the backend recomputes
    those from CentralFood DB records.
    """
    allergy_str = (user_profile.allergies or "").lower().strip()
    if not allergy_str or allergy_str == "none":
        return

    raw_allergens = re.split(r"[,;/&\n]+|\band\b|\bor\b", allergy_str)
    base_keywords: List[str] = [
        a.strip() for a in raw_allergens if a.strip() and a.strip() != "none"
    ]

    allergen_keywords: List[str] = list(base_keywords)
    for kw in base_keywords:
        for family, members in _FAMILY_EXPANSIONS.items():
            if family in kw:
                allergen_keywords.extend(members)

    allergen_keywords = list(set(allergen_keywords))

    violations: List[str] = []
    for day in plan.days:
        for meal in day.meals:
            for ing in (meal.ingredients or []):
                food_name = (getattr(ing, "food_name", None) or "").lower()
                for kw in allergen_keywords:
                    if kw and kw in food_name:
                        msg = (
                            f"Day {day.day_number} — {meal.meal_name}: "
                            f"ingredient '{getattr(ing, 'food_name', ing)}' "
                            f"contains allergen '{kw}'"
                        )
                        violations.append(msg)
                        logger.error("ALLERGY VIOLATION: %s", msg)

    if violations:
        raise ValueError(
            "Nutrition plan rejected — allergy violations detected:\n"
            + "\n".join(violations)
        )
