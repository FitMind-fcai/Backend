"""
DTOs (Data Transfer Objects) for Meal Scanner Service.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ========================================
# INPUT DTOs
# ========================================

class MealScanRequestDTO(BaseModel):
    image_bytes: bytes = Field(..., description="Raw image bytes")
    image_format: str = Field(default="jpeg", description="Image format (jpeg, png, webp)")
    user_dietary_preference: Optional[str] = Field(None, description="User's dietary preference for context")
    user_allergies: Optional[str] = Field(None, description="User's allergies for warnings")
    language: str = Field(default="en", description="Response language (en, ar)")


# ========================================
# OUTPUT DTOs
# ========================================

class FoodItemDTO(BaseModel):
    name: str
    portion_size: str
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    carbs_g: float = Field(..., ge=0)
    fats_g: float = Field(..., ge=0)
    fiber_g: Optional[float] = Field(None, ge=0)
    confidence: float = Field(..., ge=0, le=1)


class AllergenWarningDTO(BaseModel):
    allergen: str
    food_item: str
    severity: str = Field(default="warning")


class MatchedFoodDTO(BaseModel):
    """A food from the central catalog matched via vector similarity."""
    id: int
    food_name: str
    food_category: Optional[str] = None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fats_per_100g: float
    fiber_per_100g: Optional[float] = None
    serving_size_g: Optional[float] = None
    serving_description: Optional[str] = None
    similarity_score: float = Field(..., ge=0, le=1, description="Cosine similarity 0-1")


class MealScanResultDTO(BaseModel):
    meal_name: str
    meal_type: str
    food_items: List[FoodItemDTO] = Field(default_factory=list)
    total_calories: int = Field(..., ge=0)
    total_protein_g: float = Field(..., ge=0)
    total_carbs_g: float = Field(..., ge=0)
    total_fats_g: float = Field(..., ge=0)
    allergen_warnings: List[AllergenWarningDTO] = Field(default_factory=list)
    health_notes: Optional[str] = None
    confidence_score: float = Field(..., ge=0, le=1)
    tags: List[str] = Field(default_factory=list, description="Meal tags used for vector search (e.g. 'grilled', 'chicken', 'high-protein')")
    matched_foods: List[MatchedFoodDTO] = Field(default_factory=list, description="Top 5 similar foods from central catalog")
    scan_successful: bool = Field(default=True)
    error_message: Optional[str] = None
