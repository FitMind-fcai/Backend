from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository
from app.tracking_module.services.tracking_service import TrackingService
from app.shared.repositories.central_food_repository import CentralFoodRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository
from app.ai_services.meal_scanner.meal_scanner_service import MealScannerService, get_meal_scanner_service
from app.ai_services.voice_transcriber.voice_transcriber_service import VoiceTranscriberService, get_voice_transcriber_service


def get_workout_log_repository(db: Session = Depends(get_db)) -> WorkoutLogRepository:
    return WorkoutLogRepository(db)


def get_meal_log_repository(db: Session = Depends(get_db)) -> MealLogRepository:
    return MealLogRepository(db)


def get_weight_log_repository(db: Session = Depends(get_db)) -> WeightLogRepository:
    return WeightLogRepository(db)


def get_sleep_log_repository(db: Session = Depends(get_db)) -> SleepLogRepository:
    return SleepLogRepository(db)


def get_hydration_log_repository(db: Session = Depends(get_db)) -> HydrationLogRepository:
    return HydrationLogRepository(db)


def get_central_food_repository(db: Session = Depends(get_db)) -> CentralFoodRepository:
    return CentralFoodRepository(db)


def get_central_exercise_repository(db: Session = Depends(get_db)) -> CentralExerciseRepository:
    return CentralExerciseRepository(db)


def get_meal_scanner_service_dep() -> MealScannerService:
    return get_meal_scanner_service()


def get_voice_transcriber_service_dep() -> VoiceTranscriberService:
    return get_voice_transcriber_service()


def get_tracking_service(
    workout_repo: WorkoutLogRepository = Depends(get_workout_log_repository),
    meal_repo: MealLogRepository = Depends(get_meal_log_repository),
    weight_repo: WeightLogRepository = Depends(get_weight_log_repository),
    sleep_repo: SleepLogRepository = Depends(get_sleep_log_repository),
    hydration_repo: HydrationLogRepository = Depends(get_hydration_log_repository),
    central_food_repo: CentralFoodRepository = Depends(get_central_food_repository),
    central_exercise_repo: CentralExerciseRepository = Depends(get_central_exercise_repository),
) -> TrackingService:
    return TrackingService(
        workout_repo=workout_repo,
        meal_repo=meal_repo,
        weight_repo=weight_repo,
        sleep_repo=sleep_repo,
        hydration_repo=hydration_repo,
        central_food_repo=central_food_repo,
        central_exercise_repo=central_exercise_repo,
    )
