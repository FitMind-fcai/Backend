"""
DTOs (Data Transfer Objects) for AI Coach Service.
These are used to pass data to the AI Coach without coupling to any other module.
The AI Coach is completely modular and independent.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ========================================
# INPUT DTOs - What AI Coach receives
# ========================================

class UserProfileDTO(BaseModel):
    """DTO for user profile data needed by AI Coach."""
    age: int
    gender: str
    height: float = Field(..., description="Height in cm")
    weight: float = Field(..., description="Weight in kg")
    fitness_goal: str
    activity_level: str
    dietary_preference: Optional[str] = None
    medical_conditions: Optional[str] = None
    allergies: Optional[str] = None
    injuries: Optional[str] = None
    medications: Optional[str] = None

    def to_context_string(self) -> str:
        """Convert profile to context string for LLM prompt."""
        return f"""USER PROFILE:
- Age: {self.age}
- Gender: {self.gender}
- Height: {self.height} cm
- Weight: {self.weight} kg
- Fitness Goal: {self.fitness_goal}
- Activity Level: {self.activity_level}
- Dietary Preference: {self.dietary_preference or 'None'}
- Medical Conditions: {self.medical_conditions or 'None'}
- Allergies: {self.allergies or 'None'}
- Injuries: {self.injuries or 'None'}
- Medications: {self.medications or 'None'}"""


class WorkoutPreferencesDTO(BaseModel):
    """DTO for workout preferences."""
    workout_days_per_week: int = Field(..., ge=1, le=7)
    workout_location: str  # "Home", "Gym", "Outdoor"
    equipment_availability: str  # "No Equipment", "Basic", "Full Gym"
    workout_focus: str  # "Strength", "Cardio", "Flexibility", "Mixed"
    workout_difficulty: str  # "Beginner", "Intermediate", "Advanced"
    session_duration_minutes: int = Field(..., ge=15, le=180)
    focus_areas: Optional[List[str]] = None

    def to_context_string(self) -> str:
        """Convert preferences to context string for LLM prompt."""
        return f"""WORKOUT PREFERENCES:
- Days per Week: {self.workout_days_per_week}
- Location: {self.workout_location}
- Equipment: {self.equipment_availability}
- Focus: {self.workout_focus}
- Difficulty: {self.workout_difficulty}
- Session Duration: {self.session_duration_minutes} minutes
- Focus Areas: {', '.join(self.focus_areas) if self.focus_areas else 'General'}"""


class NutritionPreferencesDTO(BaseModel):
    """DTO for nutrition preferences."""
    calorie_preference: str  # "Deficit", "Maintenance", "Surplus", "Custom"
    custom_calorie_target: Optional[int] = Field(None, ge=1000, le=5000)
    meals_per_day: int = Field(..., ge=3, le=6)
    meal_complexity: str  # "Simple", "Moderate", "Complex"
    cuisine_preference: str  # "Any", "Mediterranean", "Asian", etc.
    exclude_ingredients: Optional[List[str]] = None

    def to_context_string(self) -> str:
        """Convert preferences to context string for LLM prompt."""
        calorie_info = self.custom_calorie_target if self.custom_calorie_target else self.calorie_preference
        return f"""NUTRITION PREFERENCES:
- Calorie Target: {calorie_info}
- Meals per Day: {self.meals_per_day}
- Meal Complexity: {self.meal_complexity}
- Cuisine Preference: {self.cuisine_preference}
- Excluded Ingredients: {', '.join(self.exclude_ingredients) if self.exclude_ingredients else 'None'}"""


class PlanGenerationRequestDTO(BaseModel):
    """DTO for plan generation request."""
    plan_type: str  # "WORKOUT_ONLY", "NUTRITION_ONLY", "BOTH"
    duration_weeks: int = Field(..., ge=1, le=52)
    workout_preferences: Optional[WorkoutPreferencesDTO] = None
    nutrition_preferences: Optional[NutritionPreferencesDTO] = None


# ========================================
# OUTPUT DTOs - What AI Coach returns
# ========================================

class ExerciseDTO(BaseModel):
    """DTO for a single exercise."""
    exercise_name: str
    exercise_type: Optional[str] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_kg: Optional[float] = None
    duration_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    instructions: Optional[str] = None
    video_url: Optional[str] = None
    image_url: Optional[str] = None
    order_index: int = 0


class WorkoutDayDTO(BaseModel):
    """DTO for a single workout day."""
    day_name: str
    day_number: int
    focus_area: Optional[str] = None
    estimated_duration: Optional[int] = None
    notes: Optional[str] = None
    exercises: List[ExerciseDTO] = []


class WorkoutPlanDTO(BaseModel):
    """DTO for generated workout plan."""
    plan_name: str
    description: Optional[str] = None
    frequency: Optional[str] = None
    difficulty_level: Optional[str] = None
    estimated_duration_per_session: Optional[int] = None
    workout_days: List[WorkoutDayDTO] = []

    def to_context_string(self) -> str:
        """Convert workout plan to context string for LLM prompt."""
        days_info = "\n".join(
            [f"- {day.day_name} (Day {day.day_number}): {len(day.exercises)} exercises" for day in self.workout_days]
        )
        return f"""WORKOUT PLAN:
        - Plan Name: {self.plan_name}
        - Description: {self.description or 'N/A'}
        - Frequency: {self.frequency or 'N/A'}
        - Difficulty Level: {self.difficulty_level or 'N/A'}
        - Estimated Duration per Session: {self.estimated_duration_per_session or 'N/A'} minutes
        {days_info}

        """


class MealDTO(BaseModel):
    """DTO for a single meal."""
    meal_type: str
    meal_name: str
    calories: float
    protein_g: float
    carbs_g: float
    fats_g: float
    fiber_g: Optional[float] = None
    ingredients: Optional[str] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    servings: int = 1
    order_index: int = 0


class NutritionDayDTO(BaseModel):
    """DTO for a single nutrition day (Mon-Sun)."""
    day_name: str
    day_number: int
    notes: Optional[str] = None
    meals: List[MealDTO] = []


class NutritionPlanDTO(BaseModel):
    """DTO for generated nutrition plan."""
    plan_name: str
    description: Optional[str] = None
    daily_calories: float
    daily_protein_g: float
    daily_carbs_g: float
    daily_fats_g: float
    days: List[NutritionDayDTO] = []

    def to_context_string(self) -> str:
        """Convert nutrition plan to context string for LLM prompt."""
        days_info = "\n".join(
            [
                f"- {day.day_name} (Day {day.day_number}): "
                + ", ".join(f"{m.meal_type}: {m.meal_name} ({m.calories} kcal)" for m in day.meals)
                for day in self.days
            ]
        )
        return f"""NUTRITION PLAN:
        - Plan Name: {self.plan_name}
        - Description: {self.description or 'N/A'}
        - Daily Calories: {self.daily_calories} kcal
        - Daily Protein: {self.daily_protein_g} g
        - Daily Carbs: {self.daily_carbs_g} g
        - Daily Fats: {self.daily_fats_g} g
        {days_info}

        """


class GeneratedPlansDTO(BaseModel):
    """DTO for generated plans result."""
    workout_plan: Optional[WorkoutPlanDTO] = None
    nutrition_plan: Optional[NutritionPlanDTO] = None
