"""
Converters for Planning Module.
Convert between DB models, schemas, and AI Coach DTOs.
"""
from datetime import date, timedelta
from typing import Optional

# AI Coach DTOs
from app.ai_services.ai_coach import (
    UserProfileDTO,
    WorkoutPreferencesDTO,
    NutritionPreferencesDTO,
    PlanGenerationRequestDTO,
    WorkoutPlanDTO,
    NutritionPlanDTO
)

# DB Models
from app.profile_module.models.profile import Profile

# Schemas
from app.planning_module.schemas.plan import (
    WorkoutPreferences,
    NutritionPreferences,
    WorkoutPlanCreate,
    WorkoutDayCreate,
    ExerciseCreate,
    NutritionPlanCreate,
    NutritionPlanDayCreate,
    MealCreate
)


# ========================================
# INPUT CONVERTERS: DB/Schema -> DTO
# ========================================

def profile_to_dto(profile: Profile) -> UserProfileDTO:
    """
    Convert Profile DB model to UserProfileDTO for AI Coach.
    
    Args:
        profile: Profile SQLAlchemy model instance
        
    Returns:
        UserProfileDTO for AI Coach consumption
    """
    return UserProfileDTO(
        age=profile.age,
        gender=profile.gender.value if hasattr(profile.gender, 'value') else str(profile.gender),
        height=profile.height,
        weight=profile.weight,
        fitness_goal=profile.fitness_goal.value if hasattr(profile.fitness_goal, 'value') else str(profile.fitness_goal),
        activity_level=profile.activity_level.value if hasattr(profile.activity_level, 'value') else str(profile.activity_level),
        dietary_preference=profile.dietary_preference if profile.dietary_preference else None,
        medical_conditions=profile.medical_conditions if profile.medical_conditions else None,
        allergies=profile.allergies if profile.allergies else None,
        injuries=profile.injuries if profile.injuries else None,
        medications=profile.medications if profile.medications else None
    )


def workout_preferences_to_dto(preferences: WorkoutPreferences) -> WorkoutPreferencesDTO:
    """
    Convert WorkoutPreferences schema to WorkoutPreferencesDTO for AI Coach.
    
    Args:
        preferences: WorkoutPreferences Pydantic schema
        
    Returns:
        WorkoutPreferencesDTO for AI Coach consumption
    """
    return WorkoutPreferencesDTO(
        workout_days_per_week=preferences.workout_days_per_week,
        workout_location=preferences.workout_location.value,
        equipment_availability=preferences.equipment_availability.value,
        workout_focus=preferences.workout_focus.value,
        workout_difficulty=preferences.workout_difficulty.value,
        session_duration_minutes=preferences.session_duration_minutes,
        focus_areas=preferences.focus_areas
    )


def nutrition_preferences_to_dto(preferences: NutritionPreferences) -> NutritionPreferencesDTO:
    """
    Convert NutritionPreferences schema to NutritionPreferencesDTO for AI Coach.
    
    Args:
        preferences: NutritionPreferences Pydantic schema
        
    Returns:
        NutritionPreferencesDTO for AI Coach consumption
    """
    return NutritionPreferencesDTO(
        calorie_preference=preferences.calorie_preference.value,
        custom_calorie_target=preferences.custom_calorie_target,
        meals_per_day=preferences.meals_per_day,
        meal_complexity=preferences.meal_complexity.value,
        cuisine_preference=preferences.cuisine_preference.value,
        exclude_ingredients=preferences.exclude_ingredients
    )





# ========================================
# OUTPUT CONVERTERS: DTO -> Schema (for DB)
# ========================================

def workout_plan_dto_to_create(
    dto: WorkoutPlanDTO,
    duration_weeks: int
) -> WorkoutPlanCreate:
    """
    Convert WorkoutPlanDTO from AI Coach to WorkoutPlanCreate schema for DB.
    
    Args:
        dto: WorkoutPlanDTO from AI Coach
        duration_weeks: Plan duration in weeks
        
    Returns:
        WorkoutPlanCreate schema ready for DB insertion
    """
    start_date = date.today()
    end_date = start_date + timedelta(weeks=duration_weeks)
    
    workout_days = []
    for day_dto in dto.workout_days:
        exercises = [
            ExerciseCreate(
                exercise_name=ex.exercise_name,
                exercise_type=ex.exercise_type,
                sets=ex.sets,
                reps=ex.reps,
                weight_kg=ex.weight_kg,
                duration_seconds=ex.duration_seconds,
                rest_seconds=ex.rest_seconds,
                instructions=ex.instructions,
                video_url=ex.video_url,
                image_url=ex.image_url,
                order_index=ex.order_index
            )
            for ex in day_dto.exercises
        ]
        
        workout_days.append(WorkoutDayCreate(
            day_name=day_dto.day_name,
            day_number=day_dto.day_number,
            focus_area=day_dto.focus_area,
            estimated_duration=day_dto.estimated_duration,
            notes=day_dto.notes,
            exercises=exercises
        ))
    
    return WorkoutPlanCreate(
        plan_name=dto.plan_name,
        description=dto.description,
        start_date=start_date,
        end_date=end_date,
        frequency=dto.frequency,
        difficulty_level=dto.difficulty_level,
        estimated_duration_per_session=dto.estimated_duration_per_session,
        workout_days=workout_days
    )


def nutrition_plan_dto_to_create(
    dto: NutritionPlanDTO,
    duration_weeks: int
) -> NutritionPlanCreate:
    """
    Convert NutritionPlanDTO from AI Coach to NutritionPlanCreate schema for DB.
    """
    start_date = date.today()
    end_date = start_date + timedelta(weeks=duration_weeks)

    days = [
        NutritionPlanDayCreate(
            day_number=day_dto.day_number,
            day_name=day_dto.day_name,
            notes=day_dto.notes,
            meals=[
                MealCreate(
                    meal_type=meal.meal_type,
                    meal_name=meal.meal_name,
                    calories=meal.calories,
                    protein_g=meal.protein_g,
                    carbs_g=meal.carbs_g,
                    fats_g=meal.fats_g,
                    ingredients=meal.ingredients,
                    instructions=meal.instructions,
                    prep_time_minutes=meal.prep_time_minutes,
                    cook_time_minutes=meal.cook_time_minutes,
                    servings=meal.servings,
                    image_url=meal.image_url,
                    order_index=meal.order_index
                )
                for meal in day_dto.meals
            ]
        )
        for day_dto in dto.days
    ]

    return NutritionPlanCreate(
        plan_name=dto.plan_name,
        description=dto.description,
        start_date=start_date,
        end_date=end_date,
        daily_calories=dto.daily_calories,
        daily_protein_g=dto.daily_protein_g,
        daily_carbs_g=dto.daily_carbs_g,
        daily_fats_g=dto.daily_fats_g,
        days=days
    )


# ========================================
# EXISTING PLAN CONVERTERS: DB Model -> DTO
# ========================================

def workout_plan_model_to_dto(plan) -> WorkoutPlanDTO:
    """
    Convert WorkoutPlan DB model to WorkoutPlanDTO for AI Coach.
    Used for passing existing plans to regeneration logic.
    """
    from app.ai_services.ai_coach.dtos import WorkoutDayDTO, ExerciseDTO

    workout_days = []
    for day in plan.workout_days:
        exercises = [
            ExerciseDTO(
                exercise_name=wde.central_exercise.name,
                exercise_type=wde.central_exercise.exercise_type,
                sets=wde.sets,
                reps=wde.reps,
                weight_kg=wde.weight_kg,
                duration_seconds=wde.duration_seconds,
                rest_seconds=wde.rest_seconds,
                instructions=wde.central_exercise.instructions,
                video_url=wde.central_exercise.video_url,
                image_url=wde.central_exercise.image_url,
                order_index=wde.order_index
            )
            for wde in day.exercises
        ]

        workout_days.append(WorkoutDayDTO(
            day_name=day.day_name,
            day_number=day.day_number,
            focus_area=day.focus_area,
            estimated_duration=day.estimated_duration,
            notes=day.notes,
            exercises=exercises
        ))

    return WorkoutPlanDTO(
        plan_name=plan.plan_name,
        description=plan.description,
        frequency=plan.frequency,
        difficulty_level=plan.difficulty_level,
        estimated_duration_per_session=plan.estimated_duration_per_session,
        workout_days=workout_days
    )


def nutrition_plan_model_to_dto(plan) -> NutritionPlanDTO:
    """
    Convert NutritionPlan DB model to NutritionPlanDTO for AI Coach.
    Used for passing existing plans to regeneration logic.
    """
    from app.ai_services.ai_coach.dtos import NutritionDayDTO, MealDTO

    days = [
        NutritionDayDTO(
            day_name=day.day_name,
            day_number=day.day_number,
            notes=day.notes,
            meals=[
                MealDTO(
                    meal_type=npm.meal_type,
                    meal_name=npm.meal_name,
                    calories=float(npm.calories),
                    protein_g=npm.protein_g,
                    carbs_g=npm.carbs_g,
                    fats_g=npm.fats_g,
                    fiber_g=npm.fiber_g,
                    ingredients=npm.ingredients,
                    instructions=npm.instructions,
                    prep_time_minutes=npm.prep_time_minutes,
                    cook_time_minutes=npm.cook_time_minutes,
                    servings=npm.servings,
                    order_index=npm.order_index
                )
                for npm in day.meals
            ]
        )
        for day in plan.days
    ]

    return NutritionPlanDTO(
        plan_name=plan.plan_name,
        description=plan.description,
        daily_calories=plan.daily_calories,
        daily_protein_g=plan.daily_protein_g,
        daily_carbs_g=plan.daily_carbs_g,
        daily_fats_g=plan.daily_fats_g,
        days=days
    )
