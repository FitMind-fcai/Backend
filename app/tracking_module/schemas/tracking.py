from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkoutLogCreateText(BaseModel):
    central_exercise_id: Optional[int] = None
    workout_day_exercise_id: Optional[int] = None
    log_date: date
    sets_completed: int = Field(..., ge=1)
    reps_completed: int = Field(..., ge=1)
    weight_used: Optional[float] = Field(default=None, ge=0)
    duration_seconds: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class WorkoutLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    central_exercise_id: Optional[int]
    workout_day_exercise_id: Optional[int]
    log_date: date
    sets_completed: int
    reps_completed: int
    weight_used: Optional[float]
    duration_seconds: Optional[int]
    notes: Optional[str]
    created_at: datetime


class MealLogCreateText(BaseModel):
    central_food_id: Optional[int] = None
    log_date: date
    meal_type: str = Field(..., min_length=2, max_length=50)
    meal_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    servings: float = Field(default=1.0, gt=0)
    serving_size_g_snapshot: Optional[float] = Field(default=None, gt=0)
    serving_description_snapshot: Optional[str] = Field(default=None, max_length=100)
    calories: Optional[float] = Field(default=None, ge=0)
    protein_g: Optional[float] = Field(default=None, ge=0)
    carbs_g: Optional[float] = Field(default=None, ge=0)
    fats_g: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_meal_input_mode(self):
        if self.central_food_id is not None:
            if any(v is not None for v in [self.calories, self.protein_g, self.carbs_g, self.fats_g]):
                raise ValueError(
                    "When central_food_id is provided, do not send macros. "
                    "Macros are calculated automatically from central food and servings."
                )
            return self

        missing_fields = []
        if not self.meal_name:
            missing_fields.append("meal_name")
        if self.calories is None:
            missing_fields.append("calories")
        if self.protein_g is None:
            missing_fields.append("protein_g")
        if self.carbs_g is None:
            missing_fields.append("carbs_g")
        if self.fats_g is None:
            missing_fields.append("fats_g")

        if missing_fields:
            raise ValueError(
                "For manual meal logs without central_food_id, required fields are missing: "
                + ", ".join(missing_fields)
            )
        return self


class MealLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    central_food_id: Optional[int]
    log_date: date
    meal_type: str
    meal_name: str
    servings: float
    serving_size_g_snapshot: Optional[float]
    serving_description_snapshot: Optional[str]
    calories: float
    protein_g: float
    carbs_g: float
    fats_g: float
    log_method: str
    image_url: Optional[str]
    created_at: datetime


class WeightLogCreateText(BaseModel):
    log_date: date
    weight: float = Field(..., gt=0)
    notes: Optional[str] = None


class WeightLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    log_date: date
    weight: float
    notes: Optional[str]
    created_at: datetime


class FoodSearchResult(BaseModel):
    id: int
    food_name: str
    food_category: Optional[str] = None
    serving_size_g: float
    serving_description: str
    calories_per_serving: float
    protein_g_per_serving: float
    carbs_g_per_serving: float
    fats_g_per_serving: float
    fiber_g_per_serving: float
    source: str


class ExerciseSearchResult(BaseModel):
    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    instructions: Optional[str] = None


class ManualFoodCreate(BaseModel):
    food_name: str = Field(..., min_length=2, max_length=255)
    food_category: Optional[str] = Field(default=None, max_length=100)
    serving_size_g: float = Field(..., gt=0)
    serving_description: Optional[str] = Field(default="1 serving", max_length=100)
    calories_per_serving: float = Field(..., ge=0)
    protein_g_per_serving: float = Field(..., ge=0)
    carbs_g_per_serving: float = Field(..., ge=0)
    fats_g_per_serving: float = Field(..., ge=0)
    fiber_g_per_serving: Optional[float] = Field(default=0, ge=0)


class ManualExerciseCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    exercise_type: str = Field(default="Strength", max_length=50)
    primary_muscle_group: str = Field(default="Full Body", max_length=100)
    secondary_muscles: Optional[str] = Field(default=None, max_length=255)
    equipment_required: str = Field(default="Bodyweight", max_length=100)
    difficulty_level: str = Field(default="Beginner", max_length=50)
    location: str = Field(default="Any", max_length=50)
    instructions: Optional[str] = None


class ManualCentralFoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    source: str
    is_verified: bool
    is_public: bool


class ManualCentralExerciseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    instructions: Optional[str] = None
    source: str
    is_verified: bool
    is_public: bool
