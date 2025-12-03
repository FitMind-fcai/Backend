"""
AI Coach Service
Handles AI-powered workout and nutrition plan generation using Groq API.
This module is completely modular and has NO dependencies on other app modules.
"""
from app.ai_services.ai_coach.vector_db_service import (
    VectorDBService,
    get_vector_db_service,
    initialize_vector_db
)
from app.ai_services.ai_coach.ai_coach_service import (
    AICoachService,
    get_ai_coach_service
)
from app.ai_services.ai_coach.dtos import (
    # Input DTOs
    UserProfileDTO,
    WorkoutPreferencesDTO,
    NutritionPreferencesDTO,
    PlanGenerationRequestDTO,
    # Output DTOs
    ExerciseDTO,
    WorkoutDayDTO,
    WorkoutPlanDTO,
    MealDTO,
    NutritionPlanDTO,
    GeneratedPlansDTO
)

__all__ = [
    # Services
    "VectorDBService",
    "get_vector_db_service",
    "initialize_vector_db",
    "AICoachService",
    "get_ai_coach_service",
    # Input DTOs
    "UserProfileDTO",
    "WorkoutPreferencesDTO",
    "NutritionPreferencesDTO",
    "PlanGenerationRequestDTO",
    # Output DTOs
    "ExerciseDTO",
    "WorkoutDayDTO",
    "WorkoutPlanDTO",
    "MealDTO",
    "NutritionPlanDTO",
    "GeneratedPlansDTO"
]
