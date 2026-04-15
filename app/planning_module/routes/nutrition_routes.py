from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.auth_module.models.user import User
from app.auth_module.core.dependencies import get_current_verified_user
from app.planning_module.services.nutrition_plan_service import NutritionPlanService
from app.planning_module.schemas.plan import (
    NutritionPlanResponse,
    NutritionPlanSummary,
    NutritionPlanDayResponse,
    MealResponse,
    NutritionPlanMealIngredientResponse,
)

nutrition_plan_router = APIRouter(prefix="/nutrition-plans", tags=["Nutrition Plans"])


# ============================================================
# PLAN ENDPOINTS
# ============================================================

@nutrition_plan_router.get("/", response_model=List[NutritionPlanSummary])
def get_my_nutrition_plans(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    List all nutrition plans for the current user (summary view, no meal details).
    """
    service = NutritionPlanService(db)
    plans = service.get_user_plans(current_user.id, skip=skip, limit=limit)

    summaries = []
    for plan in plans:
        full = service.get_plan_with_full_details(plan.id)
        summary = NutritionPlanSummary.model_validate(plan)
        summary.total_meals = sum(len(day.meals) for day in full.days) if full else 0
        summaries.append(summary)

    return summaries


@nutrition_plan_router.get("/active", response_model=NutritionPlanResponse)
def get_active_nutrition_plan(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get the current active nutrition plan with all days, meals, and ingredients.
    """
    service = NutritionPlanService(db)
    plan = service.get_active_plan(current_user.id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active nutrition plan found. Please generate a new plan."
        )

    plan = service.get_plan_with_full_details(plan.id)
    return NutritionPlanResponse.model_validate(plan)


@nutrition_plan_router.get("/{plan_id}", response_model=NutritionPlanResponse)
def get_nutrition_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific nutrition plan by ID with all days, meals, and ingredients.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    plan = service.get_plan_with_full_details(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutrition plan not found")

    return NutritionPlanResponse.model_validate(plan)


@nutrition_plan_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_nutrition_plan(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Delete a nutrition plan and all its days, meals, and ingredients.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to delete it"
        )

    service.delete_plan(plan_id)
    return None


# ============================================================
# DAY ENDPOINTS
# ============================================================

@nutrition_plan_router.get("/{plan_id}/days", response_model=List[NutritionPlanDayResponse])
def get_nutrition_days(
    plan_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all 7 days of a nutrition plan with their meals.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    days = service.get_days(plan_id)
    return [NutritionPlanDayResponse.model_validate(day) for day in days]


@nutrition_plan_router.get("/{plan_id}/days/{day_id}", response_model=NutritionPlanDayResponse)
def get_nutrition_day(
    plan_id: int,
    day_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific day by ID with all its meals.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
    repo = NutritionPlanRepository(db)
    day = repo.get_day_by_id(day_id)

    if not day or day.nutrition_plan_id != plan_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Day not found in this plan")

    return NutritionPlanDayResponse.model_validate(day)


# ============================================================
# MEAL ENDPOINTS  (scoped under a day)
# ============================================================

@nutrition_plan_router.get("/{plan_id}/days/{day_id}/meals", response_model=List[MealResponse])
def get_meals_for_day(
    plan_id: int,
    day_id: int,
    meal_type: Optional[str] = None,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all meals for a specific day. Optionally filter by meal_type
    (Breakfast | Lunch | Dinner | Snack).
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    # Verify day belongs to plan
    from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
    repo = NutritionPlanRepository(db)
    day = repo.get_day_by_id(day_id)
    if not day or day.nutrition_plan_id != plan_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Day not found in this plan")

    meals = service.get_meals_for_day(day_id, meal_type)
    return [MealResponse.model_validate(meal) for meal in meals]


@nutrition_plan_router.get("/{plan_id}/days/{day_id}/meals/{meal_id}", response_model=MealResponse)
def get_meal(
    plan_id: int,
    day_id: int,
    meal_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific meal by ID with its ingredients.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    if not service.verify_meal_belongs_to_plan(meal_id, plan_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found in this plan")

    meal = service.get_meal_by_id(meal_id)
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")

    return MealResponse.model_validate(meal)


# ============================================================
# INGREDIENT ENDPOINTS  (scoped under a meal)
# ============================================================

@nutrition_plan_router.get(
    "/{plan_id}/days/{day_id}/meals/{meal_id}/ingredients",
    response_model=List[NutritionPlanMealIngredientResponse]
)
def get_meal_ingredients(
    plan_id: int,
    day_id: int,
    meal_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Get all ingredients for a specific meal, including their central_food_id and amount_g.
    Use the central_food_id to look up full nutritional details via the food catalog.
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    if not service.verify_meal_belongs_to_plan(meal_id, plan_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found in this plan")

    meal = service.get_meal_by_id(meal_id)
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")

    return [NutritionPlanMealIngredientResponse.model_validate(ing) for ing in meal.ingredients]


# ============================================================
# FLAT MEALS LIST  (convenience: all meals across all days for a plan)
# ============================================================

@nutrition_plan_router.get("/{plan_id}/meals", response_model=List[MealResponse])
def get_all_meals_for_plan(
    plan_id: int,
    meal_type: Optional[str] = None,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Flat list of all meals across all days for a nutrition plan.
    Optionally filter by meal_type (Breakfast | Lunch | Dinner | Snack).
    """
    service = NutritionPlanService(db)

    if not service.verify_plan_ownership(plan_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nutrition plan not found or you do not have permission to access it"
        )

    days = service.get_days(plan_id)
    all_meals = []
    for day in days:
        meals = service.get_meals_for_day(day.id, meal_type)
        all_meals.extend(meals)

    return [MealResponse.model_validate(meal) for meal in all_meals]




