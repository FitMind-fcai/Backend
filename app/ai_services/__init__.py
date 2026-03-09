"""
AI Services Package
Contains external AI service integrations and clients.
All services are modular and have NO dependencies on other app modules.
"""

# AI Coach - Workout & Nutrition Plan Generation with RAG
from app.ai_services.ai_coach import (
    AICoachService,
    get_ai_coach_service,
    VectorDBService,
    get_vector_db_service,
    initialize_vector_db,
    # DTOs
    UserProfileDTO,
    WorkoutPreferencesDTO,
    NutritionPreferencesDTO,
    PlanGenerationRequestDTO,
    WorkoutPlanDTO,
    NutritionPlanDTO,
    GeneratedPlansDTO,
    WorkoutDayDTO,
    ExerciseDTO,
    MealDTO,
    NutritionDayDTO
)

# Meal Scanner - Food Image Analysis
from app.ai_services.meal_scanner import (
    MealScannerService,
    get_meal_scanner_service,
    # DTOs
    MealScanRequestDTO,
    MealScanResultDTO,
    FoodItemDTO,
    AllergenWarningDTO
)

# Voice Transcriber - Speech-to-Text
from app.ai_services.voice_transcriber import (
    VoiceTranscriberService,
    get_voice_transcriber_service,
    # DTOs
    TranscriptionContextType,
    TranscriptionRequestDTO,
    TranscriptionResultDTO,
    MealLogTranscriptionDTO,
    WorkoutLogTranscriptionDTO
)

__all__ = [
    # AI Coach
    "AICoachService",
    "get_ai_coach_service",
    "VectorDBService",
    "get_vector_db_service",
    "initialize_vector_db",
    "UserProfileDTO",
    "WorkoutPreferencesDTO",
    "NutritionPreferencesDTO",
    "PlanGenerationRequestDTO",
    "WorkoutPlanDTO",
    "NutritionPlanDTO",
    "GeneratedPlansDTO",
    "WorkoutDayDTO",
    "ExerciseDTO",
    "MealDTO",
    "NutritionDayDTO",
    # Meal Scanner
    "MealScannerService",
    "get_meal_scanner_service",
    "MealScanRequestDTO",
    "MealScanResultDTO",
    "FoodItemDTO",
    "AllergenWarningDTO",
    # Voice Transcriber
    "VoiceTranscriberService",
    "get_voice_transcriber_service",
    "TranscriptionContextType",
    "TranscriptionRequestDTO",
    "TranscriptionResultDTO",
    "MealLogTranscriptionDTO",
    "WorkoutLogTranscriptionDTO"
]
