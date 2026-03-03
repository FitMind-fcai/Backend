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
# EXERCISE SCHEMAS
# ========================================

class ExerciseBase(BaseModel):
    """Base exercise schema"""
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


class ExerciseCreate(ExerciseBase):
    """Schema for creating an exercise"""
    pass


class ExerciseResponse(ExerciseBase):
    """Schema for exercise response"""
    id: int
    workout_day_id: int

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
    exercises: List[ExerciseResponse] = []

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

class MealBase(BaseModel):
    """Base meal schema"""
    meal_type: str = Field(..., max_length=50)
    meal_name: str = Field(..., min_length=1, max_length=255)
    calories: float = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    carbs_g: float = Field(..., ge=0)
    fats_g: float = Field(..., ge=0)
    ingredients: Optional[str] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = Field(None, ge=0)
    cook_time_minutes: Optional[int] = Field(None, ge=0)
    servings: int = Field(default=1, ge=1)
    image_url: Optional[str] = Field(None, max_length=500)
    order_index: int = Field(default=0, ge=0)


class MealCreate(MealBase):
    """Schema for creating a meal"""
    pass


class MealResponse(MealBase):
    """Schema for meal response"""
    id: int
    nutrition_plan_id: int

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
    meals: List[MealCreate] = []


class NutritionPlanResponse(NutritionPlanBase):
    """Schema for nutrition plan response"""
    id: int
    user_id: int
    profile_id: int
    generated_from_preferences: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    meals: List[MealResponse] = []

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
