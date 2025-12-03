"""
Plan Generation Routes.
Handles AI-powered generation and regeneration of workout and nutrition plans.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.auth_module.models.user import User
from app.auth_module.core.dependencies import get_current_verified_user
from app.profile_module.services.profile_service import ProfileService
from app.profile_module.core.dependencies import get_profile_service
from app.planning_module.services.plan_generation_service import PlanGenerationService
from app.planning_module.schemas.plan import (
    WorkoutPlanGenerationRequest,
    NutritionPlanGenerationRequest,
    WorkoutPlanResponse,
    NutritionPlanResponse,
    CombinedPlanResponse
)


plan_generation_router = APIRouter(prefix="/plans", tags=["Plan Generation"])


@plan_generation_router.post("/generate/workout", response_model=WorkoutPlanResponse)
def generate_workout_plan(
    request: WorkoutPlanGenerationRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    db: Session = Depends(get_db)
):
    """
    Generate or update workout plan using AI based on user profile and preferences.
    
    **Smart Generation:**
    - **If no plan exists**: Creates a new personalized workout plan from scratch
    - **If plan exists**: Updates it intelligently using the existing plan as reference
      - AI analyzes your EXISTING plan and NEW preferences
      - KEEPS exercises that still match your requirements
      - ONLY CHANGES exercises that conflict with new preferences
      - Maintains progression and familiarity where possible
    
    **Example Use Cases:**
    - First time → Creates new workout plan
    - Changed gym to home workouts → Updates equipment only
    - New focus area (e.g., strength to cardio) → Adjusts exercises
    - Different difficulty level → Modifies intensity
    - Already have nutrition plan → Creates workout plan (keeps nutrition)
    
    **Requirements:**
    - User must have a verified account
    - User must have a complete profile with required fields
    - Workout preferences must be provided
    """
    # Get user profile
    profile = profile_service.get_profile_by_user_id(current_user.id)
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not found. Please create your profile first before generating plans."
        )
    
    # Validate profile completeness
    if not all([profile.age, profile.gender, profile.height, profile.weight, profile.fitness_goal, profile.activity_level]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete profile. Please complete all required fields (age, gender, height, weight, fitness goal, activity level)."
        )
    
    # Generate workout plan
    plan_service = PlanGenerationService(db)
    workout_plan = plan_service.generate_workout_plan(
        profile=profile,
        preferences=request.workout_preferences,
        duration_weeks=request.duration_weeks
    )
    
    return WorkoutPlanResponse.model_validate(workout_plan)


@plan_generation_router.post("/generate/nutrition", response_model=NutritionPlanResponse)
def generate_nutrition_plan(
    request: NutritionPlanGenerationRequest,
    current_user: User = Depends(get_current_verified_user),
    profile_service: ProfileService = Depends(get_profile_service),
    db: Session = Depends(get_db)
):
    """
    Generate or update nutrition plan using AI based on user profile and preferences.
    
    **Smart Generation:**
    - **If no plan exists**: Creates a new personalized nutrition plan from scratch
    - **If plan exists**: Updates it intelligently using the existing plan as reference
      - AI analyzes your EXISTING plan and NEW preferences
      - KEEPS meals that still match your requirements
      - ONLY CHANGES meals that conflict with new preferences
      - Maintains dietary preferences and familiarity where possible
    
    **Example Use Cases:**
    - First time → Creates new nutrition plan
    - Adjusted calorie target → Modifies portions, not entire meals
    - New dietary restriction → Replaces only conflicting meals
    - Different cuisine preference → Updates meal types
    - Already have workout plan → Creates nutrition plan (keeps workout)
    
    **Requirements:**
    - User must have a verified account
    - User must have a complete profile with required fields
    - Nutrition preferences must be provided
    """
    # Get user profile
    profile = profile_service.get_profile_by_user_id(current_user.id)
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not found. Please create your profile first before generating plans."
        )
    
    # Validate profile completeness
    if not all([profile.age, profile.gender, profile.height, profile.weight, profile.fitness_goal, profile.activity_level]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete profile. Please complete all required fields (age, gender, height, weight, fitness goal, activity level)."
        )
    
    # Generate nutrition plan
    plan_service = PlanGenerationService(db)
    nutrition_plan = plan_service.generate_nutrition_plan(
        profile=profile,
        preferences=request.nutrition_preferences,
        duration_weeks=request.duration_weeks
    )
    
    return NutritionPlanResponse.model_validate(nutrition_plan)


@plan_generation_router.get("/active", response_model=CombinedPlanResponse)
def get_active_plans(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get currently active workout and nutrition plans for the user.
    
    Returns both plans (if they exist) with full details including:
    - All workout days and exercises
    - All meals with nutritional information
    
    **Response:**
    - Returns plans that are currently active (within date range)
    - If no plans exist, returns message indicating no active plans
    - Both workout_plan and nutrition_plan fields can be null if not present
    """
    plan_service = PlanGenerationService(db)
    result = plan_service.get_user_active_plans(current_user.id)
    
    return result
