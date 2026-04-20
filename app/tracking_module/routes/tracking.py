from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.auth_module.core.dependencies import get_current_verified_user
from app.auth_module.models.user import User
from app.tracking_module.core.dependencies import get_tracking_service
from app.tracking_module.schemas.tracking import (
    WorkoutLogCreateText,
    WorkoutLogResponse,
    MealLogCreateText,
    MealLogResponse,
    WeightLogCreateText,
    WeightLogResponse,
    FoodSearchResult,
    ExerciseSearchResult,
    ManualFoodCreate,
    ManualExerciseCreate,
    ManualCentralFoodResponse,
    ManualCentralExerciseResponse,
)
from app.tracking_module.services.tracking_service import TrackingService


tracking_router = APIRouter(prefix="/tracking", tags=["Tracking"])


@tracking_router.get("/foods/search", response_model=List[FoodSearchResult], summary="Search foods with serving nutrition")
def search_foods(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_foods(user_id=current_user.id, query=q, limit=limit)


@tracking_router.get("/exercises/search", response_model=List[ExerciseSearchResult], summary="Search exercises with details")
def search_exercises(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.search_exercises(user_id=current_user.id, query=q, limit=limit)


@tracking_router.post(
    "/foods/manual",
    response_model=ManualCentralFoodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual food in central catalog",
)
def create_manual_food(
    payload: ManualFoodCreate,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_manual_food(user_id=current_user.id, payload=payload)


@tracking_router.post(
    "/exercises/manual",
    response_model=ManualCentralExerciseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual exercise in central catalog",
)
def create_manual_exercise(
    payload: ManualExerciseCreate,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_manual_exercise(user_id=current_user.id, payload=payload)


@tracking_router.post(
    "/workouts/text",
    response_model=WorkoutLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workout log (text flow)",
)
def create_workout_log_text(
    payload: WorkoutLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_workout_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/workouts", response_model=List[WorkoutLogResponse], summary="List workout logs")
def list_workout_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
):
    return tracking_service.list_workout_logs(user_id=current_user.id, skip=skip, limit=limit, log_date=log_date)


@tracking_router.get("/workouts/{log_id}", response_model=WorkoutLogResponse, summary="Get workout log")
def get_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_workout_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/workouts/{log_id}", summary="Delete workout log")
def delete_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_workout_log(user_id=current_user.id, log_id=log_id)


@tracking_router.post(
    "/meals/text",
    response_model=MealLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create meal log (text flow)",
)
def create_meal_log_text(
    payload: MealLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_meal_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/meals", response_model=List[MealLogResponse], summary="List meal logs")
def list_meal_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
    meal_type: Optional[str] = Query(default=None),
):
    return tracking_service.list_meal_logs(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        log_date=log_date,
        meal_type=meal_type,
    )


@tracking_router.get("/meals/{log_id}", response_model=MealLogResponse, summary="Get meal log")
def get_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_meal_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/meals/{log_id}", summary="Delete meal log")
def delete_meal_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_meal_log(user_id=current_user.id, log_id=log_id)


@tracking_router.post(
    "/weights/text",
    response_model=WeightLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create weight log (text flow)",
)
def create_weight_log_text(
    payload: WeightLogCreateText,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.create_weight_log_text(user_id=current_user.id, payload=payload)


@tracking_router.get("/weights", response_model=List[WeightLogResponse], summary="List weight logs")
def list_weight_logs(
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    log_date: Optional[date] = Query(default=None),
):
    return tracking_service.list_weight_logs(user_id=current_user.id, skip=skip, limit=limit, log_date=log_date)


@tracking_router.get("/weights/{log_id}", response_model=WeightLogResponse, summary="Get weight log")
def get_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.get_weight_log(user_id=current_user.id, log_id=log_id)


@tracking_router.delete("/weights/{log_id}", summary="Delete weight log")
def delete_weight_log(
    log_id: int,
    current_user: User = Depends(get_current_verified_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
):
    return tracking_service.delete_weight_log(user_id=current_user.id, log_id=log_id)
