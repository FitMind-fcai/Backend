"""
DTOs (Data Transfer Objects) for Meal Scanner Service.
These are used to pass data to/from the Meal Scanner without coupling to any other module.
The Meal Scanner is completely modular and independent.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ========================================
# INPUT DTOs - What Meal Scanner receives
# ========================================

class MealScanRequestDTO(BaseModel):
    """DTO for meal scan request."""
    image_base64: str = Field(..., description="Base64 encoded image of the meal")
    image_format: str = Field(default="jpeg", description="Image format (jpeg, png, webp)")
    user_dietary_preference: Optional[str] = Field(None, description="User's dietary preference for context")
    user_allergies: Optional[str] = Field(None, description="User's allergies for warnings")
    language: str = Field(default="en", description="Response language (en, ar)")


# ========================================
# OUTPUT DTOs - What Meal Scanner returns
# ========================================

class FoodItemDTO(BaseModel):
    """DTO for a single identified food item."""
    name: str = Field(..., description="Name of the food item")
    portion_size: str = Field(..., description="Estimated portion size (e.g., '1 cup', '150g')")
    calories: int = Field(..., ge=0, description="Estimated calories")
    protein_g: float = Field(..., ge=0, description="Estimated protein in grams")
    carbs_g: float = Field(..., ge=0, description="Estimated carbohydrates in grams")
    fats_g: float = Field(..., ge=0, description="Estimated fats in grams")
    fiber_g: Optional[float] = Field(None, ge=0, description="Estimated fiber in grams")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")


class AllergenWarningDTO(BaseModel):
    """DTO for allergen warning."""
    allergen: str = Field(..., description="Name of the allergen")
    food_item: str = Field(..., description="Food item containing the allergen")
    severity: str = Field(default="warning", description="Severity level: warning, caution")


class MealScanResultDTO(BaseModel):
    """DTO for complete meal scan result."""
    meal_name: str = Field(..., description="Identified meal name")
    meal_type: str = Field(..., description="Meal type: Breakfast, Lunch, Dinner, Snack")
    food_items: List[FoodItemDTO] = Field(default_factory=list, description="List of identified food items")
    total_calories: int = Field(..., ge=0, description="Total estimated calories")
    total_protein_g: float = Field(..., ge=0, description="Total protein in grams")
    total_carbs_g: float = Field(..., ge=0, description="Total carbohydrates in grams")
    total_fats_g: float = Field(..., ge=0, description="Total fats in grams")
    allergen_warnings: List[AllergenWarningDTO] = Field(default_factory=list, description="Allergen warnings if any")
    health_notes: Optional[str] = Field(None, description="Health-related notes about the meal")
    confidence_score: float = Field(..., ge=0, le=1, description="Overall confidence score")
    scan_successful: bool = Field(default=True, description="Whether the scan was successful")
    error_message: Optional[str] = Field(None, description="Error message if scan failed")
