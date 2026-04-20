from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.services.tracking_service import TrackingService
from app.shared.repositories.central_food_repository import CentralFoodRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository


def get_workout_log_repository(db: Session = Depends(get_db)) -> WorkoutLogRepository:
    return WorkoutLogRepository(db)


def get_meal_log_repository(db: Session = Depends(get_db)) -> MealLogRepository:
    return MealLogRepository(db)


def get_weight_log_repository(db: Session = Depends(get_db)) -> WeightLogRepository:
    return WeightLogRepository(db)


def get_central_food_repository(db: Session = Depends(get_db)) -> CentralFoodRepository:
    return CentralFoodRepository(db)


def get_central_exercise_repository(db: Session = Depends(get_db)) -> CentralExerciseRepository:
    return CentralExerciseRepository(db)


def get_tracking_service(
    workout_repo: WorkoutLogRepository = Depends(get_workout_log_repository),
    meal_repo: MealLogRepository = Depends(get_meal_log_repository),
    weight_repo: WeightLogRepository = Depends(get_weight_log_repository),
    central_food_repo: CentralFoodRepository = Depends(get_central_food_repository),
    central_exercise_repo: CentralExerciseRepository = Depends(get_central_exercise_repository),
) -> TrackingService:
    return TrackingService(
        workout_repo=workout_repo,
        meal_repo=meal_repo,
        weight_repo=weight_repo,
        central_food_repo=central_food_repo,
        central_exercise_repo=central_exercise_repo,
    )
