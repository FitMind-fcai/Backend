"""
Plan Generation Routes — Generate & Save (two-step flow)

Flow:
  1. POST /plans/generate/workout  → AI generates draft, NOT saved to DB
  2. POST /plans/save/workout      → User confirms → draft is persisted → WorkoutPlanResponse

  Same for nutrition:
  1. POST /plans/generate/nutrition → AI generates draft, NOT saved to DB
  2. POST /plans/save/nutrition     → User confirms → draft is persisted → NutritionPlanResponse

  GET /plans/active → currently active workout + nutrition plan.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.auth_module.models.user import User
from app.auth_module.core.dependencies import get_current_verified_user
from app.profile_module.services.profile_service import ProfileService
from app.profile_module.core.dependencies import get_profile_service
from app.planning_module.core.dependencies import get_plan_generation_service
from app.planning_module.services.plan_generation_service import PlanGenerationService
from app.planning_module.schemas.plan import (
    WorkoutPlanGenerationRequest,
    NutritionPlanGenerationRequest,
    WorkoutPlanDraftResponse,
    WorkoutPlanSaveRequest,
    WorkoutPlanResponse,
    NutritionPlanDraftResponse,
    NutritionPlanSaveRequest,
    NutritionPlanResponse,
    CombinedPlanResponse,
    CombinedPlanGenerationRequest,
    CombinedPlanDraftResponse,
)

plan_generation_router = APIRouter(prefix="/plans", tags=["Plan Generation"])


# ────────────────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────────────────

def _require_complete_profile(profile):
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not found. Please create your profile first.",
        )
    if not all([
        profile.age, profile.gender, profile.height,
        profile.weight, profile.fitness_goal, profile.activity_level,
    ]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete profile. Please complete all required fields "
                   "(age, gender, height, weight, fitness goal, activity level).",
        )


# ────────────────────────────────────────────────────────────────────────────────
# WORKOUT — GENERATE
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.post(
    "/generate/workout",
    response_model=WorkoutPlanDraftResponse,
    summary="Generate Workout Plan Draft (AI only, not saved)"
)
def generate_workout_plan(
    request: WorkoutPlanGenerationRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    **Step 1 of 2** — Use AI to generate a workout plan draft.

    The plan is **NOT saved** to the database. Review the `draft_plan` returned,
    then send the entire response body to `POST /plans/save/workout` to persist it.

    If the user already has an active workout plan, the AI uses it as context to
    generate an improved or adjusted version — the old plan is **not deleted** until
    the user explicitly saves the new one.

    **Workout Preferences:**
    - `workout_location`: Gym | Home | Outdoor | Hybrid
    - `equipment_availability`: Full Gym Equipment | Basic Equipment | No Equipment
    - `workout_focus`: Strength Training | Cardiovascular | Flexibility | Hybrid | Sport Specific
    - `workout_difficulty`: Beginner | Intermediate | Advanced
    - `workout_days_per_week`: 1–7
    - `session_duration_minutes`: 15–180
    - `focus_areas`: optional list of muscle groups

    **Localization (`lang`):**
    - `"en"` *(default)* — all plan text fields (plan name, day names, notes, exercise instructions) are written in English.
    - `"ar"` — all plan text fields are written in Arabic.
    - The `language` field in the returned draft and in the saved plan record reflects this value.
    - Exercise names from the catalog (`central_exercise.name`) are always in English regardless of `lang` — exercise names are internationally standardized.
    """
    profile = profile_service.get_profile_by_user_id(current_user.id)
    _require_complete_profile(profile)

    try:
        draft = plan_service.generate_workout_plan(
            profile=profile,
            preferences=request.workout_preferences,
            duration_weeks=request.duration_weeks,
            lang=request.lang,
        )
    except ValueError as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return WorkoutPlanDraftResponse(**draft)


# ────────────────────────────────────────────────────────────────────────────────
# WORKOUT — SAVE
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.post(
    "/save/workout",
    response_model=WorkoutPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save Workout Plan Draft to Database"
)
def save_workout_plan(
    request: WorkoutPlanSaveRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    **Step 2 of 2** — Confirm and persist a previously generated workout plan draft.

    Send the exact body you received from `POST /plans/generate/workout`.
    If `update_plan_id` is set, the existing plan's days and exercises are deleted
    and replaced with the new data. Returns the full saved `WorkoutPlanResponse` with IDs.

    The `language` field inside `draft_plan` (set automatically by the generate step) is
    saved to the database and returned in the response — the frontend can use it to know
    which language this plan was generated in.
    """
    profile = profile_service.get_profile_by_user_id(current_user.id)
    _require_complete_profile(profile)

    try:
        saved = plan_service.save_workout_plan(
            user_id=current_user.id,
            profile_id=profile.id,
            plan_create=request.draft_plan,
            generated_from_preferences=request.generated_from_preferences,
            update_plan_id=request.update_plan_id,
        )
    except ValueError as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return WorkoutPlanResponse.model_validate(saved)


# ────────────────────────────────────────────────────────────────────────────────
# NUTRITION — GENERATE
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.post(
    "/generate/nutrition",
    response_model=NutritionPlanDraftResponse,
    summary="Generate Nutrition Plan Draft (AI only, not saved)"
)
def generate_nutrition_plan(
    request: NutritionPlanGenerationRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    **Step 1 of 2** — Use AI to generate a 7-day nutrition plan draft.

    The plan is **NOT saved** to the database. Review the `draft_plan` returned
    (days → meals → ingredients), then send the entire response body to
    `POST /plans/save/nutrition` to persist it.

    If the user already has an active nutrition plan, the AI uses it as context —
    the old plan is **not deleted** until the user explicitly saves the new one.

    **Nutrition Preferences:**
    - `calorie_preference`: Auto | Custom
    - `custom_calorie_target`: 1000–5000 (required when Custom)
    - `meals_per_day`: 3–6
    - `meal_complexity`: Quick | Moderate | Elaborate | Mixed
    - `cuisine_preference`: Mediterranean | Asian | Western | Middle Eastern | Latin American | Vegetarian | Vegan | Mixed
    - `exclude_ingredients`: optional list of ingredients to avoid

    **Localization (`lang`):**
    - `"en"` *(default)* — all plan text fields (plan name, day names, meal names, cooking instructions, notes) are written in English.
    - `"ar"` — all plan text fields are written in Arabic.
    - The `language` field in the returned draft and in the saved plan record reflects this value.
    - Each ingredient in the response includes both `food_name` (English, always present) and `food_name_ar` (Arabic, may be `null` if no Arabic name exists in the catalog). The frontend should display `food_name_ar` when `lang=ar` and fall back to `food_name` when it is `null`.
    - Food IDs (`central_food_id`) are language-neutral — the same catalog records are used regardless of `lang`.
    """
    profile = profile_service.get_profile_by_user_id(current_user.id)
    _require_complete_profile(profile)

    try:
        draft = plan_service.generate_nutrition_plan(
            profile=profile,
            preferences=request.nutrition_preferences,
            duration_weeks=request.duration_weeks,
            lang=request.lang,
        )
    except ValueError as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return NutritionPlanDraftResponse(**draft)


# ────────────────────────────────────────────────────────────────────────────────
# NUTRITION — SAVE
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.post(
    "/save/nutrition",
    response_model=NutritionPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save Nutrition Plan Draft to Database"
)
def save_nutrition_plan(
    request: NutritionPlanSaveRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    **Step 2 of 2** — Confirm and persist a previously generated nutrition plan draft.

    Send the exact body you received from `POST /plans/generate/nutrition`.
    If `update_plan_id` is set, the existing plan's days, meals and ingredients are
    deleted and replaced with the new data. Returns the full saved `NutritionPlanResponse` with IDs.

    The `language` field inside `draft_plan` (set automatically by the generate step) is
    saved to the database and returned in the response. Each ingredient in the saved plan
    includes `food_name` (English) and `food_name_ar` (Arabic, nullable) for bilingual display.
    """
    profile = profile_service.get_profile_by_user_id(current_user.id)
    _require_complete_profile(profile)

    try:
        saved = plan_service.save_nutrition_plan(
            user_id=current_user.id,
            profile_id=profile.id,
            plan_create=request.draft_plan,
            generated_from_preferences=request.generated_from_preferences,
            update_plan_id=request.update_plan_id,
        )
    except ValueError as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return NutritionPlanResponse.model_validate(saved)


# ────────────────────────────────────────────────────────────────────────────────
# COMBINED — GENERATE BOTH PLANS CONCURRENTLY
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.post(
    "/generate/combined",
    response_model=CombinedPlanDraftResponse,
    summary="Generate Workout + Nutrition Plan Drafts Concurrently (AI only, not saved)",
)
def generate_combined_plans(
    request: CombinedPlanGenerationRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    **Step 1 of 2 (combined)** — Generate both a workout plan draft and a nutrition plan draft
    in a single request. Both LLM generations run **concurrently**, cutting total wait time
    roughly in half compared to calling the two separate generate endpoints back-to-back.

    Neither plan is saved to the database. After reviewing the response:
    - Send `workout_draft` to `POST /plans/save/workout` to persist the workout plan.
    - Send `nutrition_draft` to `POST /plans/save/nutrition` to persist the nutrition plan.

    **Localization (`lang`):**
    - `"en"` *(default)* — both plans are generated in English.
    - `"ar"` — both plans are generated in Arabic. The single `lang` value applies to both the workout and nutrition plan.
    - All localization rules from the individual generate endpoints apply here (see `/plans/generate/workout` and `/plans/generate/nutrition` for details).
    """
    profile = profile_service.get_profile_by_user_id(current_user.id)
    _require_complete_profile(profile)

    try:
        result = plan_service.generate_combined_plans(
            profile=profile,
            workout_preferences=request.workout_preferences,
            nutrition_preferences=request.nutrition_preferences,
            duration_weeks=request.duration_weeks,
            lang=request.lang,
        )
    except ValueError as exc:
        import traceback, logging
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return CombinedPlanDraftResponse(
        workout_draft=WorkoutPlanDraftResponse(**result["workout_draft"]),
        nutrition_draft=NutritionPlanDraftResponse(**result["nutrition_draft"]),
    )


# ────────────────────────────────────────────────────────────────────────────────
# ACTIVE PLANS
# ────────────────────────────────────────────────────────────────────────────────

@plan_generation_router.get(
    "/active",
    response_model=CombinedPlanResponse,
    summary="Get Current Active Workout & Nutrition Plans"
)
def get_active_plans(
    current_user: User = Depends(get_current_verified_user),
    plan_service: PlanGenerationService = Depends(get_plan_generation_service),
):
    """
    Returns the currently active workout plan and nutrition plan for the user
    (both with full details — days, exercises/meals, ingredients).
    Either field can be `null` if no active plan of that type exists.
    """
    return plan_service.get_user_active_plans(current_user.id)
