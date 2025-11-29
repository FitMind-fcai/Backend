from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.auth_module.models.user import User
from app.auth_module.core.dependencies import get_current_verified_user
from app.planning_module.services.nutrition_plan_service import NutritionPlanService
from app.planning_module.schemas import (
    NutritionPlanResponse,
    NutritionPlanSummary,
    MealResponse
)

router = APIRouter(prefix="/nutrition-plans", tags=["Nutrition Plans"])



@router.get("/", response_model=List[NutritionPlanSummary])
def get_my_nutrition_plans(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all nutrition plans for the current user.
    Returns summarized list without full details.
    """
    service = NutritionPlanService(db)
    plans = service.get_user_plans(current_user.id, skip=skip, limit=limit)
    
    # Add meal count to each plan
    summaries = []
    for plan in plans:
        summary = NutritionPlanSummary.model_validate(plan)
        summary.total_meals = len(plan.meals)
        summaries.append(summary)
    
    return summaries


@router.get("/active", response_model=NutritionPlanResponse)
def get_active_nutrition_plan(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get the current active nutrition plan (based on current date).
    Returns full plan details with all meals.
    """
    service = NutritionPlanService(db)
    plan = service.get_active_plan(current_user.id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active nutrition plan found. Please generate a new plan."
        )
    
    # Load full details
    plan = service.get_plan_with_details(plan.id)
    return NutritionPlanResponse.model_validate(plan)


@router.get("/{plan_id}", response_model=NutritionPlanResponse)
def get_nutrition_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific nutrition plan by ID with all meals.
    User can only access their own plans.
    """
    service = NutritionPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )
    
    plan = service.get_plan_with_details(plan_id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nutrition plan not found"
        )
    
    return NutritionPlanResponse.model_validate(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_nutrition_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Delete a nutrition plan.
    Cascades to delete all associated meals.
    """
    service = NutritionPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to delete it"
        )
    
    service.delete_plan(plan_id)
    return None


# ========================================
# MEAL ENDPOINTS
# ========================================

@router.get("/{plan_id}/meals", response_model=List[MealResponse])
def get_meals(
    plan_id: int,
    meal_type: str = None,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all meals for a specific nutrition plan.
    Optionally filter by meal_type (Breakfast, Lunch, Dinner, Snack).
    """
    service = NutritionPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )
    
    if meal_type:
        meals = service.get_meals_by_type(plan_id, meal_type)
    else:
        meals = service.get_meals(plan_id)
    
    return [MealResponse.model_validate(meal) for meal in meals]


@router.get("/{plan_id}/meals/{meal_id}", response_model=MealResponse)
def get_meal(
    plan_id: int,
    meal_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific meal by ID.
    """
    service = NutritionPlanService(db)
    
    # Verify ownership
    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )
    
    # Verify meal belongs to plan
    if not service.verify_meal_belongs_to_plan(meal_id, plan_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found in this plan"
        )
    
    meal = service.get_meal(meal_id)
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found"
        )
    
    return MealResponse.model_validate(meal)


# TODO: Implement AI plan generation endpoint
# @router.post("/generate", response_model=NutritionPlanResponse)
# async def generate_nutrition_plan(
#     request: PlanGenerationRequest,
#     current_user: User = Depends(get_current_verified_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Generate a new nutrition plan using AI based on user profile and preferences.
#     
#     Flow:
#     1. Validate user has a profile
#     2. Extract nutrition preferences from request
#     3. Calculate nutritional needs (BMR, TDEE, macros)
#     4. Call AI Coach service to generate meal plan
#     5. Save generated plan to database
#     6. Return complete plan with all meals
#     """
#     pass
