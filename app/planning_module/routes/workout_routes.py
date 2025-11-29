from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.auth_module.models.user import User
from app.auth_module.core.dependencies import get_current_verified_user
from app.planning_module.services.workout_plan_service import WorkoutPlanService
from app.planning_module.schemas import (
    WorkoutPlanResponse,
    WorkoutPlanSummary,
    WorkoutDayResponse,
    ExerciseResponse
)

workout_plan_router = APIRouter(prefix="/workout-plans", tags=["Workout Plans"])


# ========================================
# WORKOUT PLAN ENDPOINTS
# ========================================

@workout_plan_router.get("/", response_model=List[WorkoutPlanSummary])
def get_my_workout_plans(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all workout plans for the current user.
    Returns summarized list without full details.
    """
    service = WorkoutPlanService(db)
    plans = service.get_user_plans(current_user.id, skip=skip, limit=limit)
    
    # Add workout day count to each plan
    summaries = []
    for plan in plans:
        summary = WorkoutPlanSummary.model_validate(plan)
        summary.total_workout_days = len(plan.workout_days)
        summaries.append(summary)
    
    return summaries


@workout_plan_router.get("/active", response_model=WorkoutPlanResponse)
def get_active_workout_plan(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get the current active workout plan (based on current date).
    Returns full plan details with all workout days and exercises.
    """
    service = WorkoutPlanService(db)
    plan = service.get_active_plan(current_user.id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active workout plan found. Please generate a new plan."
        )
    
    # Load full details
    plan = service.get_plan_with_details(plan.id)
    return WorkoutPlanResponse.model_validate(plan)


@workout_plan_router.get("/{plan_id}", response_model=WorkoutPlanResponse)
def get_workout_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific workout plan by ID with all details.
    User can only access their own plans.
    """
    service = WorkoutPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workout plan not found or you do not have permission to access it"
        )
    
    plan = service.get_plan_with_details(plan_id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout plan not found"
        )
    
    return WorkoutPlanResponse.model_validate(plan)


@workout_plan_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Delete a workout plan.
    Cascades to delete all associated workout days and exercises.
    """
    service = WorkoutPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workout plan not found or you do not have permission to delete it"
        )
    
    service.delete_plan(plan_id)
    return None


# ========================================
# WORKOUT DAY ENDPOINTS
# ========================================

@workout_plan_router.get("/{plan_id}/days", response_model=List[WorkoutDayResponse])
def get_workout_days(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all workout days for a specific plan.
    """
    service = WorkoutPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workout plan not found or you do not have permission to access it"
        )
    
    days = service.get_workout_days(plan_id)
    
    return [WorkoutDayResponse.model_validate(day) for day in days]


@workout_plan_router.get("/{plan_id}/days/{day_id}", response_model=WorkoutDayResponse)
def get_workout_day(
    plan_id: int,
    day_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific workout day with all exercises.
    """
    service = WorkoutPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workout plan not found or you do not have permission to access it"
        )
    
    # Verify day belongs to plan
    if not service.verify_day_belongs_to_plan(day_id, plan_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout day not found in this plan"
        )
    
    day = service.get_workout_day_with_exercises(day_id)
    
    return WorkoutDayResponse.model_validate(day)


# ========================================
# EXERCISE ENDPOINTS
# ========================================

@workout_plan_router.get("/{plan_id}/days/{day_id}/exercises", response_model=List[ExerciseResponse])
def get_exercises(
    plan_id: int,
    day_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all exercises for a specific workout day.
    """
    service = WorkoutPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workout plan not found or you do not have permission to access it"
        )
    
    # Verify day belongs to plan
    if not service.verify_day_belongs_to_plan(day_id, plan_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout day not found in this plan"
        )
    
    exercises = service.get_exercises(day_id)
    
    return [ExerciseResponse.model_validate(exercise) for exercise in exercises]

# TODO: Implement AI plan generation endpoint
# @router.post("/generate", response_model=WorkoutPlanResponse)
# async def generate_workout_plan(
#     request: PlanGenerationRequest,
#     current_user: User = Depends(get_current_verified_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Generate a new workout plan using AI based on user profile and preferences.
#     
#     Flow:
#     1. Validate user has a profile
#     2. Extract workout preferences from request
#     3. Call AI Coach service to generate plan
#     4. Save generated plan to database
#     5. Return complete plan with all details
#     """
#     pass
