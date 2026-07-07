"""
Meal Scanner Service — Qwen2.5-VL vision recognition (nutrition estimates + tags).
"""
from app.ai_services.meal_scanner.meal_scanner_service import (
    MealScannerService,
    get_meal_scanner_service,
)
from app.ai_services.meal_scanner.dtos import (
    MealScanRequestDTO,
    FoodItemDTO,
    AllergenWarningDTO,
    MealScanResultDTO,
)

__all__ = [
    "MealScannerService",
    "get_meal_scanner_service",
    "MealScanRequestDTO",
    "FoodItemDTO",
    "AllergenWarningDTO",
    "MealScanResultDTO",
]
