from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from app.planning_module.models.enums import (
    PlanType,
    WorkoutLocation,
    EquipmentAvailability,
    WorkoutFocus,
    WorkoutDifficulty,
    CaloriePreference,
    MealComplexity,
    CuisineType
)


# ========================================
# PLAN REQUEST SCHEMAS (User Input)
# ========================================

class WorkoutPreferences(BaseModel):
    """Workout-specific preferences for plan generation"""
    workout_days_per_week: int = Field(..., ge=1, le=7, description="Training frequency per week")
    workout_location: WorkoutLocation
    equipment_availability: EquipmentAvailability
    workout_focus: WorkoutFocus
    workout_difficulty: WorkoutDifficulty
    session_duration_minutes: int = Field(..., ge=15, le=180, description="Target session duration")
    focus_areas: Optional[List[str]] = Field(None, description="Specific muscle groups or body areas")


class NutritionPreferences(BaseModel):
    """Nutrition-specific preferences for plan generation"""
    calorie_preference: CaloriePreference
    custom_calorie_target: Optional[int] = Field(None, ge=1000, le=5000, description="Custom daily calorie goal")
    meals_per_day: int = Field(..., ge=3, le=6, description="Number of meals per day")
    meal_complexity: MealComplexity
    cuisine_preference: CuisineType
    exclude_ingredients: Optional[List[str]] = Field(None, description="Ingredients to avoid")

    @field_validator('custom_calorie_target')
    @classmethod
    def validate_custom_calories(cls, v, info):
        """Ensure custom_calorie_target is provided when calorie_preference is CUSTOM"""
        if info.data.get('calorie_preference') == CaloriePreference.CUSTOM and not v:
            raise ValueError('custom_calorie_target is required when calorie_preference is CUSTOM')
        return v


class WorkoutPlanGenerationRequest(BaseModel):
    """Request for generating/updating workout plan"""
    duration_weeks: int = Field(..., ge=1, le=52, description="Plan duration in weeks")
    workout_preferences: WorkoutPreferences


class NutritionPlanGenerationRequest(BaseModel):
    """Request for generating/updating nutrition plan"""
    duration_weeks: int = Field(..., ge=1, le=52, description="Plan duration in weeks")
    nutrition_preferences: NutritionPreferences


# ========================================
# CENTRAL CATALOG SCHEMAS
# ========================================

class CentralExerciseResponse(BaseModel):
    """Schema for central exercise catalog entry"""
    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    instructions: Optional[str] = None
    video_url: Optional[str] = None
    image_url: Optional[str] = None

    class Config:
        from_attributes = True


class CentralFoodResponse(BaseModel):
    """Schema for central food catalog entry (USDA foods for logging and AI context)"""
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
    dietary_tags: Optional[list] = []
    usda_fdc_id: Optional[int] = None
    source: str = "USDA"

    class Config:
        from_attributes = True


# ========================================
# EXERCISE SCHEMAS
# ========================================

class ExerciseCreate(BaseModel):
    """Internal schema for AI-generated exercise data before catalog lookup"""
    exercise_name: str = Field(..., min_length=1, max_length=255)
    exercise_type: Optional[str] = Field(None, max_length=50)
    sets: Optional[int] = Field(None, ge=1, le=20)
    reps: Optional[int] = Field(None, ge=1, le=100)
    weight_kg: Optional[float] = Field(None, ge=0)
    duration_seconds: Optional[int] = Field(None, ge=0)
    rest_seconds: Optional[int] = Field(None, ge=0, le=600)
    instructions: Optional[str] = None
    video_url: Optional[str] = Field(None, max_length=500)
    image_url: Optional[str] = Field(None, max_length=500)
    order_index: int = Field(default=0, ge=0)


class WorkoutDayExerciseResponse(BaseModel):
    """Schema for a workout day exercise slot (junction + embedded catalog entry)"""
    id: int
    workout_day_id: int
    order_index: int
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_kg: Optional[float] = None
    duration_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    notes: Optional[str] = None
    central_exercise: CentralExerciseResponse

    class Config:
        from_attributes = True


# ========================================
# WORKOUT DAY SCHEMAS
# ========================================

class WorkoutDayBase(BaseModel):
    """Base workout day schema"""
    day_name: str = Field(..., min_length=1, max_length=100)
    day_number: int = Field(..., ge=1)
    focus_area: Optional[str] = Field(None, max_length=100)
    estimated_duration: Optional[int] = Field(None, ge=0, le=300)
    notes: Optional[str] = None


class WorkoutDayCreate(WorkoutDayBase):
    """Schema for creating a workout day"""
    exercises: List[ExerciseCreate] = []


class WorkoutDayResponse(WorkoutDayBase):
    """Schema for workout day response"""
    id: int
    workout_plan_id: int
    exercises: List[WorkoutDayExerciseResponse] = []

    class Config:
        from_attributes = True


# ========================================
# WORKOUT PLAN SCHEMAS
# ========================================

class WorkoutPlanBase(BaseModel):
    """Base workout plan schema"""
    plan_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    frequency: Optional[str] = Field(None, max_length=100)
    difficulty_level: Optional[str] = Field(None, max_length=50)
    estimated_duration_per_session: Optional[int] = Field(None, ge=0)


class WorkoutPlanCreate(WorkoutPlanBase):
    """Schema for creating a workout plan"""
    workout_days: List[WorkoutDayCreate] = []


class WorkoutPlanResponse(WorkoutPlanBase):
    """Schema for workout plan response"""
    id: int
    user_id: int
    profile_id: int
    generated_from_preferences: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    workout_days: List[WorkoutDayResponse] = []

    class Config:
        from_attributes = True


class WorkoutPlanSummary(BaseModel):
    """Summarized workout plan (without full details)"""
    id: int
    user_id: int
    plan_name: str
    start_date: date
    end_date: Optional[date] = None
    frequency: Optional[str] = None
    difficulty_level: Optional[str] = None
    created_at: datetime
    total_workout_days: int = 0

    class Config:
        from_attributes = True


# ========================================
# MEAL SCHEMAS
# ========================================

class NutritionPlanMealIngredientCreate(BaseModel):
    central_food_id: int
    amount_g: float

class NutritionPlanMealIngredientResponse(BaseModel):
    """
    Full ingredient row including food name, category, and macros
    scaled to the actual amount_g used in the meal.

    Per-serving values are computed as:  (per_100g_value / 100) * amount_g
    """
    id: int
    nutrition_plan_meal_id: int
    central_food_id: int
    amount_g: float

    # Food identity
    food_name: str = ""
    food_category: Optional[str] = None

    # Macros scaled to amount_g  (not per-100g)
    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fats_g: float = 0.0
    fiber_g: Optional[float] = None

    # Raw per-100g values (useful for display / editing)
    calories_per_100g: float = 0.0
    protein_per_100g: float = 0.0
    carbs_per_100g: float = 0.0
    fats_per_100g: float = 0.0
    fiber_per_100g: Optional[float] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_food(cls, ing) -> "NutritionPlanMealIngredientResponse":
        """Build from a NutritionPlanMealIngredient ORM row that has .food loaded."""
        food = getattr(ing, "food", None)
        if food is None:
            return cls(
                id=ing.id,
                nutrition_plan_meal_id=ing.nutrition_plan_meal_id,
                central_food_id=ing.central_food_id,
                amount_g=ing.amount_g,
            )
        ratio = ing.amount_g / 100.0
        return cls(
            id=ing.id,
            nutrition_plan_meal_id=ing.nutrition_plan_meal_id,
            central_food_id=ing.central_food_id,
            amount_g=ing.amount_g,
            food_name=food.food_name,
            food_category=food.food_category,
            calories=round(food.calories_per_100g * ratio, 2),
            protein_g=round(food.protein_per_100g * ratio, 2),
            carbs_g=round(food.carbs_per_100g * ratio, 2),
            fats_g=round(food.fats_per_100g * ratio, 2),
            fiber_g=round(food.fiber_per_100g * ratio, 2) if food.fiber_per_100g is not None else None,
            calories_per_100g=food.calories_per_100g,
            protein_per_100g=food.protein_per_100g,
            carbs_per_100g=food.carbs_per_100g,
            fats_per_100g=food.fats_per_100g,
            fiber_per_100g=food.fiber_per_100g,
        )


class MealCreate(BaseModel):
    """Internal schema for AI-generated meal data"""
    meal_type: str = Field(..., max_length=50)
    meal_name: str = Field(..., min_length=1, max_length=255)
    calories: float = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    carbs_g: float = Field(..., ge=0)
    fats_g: float = Field(..., ge=0)
    fiber_g: Optional[float] = Field(None, ge=0)
    ingredients: List[NutritionPlanMealIngredientCreate] = []
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = Field(None, ge=0)
    cook_time_minutes: Optional[int] = Field(None, ge=0)
    servings: int = Field(default=1, ge=1)
    image_url: Optional[str] = Field(None, max_length=500)
    order_index: int = Field(default=0, ge=0)


class NutritionPlanMealResponse(BaseModel):
    """Schema for a nutrition plan meal (inline, self-contained)"""
    id: int
    nutrition_plan_day_id: int
    meal_type: str
    meal_name: str
    calories: int
    protein_g: float
    carbs_g: float
    fats_g: float
    fiber_g: Optional[float] = None
    ingredients: List[NutritionPlanMealIngredientResponse] = []
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    servings: float
    order_index: int
    notes: Optional[str] = None

    class Config:
        from_attributes = True

    @field_validator('ingredients', mode='before')
    @classmethod
    def resolve_ingredients(cls, v):
        if not v:
            return []
        resolved = []
        for ing in v:
            # If it's an ORM object containing a 'food' attribute
            if hasattr(ing, 'food'):
                resolved.append(NutritionPlanMealIngredientResponse.from_orm_with_food(ing))
            else:
                resolved.append(ing)
        return resolved


# ========================================
# NUTRITION DAY SCHEMAS
# ========================================

class NutritionPlanDayCreate(BaseModel):
    """Schema for creating a nutrition plan day"""
    day_number: int = Field(..., ge=1, le=7)
    day_name: str = Field(..., min_length=1, max_length=50)
    notes: Optional[str] = None
    meals: List[MealCreate] = []


class NutritionPlanDayResponse(BaseModel):
    """Schema for nutrition plan day response"""
    id: int
    nutrition_plan_id: int
    day_number: int
    day_name: str
    notes: Optional[str] = None
    meals: List[NutritionPlanMealResponse] = []

    class Config:
        from_attributes = True


# ========================================
# NUTRITION PLAN SCHEMAS
# ========================================

class NutritionPlanBase(BaseModel):
    """Base nutrition plan schema"""
    plan_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    daily_calories: float = Field(..., ge=0)
    daily_protein_g: float = Field(..., ge=0)
    daily_carbs_g: float = Field(..., ge=0)
    daily_fats_g: float = Field(..., ge=0)


class NutritionPlanCreate(NutritionPlanBase):
    """Schema for creating a nutrition plan"""
    days: List[NutritionPlanDayCreate] = []


class NutritionPlanResponse(NutritionPlanBase):
    """Schema for nutrition plan response"""
    id: int
    user_id: int
    profile_id: int
    generated_from_preferences: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    days: List[NutritionPlanDayResponse] = []

    class Config:
        from_attributes = True


class NutritionPlanSummary(BaseModel):
    """Summarized nutrition plan (without full details)"""
    id: int
    user_id: int
    plan_name: str
    start_date: date
    end_date: Optional[date] = None
    daily_calories: float
    daily_protein_g: float
    daily_carbs_g: float
    daily_fats_g: float
    created_at: datetime
    total_meals: int = 0

    class Config:
        from_attributes = True


# ========================================
# COMBINED PLAN RESPONSE
# ========================================

class CombinedPlanResponse(BaseModel):
    """Response when both workout and nutrition plans are generated"""
    workout_plan: Optional[WorkoutPlanResponse] = None
    nutrition_plan: Optional[NutritionPlanResponse] = None
    message: str = "Plan(s) generated successfully"


# ========================================
# DRAFT RESPONSE & SAVE REQUEST SCHEMAS
# (Generate = AI only, no DB write;
#  Save = client confirms and persists)
# ========================================

class WorkoutPlanDraftResponse(BaseModel):
    """
    Returned by POST /plans/generate/workout.
    Contains the full AI-generated plan structure but NOT yet saved to the database.
    Pass this entire object to POST /plans/save/workout to persist it.
    """
    draft_plan: WorkoutPlanCreate
    generated_from_preferences: dict = {}
    update_plan_id: Optional[int] = Field(
        None,
        description="ID of the existing plan that will be replaced on save. Null if this is a new plan."
    )


class WorkoutPlanSaveRequest(BaseModel):
    """
    Request body for POST /plans/save/workout.
    Send the exact draft_plan object received from the generate endpoint.
    """
    draft_plan: WorkoutPlanCreate
    generated_from_preferences: dict = {}
    update_plan_id: Optional[int] = Field(
        None,
        description="ID of the existing plan to update. Null to create a new plan."
    )


class NutritionPlanDraftResponse(BaseModel):
    """
    Returned by POST /plans/generate/nutrition.
    Contains the full AI-generated plan structure (7 days, meals, ingredients)
    but NOT yet saved to the database.
    Pass this entire object to POST /plans/save/nutrition to persist it.
    """
    draft_plan: NutritionPlanCreate
    generated_from_preferences: dict = {}
    update_plan_id: Optional[int] = Field(
        None,
        description="ID of the existing plan that will be replaced on save. Null if this is a new plan."
    )


class NutritionPlanSaveRequest(BaseModel):
    """
    Request body for POST /plans/save/nutrition.
    Send the exact draft_plan object received from the generate endpoint.
    """
    draft_plan: NutritionPlanCreate
    generated_from_preferences: dict = {}
    update_plan_id: Optional[int] = Field(
        None,
        description="ID of the existing plan to update. Null to create a new plan."
    )


# Aliases for route compatibility
ExerciseResponse = WorkoutDayExerciseResponse
MealResponse = NutritionPlanMealResponse
