"""
Meal Scanner Service — Qwen2.5-VL vision recognition + pgvector food matching.
"""
from app.ai_services.meal_scanner.meal_scanner_service import (
    MealScannerService,
    get_meal_scanner_service,
    embed_text,
)
from app.ai_services.meal_scanner.dtos import (
    MealScanRequestDTO,
    FoodItemDTO,
    AllergenWarningDTO,
    MatchedFoodDTO,
    MealScanResultDTO,
)

__all__ = [
    "MealScannerService",
    "get_meal_scanner_service",
    "embed_text",
    "MealScanRequestDTO",
    "FoodItemDTO",
    "AllergenWarningDTO",
    "MatchedFoodDTO",
    "MealScanResultDTO",
]
