from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai_services.ai_coach.ai_coach_service import AICoachService, get_ai_coach_service
from app.db.database import get_db
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.recommendation_system.services.recommendation_service import RecommendationService
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.sleep_log_repository import SleepLogRepository
from app.tracking_module.repositories.hydration_log_repository import HydrationLogRepository


def get_recommendation_service(
    db: Session = Depends(get_db),
    ai_coach: AICoachService = Depends(get_ai_coach_service),
) -> RecommendationService:
    return RecommendationService(
        meal_repo=MealLogRepository(db),
        workout_repo=WorkoutLogRepository(db),
        weight_repo=WeightLogRepository(db),
        sleep_repo=SleepLogRepository(db),
        hydration_repo=HydrationLogRepository(db),
        nutrition_plan_repo=NutritionPlanRepository(db),
        workout_plan_repo=WorkoutPlanRepository(db),
        profile_repo=ProfileRepository(db),
        ai_coach=ai_coach,
    )
