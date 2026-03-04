"""
test_cases.py — Synthetic test-case factories.

Generates (UserProfileDTO, WorkoutPreferencesDTO) and
(UserProfileDTO, NutritionPreferencesDTO) pairs with intentional constraint
coverage so every evaluator check is exercised at scale.

Workout segmentation  (n cases):
  First  25% : "No Equipment" profiles  →  probes equipment_compliance
  Next   25% : cardiac / joint conditions  →  probes injury & medical safety
  Last   50% : free variation across all dimensions

Nutrition segmentation  (n cases):
  First  33% : forced allergies  →  probes allergen_safety
  Next   33% : forced vegan/vegetarian  →  probes dietary_preference_respected
  Last   33% : free variation
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.ai_services.ai_coach.dtos import (
    NutritionPreferencesDTO,
    UserProfileDTO,
    WorkoutPreferencesDTO,
)

# ---------------------------------------------------------------------------
# Domain value pools
# ---------------------------------------------------------------------------

_GOALS = ["Lose Weight", "Build Muscle", "Maintain Fitness", "Improve Endurance"]
_GENDERS = ["Male", "Female"]
_ACTIVITY_LEVELS = ["Sedentary", "Lightly Active", "Moderately Active", "Very Active"]
_LOCATIONS = ["Home", "Gym", "Outdoor"]
_FOCUSES = ["Strength", "Cardio", "Flexibility", "Mixed"]
_DIFFICULTIES = ["Beginner", "Intermediate", "Advanced"]
_CUISINES = ["Any", "Mediterranean", "Asian", "Mexican", "Middle Eastern"]
_MEAL_COMPLEXITIES = ["Simple", "Moderate", "Complex"]
_CALORIE_PREFS = ["Deficit", "Maintenance", "Surplus", "Custom"]
_EQUIPMENT_LEVELS = ["No Equipment", "Basic Equipment", "Full Gym"]

_MEDICAL_CONDITIONS: List[Optional[str]] = [
    None, None,
    "Type 2 Diabetes",
    "Heart Disease",
    "Hypertension",
    "Osteoporosis",
    "Chronic Back Pain",
    "Asthma",
]
_INJURIES: List[Optional[str]] = [
    None, None,
    "Knee injury - avoid high impact exercises",
    "Lower back pain - avoid heavy lifting",
    "Shoulder injury - avoid overhead pressing",
    "Ankle sprain - avoid jumping",
]
_DIETARY_PREFERENCES: List[Optional[str]] = [
    None, "Vegan", "Vegetarian", "Keto", "Gluten-Free"
]
_ALLERGIES: List[Optional[str]] = [
    None, None,
    "Nuts and peanuts",
    "Dairy and lactose",
    "Gluten and wheat",
    "Shellfish",
    "Eggs",
    "Tomatoes",
]


# ---------------------------------------------------------------------------
# Shared profile builder
# ---------------------------------------------------------------------------

def _make_profile(i: int, overrides: Dict[str, Any]) -> UserProfileDTO:
    return UserProfileDTO(
        age=20 + (i * 3) % 50,
        gender=_GENDERS[i % len(_GENDERS)],
        height=float(155 + (i * 2) % 40),
        weight=float(55 + (i * 4) % 60),
        fitness_goal=_GOALS[i % len(_GOALS)],
        activity_level=_ACTIVITY_LEVELS[i % len(_ACTIVITY_LEVELS)],
        dietary_preference=overrides.get(
            "dietary_preference", _DIETARY_PREFERENCES[i % len(_DIETARY_PREFERENCES)]
        ),
        medical_conditions=overrides.get(
            "medical_conditions", _MEDICAL_CONDITIONS[i % len(_MEDICAL_CONDITIONS)]
        ),
        allergies=_ALLERGIES[i % len(_ALLERGIES)],
        injuries=overrides.get("injuries", _INJURIES[i % len(_INJURIES)]),
        medications=None,
    )


# ---------------------------------------------------------------------------
# Workout test cases
# ---------------------------------------------------------------------------

def make_workout_test_cases(
    n: int,
) -> List[Tuple[UserProfileDTO, WorkoutPreferencesDTO]]:
    cases = []
    no_equipment_end = n // 4
    safety_end = n // 2

    _SAFETY_POOL = [
        "Heart Disease",
        "Knee injury - avoid high impact exercises",
        "Ankle sprain - avoid jumping",
        "Heart Disease - Cardiac Condition",
        "Lower back pain - avoid heavy lifting",
        "Shoulder injury - avoid overhead pressing",
    ]

    for i in range(n):
        if i < no_equipment_end:
            equipment = "No Equipment"
            location = _LOCATIONS[i % 2]
            overrides: Dict[str, Any] = {}
        elif i < safety_end:
            equipment = _EQUIPMENT_LEVELS[i % len(_EQUIPMENT_LEVELS)]
            location = _LOCATIONS[i % len(_LOCATIONS)]
            overrides = {"medical_conditions": _SAFETY_POOL[i % len(_SAFETY_POOL)]}
        else:
            equipment = _EQUIPMENT_LEVELS[i % len(_EQUIPMENT_LEVELS)]
            location = _LOCATIONS[i % len(_LOCATIONS)]
            overrides = {}

        profile = _make_profile(i, overrides)
        prefs = WorkoutPreferencesDTO(
            workout_days_per_week=min(3 + (i % 4), 6),
            workout_location=location,
            equipment_availability=equipment,
            workout_focus=_FOCUSES[i % len(_FOCUSES)],
            workout_difficulty=_DIFFICULTIES[i % len(_DIFFICULTIES)],
            session_duration_minutes=30 + (i * 5) % 61,
            focus_areas=None,
        )
        cases.append((profile, prefs))
    return cases


# ---------------------------------------------------------------------------
# Nutrition test cases
# ---------------------------------------------------------------------------

def make_nutrition_test_cases(
    n: int,
) -> List[Tuple[UserProfileDTO, NutritionPreferencesDTO]]:
    cases = []
    allergy_end = n // 3
    diet_end = 2 * n // 3

    _ALLERGY_POOL = [
        "Nuts and peanuts",
        "Dairy and lactose",
        "Gluten and wheat",
        "Shellfish",
        "Eggs",
        "Tomatoes",
    ]

    for i in range(n):
        if i < allergy_end:
            allergy_val: Optional[str] = _ALLERGY_POOL[i % len(_ALLERGY_POOL)]
            overrides: Dict[str, Any] = {}
        elif i < diet_end:
            allergy_val = _ALLERGIES[i % len(_ALLERGIES)]
            overrides = {"dietary_preference": ["Vegan", "Vegetarian"][i % 2]}
        else:
            allergy_val = _ALLERGIES[i % len(_ALLERGIES)]
            overrides = {}

        profile = _make_profile(i, overrides)
        profile = profile.model_copy(update={"allergies": allergy_val})

        # Mirror allergy into exclude_ingredients for maximum strictness
        exclude: List[str] = []
        if allergy_val:
            if "Nuts" in allergy_val:
                exclude.extend(["peanuts", "almonds", "cashews", "walnuts", "peanut butter"])
            if "Dairy" in allergy_val:
                exclude.extend(["milk", "cheese", "butter", "cream", "yogurt", "ghee"])
            if "Gluten" in allergy_val:
                exclude.extend(["wheat", "bread", "pasta", "flour", "soy sauce"])
            if "Shellfish" in allergy_val:
                exclude.extend(["shrimp", "lobster", "crab", "prawns", "seafood stock"])
            if "Eggs" in allergy_val:
                exclude.extend(["egg", "eggs", "mayonnaise", "hollandaise"])
            if "Tomatoes" in allergy_val:
                exclude.extend(["tomato", "tomatoes", "marinara", "ketchup", "tomato sauce"])

        cal_pref = _CALORIE_PREFS[i % len(_CALORIE_PREFS)]
        custom_cal: Optional[int] = (1800 + (i * 50) % 1200) if cal_pref == "Custom" else None

        prefs = NutritionPreferencesDTO(
            calorie_preference=cal_pref,
            custom_calorie_target=custom_cal,
            meals_per_day=min(3 + (i % 4), 6),
            meal_complexity=_MEAL_COMPLEXITIES[i % len(_MEAL_COMPLEXITIES)],
            cuisine_preference=_CUISINES[i % len(_CUISINES)],
            exclude_ingredients=exclude if exclude else None,
        )
        cases.append((profile, prefs))
    return cases
