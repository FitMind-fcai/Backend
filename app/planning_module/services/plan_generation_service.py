"""
Combined Plan Generation Service.
Handles generation of both workout and nutrition plans together.
"""
from sqlalchemy.orm import Session
from typing import Optional
from app.planning_module.services.workout_plan_service import WorkoutPlanService
from app.planning_module.services.nutrition_plan_service import NutritionPlanService
from app.planning_module.repositories.workout_repository import (
    WorkoutPlanRepository,
    WorkoutDayRepository,
    ExerciseRepository
)
from app.planning_module.repositories.nutrition_repository import (
    NutritionPlanRepository,
    MealRepository
)
from app.planning_module.schemas.plan import (
    WorkoutPlanResponse,
    NutritionPlanResponse,
    CombinedPlanResponse,
    WorkoutPreferences,
    NutritionPreferences
)
from app.planning_module.models import WorkoutPlan, NutritionPlan
from app.profile_module.models.profile import Profile
from app.planning_module.services.converters import (
    profile_to_dto,
    workout_preferences_to_dto,
    nutrition_preferences_to_dto,
    workout_plan_dto_to_create,
    nutrition_plan_dto_to_create,
    workout_plan_model_to_dto,
    nutrition_plan_model_to_dto
)
from app.ai_services.ai_coach import get_ai_coach_service


class PlanGenerationService:

    def __init__(self, db: Session):
        self.db = db
        self.workout_service = WorkoutPlanService(db)
        self.nutrition_service = NutritionPlanService(db)
        # Repositories for creating plans
        self.workout_plan_repo = WorkoutPlanRepository(db)
        self.workout_day_repo = WorkoutDayRepository(db)
        self.exercise_repo = ExerciseRepository(db)
        self.nutrition_plan_repo = NutritionPlanRepository(db)
        self.meal_repo = MealRepository(db)
    
    def generate_workout_plan(
        self,
        profile: Profile,
        preferences: WorkoutPreferences,
        duration_weeks: int = 4
    ) -> WorkoutPlan:
        """
        Generate or update workout plan.
        Smart method that:
        - If no plan exists: Creates new plan
        - If plan exists: Updates it using existing plan as AI reference
        
        Args:
            profile: User's profile model (contains user_id)
            preferences: Workout preferences
            duration_weeks: Plan duration in weeks
            
        Returns:
            WorkoutPlan model (created or updated)
        """
        # Check if user already has an active workout plan
        existing_plan = self.workout_service.get_active_plan(profile.user_id)
        existing_plan_dto = None
        existing_plan_id = None
        
        if existing_plan:
            # Load full details and convert to DTO for AI context
            existing_plan_full = self.workout_service.get_plan_with_details(existing_plan.id)
            existing_plan_dto = workout_plan_model_to_dto(existing_plan_full)
            existing_plan_id = existing_plan.id
            # Delete old workout days and exercises for update
            self._delete_workout_plan_details(existing_plan_id)
        
        # Generate/update plan with existing plan context (if any)
        return self._generate_workout_plan(
            profile=profile,
            preferences=preferences,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan_dto,
            update_plan_id=existing_plan_id
        )
    
    def generate_nutrition_plan(
        self,
        profile: Profile,
        preferences: NutritionPreferences,
        duration_weeks: int = 4
    ) -> NutritionPlan:
        """
        Generate or update nutrition plan.
        Smart method that:
        - If no plan exists: Creates new plan
        - If plan exists: Updates it using existing plan as AI reference
        
        Args:
            profile: User's profile model (contains user_id)
            preferences: Nutrition preferences
            duration_weeks: Plan duration in weeks
            
        Returns:
            NutritionPlan model (created or updated)
        """
        # Check if user already has an active nutrition plan
        existing_plan = self.nutrition_service.get_active_plan(profile.user_id)
        existing_plan_dto = None
        existing_plan_id = None
        
        if existing_plan:
            # Load full details and convert to DTO for AI context
            existing_plan_full = self.nutrition_service.get_plan_with_meals(existing_plan.id)
            existing_plan_dto = nutrition_plan_model_to_dto(existing_plan_full)
            existing_plan_id = existing_plan.id
            # Delete old meals for update
            self._delete_nutrition_plan_details(existing_plan_id)
        
        # Generate/update plan with existing plan context (if any)
        return self._generate_nutrition_plan(
            profile=profile,
            preferences=preferences,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan_dto,
            update_plan_id=existing_plan_id
        )

    def get_user_active_plans(self, user_id: int) -> CombinedPlanResponse:
        """
        Get user's currently active workout and nutrition plans.
        
        Args:
            user_id: User ID
            
        Returns:
            CombinedPlanResponse with active plans
        """
        workout_plan = self.workout_service.get_active_plan(user_id)
        nutrition_plan = self.nutrition_service.get_active_plan(user_id)
        
        # Load full details if plans exist
        if workout_plan:
            workout_plan = self.workout_service.get_plan_with_details(workout_plan.id)
        if nutrition_plan:
            nutrition_plan = self.nutrition_service.get_plan_with_meals(nutrition_plan.id)
        
        message = "Active plans retrieved"
        if not workout_plan and not nutrition_plan:
            message = "No active plans found"
        
        return CombinedPlanResponse(
            workout_plan=WorkoutPlanResponse.model_validate(workout_plan) if workout_plan else None,
            nutrition_plan=NutritionPlanResponse.model_validate(nutrition_plan) if nutrition_plan else None,
            message=message
        )
    
    def _generate_workout_plan(
        self,
        profile: Profile,
        preferences: WorkoutPreferences,
        duration_weeks: int = 4,
        existing_plan=None,
        update_plan_id: int = None
    ) -> WorkoutPlan:
        """
        Generate a new workout plan using AI Coach service.
        
        Args:
            profile: User's profile model
            preferences: Workout preferences from request
            duration_weeks: Plan duration in weeks
            existing_plan: Optional existing plan DTO for regeneration
            
        Returns:
            Created WorkoutPlan model
        """
        # Convert to DTOs for AI Coach
        profile_dto = profile_to_dto(profile)
        preferences_dto = workout_preferences_to_dto(preferences)
        
        # Generate plan via AI Coach (with existing plan if regenerating)
        ai_coach = get_ai_coach_service()
        workout_plan_dto = ai_coach.generate_workout_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan
        )
        
        # Convert DTO to create schema
        plan_create = workout_plan_dto_to_create(workout_plan_dto, duration_weeks)
        
        # Store preferences used for generation
        preferences_dict = preferences.model_dump()
        
        # Create or update plan in database
        if update_plan_id:
            return self._update_workout_plan_with_details(
                plan_id=update_plan_id,
                plan_create=plan_create,
                generated_from_preferences=preferences_dict
            )
        else:
            return self._create_workout_plan_with_details(
                user_id=profile.user_id,
                profile_id=profile.id,
                plan_create=plan_create,
                generated_from_preferences=preferences_dict
            )
    
    def _generate_nutrition_plan(
        self,
        profile: Profile,
        preferences: NutritionPreferences,
        duration_weeks: int = 4,
        existing_plan=None,
        update_plan_id: int = None
    ) -> NutritionPlan:
        """
        Generate a new nutrition plan using AI Coach service.
        
        Args:
            profile: User's profile model
            preferences: Nutrition preferences from request
            duration_weeks: Plan duration in weeks
            existing_plan: Optional existing plan DTO for regeneration
            
        Returns:
            Created NutritionPlan model
        """
        # Convert to DTOs for AI Coach
        profile_dto = profile_to_dto(profile)
        preferences_dto = nutrition_preferences_to_dto(preferences)
        
        # Generate plan via AI Coach (with existing plan if regenerating)
        ai_coach = get_ai_coach_service()
        nutrition_plan_dto = ai_coach.generate_nutrition_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan
        )
        
        # Convert DTO to create schema
        plan_create = nutrition_plan_dto_to_create(nutrition_plan_dto, duration_weeks)
        
        # Store preferences used for generation
        preferences_dict = preferences.model_dump()
        
        # Create or update plan in database
        if update_plan_id:
            return self._update_nutrition_plan_with_meals(
                plan_id=update_plan_id,
                plan_create=plan_create,
                generated_from_preferences=preferences_dict
            )
        else:
            return self._create_nutrition_plan_with_meals(
                user_id=profile.user_id,
                profile_id=profile.id,
                plan_create=plan_create,
                generated_from_preferences=preferences_dict
            )
    
    def _create_workout_plan_with_details(
        self,
        user_id: int,
        profile_id: int,
        plan_create,
        generated_from_preferences: dict
    ) -> WorkoutPlan:
        """Create workout plan with all nested workout days and exercises."""
        # Create the plan
        plan_data = {
            "plan_name": plan_create.plan_name,
            "description": plan_create.description,
            "start_date": plan_create.start_date,
            "end_date": plan_create.end_date,
            "frequency": plan_create.frequency,
            "difficulty_level": plan_create.difficulty_level,
            "estimated_duration_per_session": plan_create.estimated_duration_per_session,
            "generated_from_preferences": generated_from_preferences
        }
        
        plan = self.workout_plan_repo.create_plan(
            user_id=user_id,
            profile_id=profile_id,
            plan_data=plan_data
        )
        
        # Create workout days and exercises
        for day_create in plan_create.workout_days:
            day_data = {
                "day_name": day_create.day_name,
                "day_number": day_create.day_number,
                "focus_area": day_create.focus_area,
                "estimated_duration": day_create.estimated_duration,
                "notes": day_create.notes
            }
            
            workout_day = self.workout_day_repo.create_workout_day(
                plan_id=plan.id,
                day_data=day_data
            )
            
            # Create exercises for this day
            for exercise_create in day_create.exercises:
                exercise_data = {
                    "exercise_name": exercise_create.exercise_name,
                    "exercise_type": exercise_create.exercise_type,
                    "sets": exercise_create.sets,
                    "reps": exercise_create.reps,
                    "weight_kg": exercise_create.weight_kg,
                    "duration_seconds": exercise_create.duration_seconds,
                    "rest_seconds": exercise_create.rest_seconds,
                    "instructions": exercise_create.instructions,
                    "video_url": exercise_create.video_url,
                    "image_url": exercise_create.image_url,
                    "order_index": exercise_create.order_index
                }
                
                self.exercise_repo.create_exercise(
                    day_id=workout_day.id,
                    exercise_data=exercise_data
                )
        
        # Return plan with full details loaded
        return self.workout_service.get_plan_with_details(plan.id)
    
    def _create_nutrition_plan_with_meals(
        self,
        user_id: int,
        profile_id: int,
        plan_create,
        generated_from_preferences: dict
    ) -> NutritionPlan:
        """Create nutrition plan with all meals."""
        # Create the plan
        plan_data = {
            "plan_name": plan_create.plan_name,
            "description": plan_create.description,
            "start_date": plan_create.start_date,
            "end_date": plan_create.end_date,
            "daily_calories": plan_create.daily_calories,
            "daily_protein_g": plan_create.daily_protein_g,
            "daily_carbs_g": plan_create.daily_carbs_g,
            "daily_fats_g": plan_create.daily_fats_g,
            "generated_from_preferences": generated_from_preferences
        }
        
        plan = self.nutrition_plan_repo.create_plan(
            user_id=user_id,
            profile_id=profile_id,
            plan_data=plan_data
        )
        
        # Create meals
        for meal_create in plan_create.meals:
            meal_data = {
                "meal_type": meal_create.meal_type,
                "meal_name": meal_create.meal_name,
                "calories": meal_create.calories,
                "protein_g": meal_create.protein_g,
                "carbs_g": meal_create.carbs_g,
                "fats_g": meal_create.fats_g,
                "ingredients": meal_create.ingredients,
                "instructions": meal_create.instructions,
                "prep_time_minutes": meal_create.prep_time_minutes,
                "cook_time_minutes": meal_create.cook_time_minutes,
                "servings": meal_create.servings,
                "image_url": meal_create.image_url,
                "order_index": meal_create.order_index
            }
            
            self.meal_repo.create_meal(
                plan_id=plan.id,
                meal_data=meal_data
            )
        
        # Return plan with meals loaded
        return self.nutrition_service.get_plan_with_meals(plan.id)
    

    
    def _delete_workout_plan_details(self, plan_id: int):
        """Delete all workout days and exercises for a plan (for update)"""
        # Get all workout days for this plan
        workout_days = (
            self.db.query(self.workout_day_repo.model)
            .filter(self.workout_day_repo.model.workout_plan_id == plan_id)
            .all()
        )
        
        # Delete exercises for each day, then delete the day
        for day in workout_days:
            # Delete exercises
            self.db.query(self.exercise_repo.model).filter(
                self.exercise_repo.model.workout_day_id == day.id
            ).delete()
            # Delete day
            self.db.query(self.workout_day_repo.model).filter(
                self.workout_day_repo.model.id == day.id
            ).delete()
        
        self.db.commit()
    
    def _delete_nutrition_plan_details(self, plan_id: int):
        """Delete all meals for a plan (for update)"""
        self.db.query(self.meal_repo.model).filter(
            self.meal_repo.model.nutrition_plan_id == plan_id
        ).delete()
        self.db.commit()
    
    def _update_workout_plan_with_details(
        self,
        plan_id: int,
        plan_create,
        generated_from_preferences: dict
    ) -> WorkoutPlan:
        """Update existing workout plan with new data."""
        # Update the plan
        plan_data = {
            "plan_name": plan_create.plan_name,
            "description": plan_create.description,
            "start_date": plan_create.start_date,
            "end_date": plan_create.end_date,
            "frequency": plan_create.frequency,
            "difficulty_level": plan_create.difficulty_level,
            "estimated_duration_per_session": plan_create.estimated_duration_per_session,
            "generated_from_preferences": generated_from_preferences
        }
        
        plan = self.workout_plan_repo.update_plan(plan_id, plan_data)
        
        # Create new workout days and exercises
        for day_create in plan_create.workout_days:
            day_data = {
                "day_name": day_create.day_name,
                "day_number": day_create.day_number,
                "focus_area": day_create.focus_area,
                "estimated_duration": day_create.estimated_duration,
                "notes": day_create.notes
            }
            
            workout_day = self.workout_day_repo.create_workout_day(
                plan_id=plan.id,
                day_data=day_data
            )
            
            # Create exercises for this day
            for exercise_create in day_create.exercises:
                exercise_data = {
                    "exercise_name": exercise_create.exercise_name,
                    "exercise_type": exercise_create.exercise_type,
                    "sets": exercise_create.sets,
                    "reps": exercise_create.reps,
                    "weight_kg": exercise_create.weight_kg,
                    "duration_seconds": exercise_create.duration_seconds,
                    "rest_seconds": exercise_create.rest_seconds,
                    "instructions": exercise_create.instructions,
                    "video_url": exercise_create.video_url,
                    "image_url": exercise_create.image_url,
                    "order_index": exercise_create.order_index
                }
                
                self.exercise_repo.create_exercise(
                    day_id=workout_day.id,
                    exercise_data=exercise_data
                )
        
        # Return plan with full details loaded
        return self.workout_service.get_plan_with_details(plan.id)
    
    def _update_nutrition_plan_with_meals(
        self,
        plan_id: int,
        plan_create,
        generated_from_preferences: dict
    ) -> NutritionPlan:
        """Update existing nutrition plan with new data."""
        # Update the plan
        plan_data = {
            "plan_name": plan_create.plan_name,
            "description": plan_create.description,
            "start_date": plan_create.start_date,
            "end_date": plan_create.end_date,
            "daily_calories": plan_create.daily_calories,
            "daily_protein_g": plan_create.daily_protein_g,
            "daily_carbs_g": plan_create.daily_carbs_g,
            "daily_fats_g": plan_create.daily_fats_g,
            "generated_from_preferences": generated_from_preferences
        }
        
        plan = self.nutrition_plan_repo.update_plan(plan_id, plan_data)
        
        # Create new meals
        for meal_create in plan_create.meals:
            meal_data = {
                "meal_type": meal_create.meal_type,
                "meal_name": meal_create.meal_name,
                "calories": meal_create.calories,
                "protein_g": meal_create.protein_g,
                "carbs_g": meal_create.carbs_g,
                "fats_g": meal_create.fats_g,
                "ingredients": meal_create.ingredients,
                "instructions": meal_create.instructions,
                "prep_time_minutes": meal_create.prep_time_minutes,
                "cook_time_minutes": meal_create.cook_time_minutes,
                "servings": meal_create.servings,
                "image_url": meal_create.image_url,
                "order_index": meal_create.order_index
            }
            
            self.meal_repo.create_meal(
                plan_id=plan.id,
                meal_data=meal_data
            )
        
        # Return plan with meals loaded
        return self.nutrition_service.get_plan_with_meals(plan.id)
