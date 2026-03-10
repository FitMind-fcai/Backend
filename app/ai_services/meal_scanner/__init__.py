"""
Meal Scanner Service
Handles AI-powered food image analysis using Groq API with vision capabilities.
This module is completely modular and has NO dependencies on other app modules.
"""
from app.ai_services.meal_scanner.meal_scanner_service import (
    MealScannerService,
    get_meal_scanner_service
)
from app.ai_services.meal_scanner.dtos import (
    # Input DTOs
    MealScanRequestDTO,
    # Output DTOs
    FoodItemDTO,
    AllergenWarningDTO,
    MealScanResultDTO
)

__all__ = [
    # Service
    "MealScannerService",
    "get_meal_scanner_service",
    # Input DTOs
    "MealScanRequestDTO",
    # Output DTOs
    "FoodItemDTO",
    "AllergenWarningDTO",
    "MealScanResultDTO"
]
