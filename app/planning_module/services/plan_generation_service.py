"""
Combined Plan Generation Service.
Handles generation of both workout and nutrition plans together.
"""
from sqlalchemy.orm import Session
from typing import Optional
from app.planning_module.services.workout_plan_service import WorkoutPlanService
from app.planning_module.services.nutrition_plan_service import NutritionPlanService
from app.planning_module.repositories.workout_repository import WorkoutPlanRepository
from app.planning_module.repositories.nutrition_repository import NutritionPlanRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository
from app.shared.repositories.central_food_repository import CentralFoodRepository
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
        self.workout_repo = WorkoutPlanRepository(db)
        self.central_exercise_repo = CentralExerciseRepository(db)
        self.nutrition_repo = NutritionPlanRepository(db)
        self.central_food_repo = CentralFoodRepository(db)
    
    def generate_workout_plan(
        self,
        profile: Profile,
        preferences: WorkoutPreferences,
        duration_weeks: int = 4
    ) -> dict:
        """
        Generate an AI workout plan DRAFT without saving it to the database.

        Returns a dict with:
          - draft_plan: WorkoutPlanCreate (the full generated structure)
          - generated_from_preferences: dict
          - update_plan_id: int | None (existing plan ID to replace, or None for new)

        The caller must explicitly call save_workout_plan() to persist.
        """
        existing_plan = self.workout_service.get_active_plan(profile.user_id)
        existing_plan_dto = None
        existing_plan_id = None

        if existing_plan:
            # Load full details as AI context — do NOT delete yet (user hasn't confirmed)
            existing_plan_full = self.workout_service.get_plan_with_details(existing_plan.id)
            existing_plan_dto = workout_plan_model_to_dto(existing_plan_full)
            existing_plan_id = existing_plan.id

        return self._generate_workout_draft(
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
    ) -> dict:
        """
        Generate an AI nutrition plan DRAFT without saving it to the database.

        Returns a dict with:
          - draft_plan: NutritionPlanCreate (7 days, meals, ingredients)
          - generated_from_preferences: dict
          - update_plan_id: int | None (existing plan ID to replace, or None for new)

        The caller must explicitly call save_nutrition_plan() to persist.
        """
        existing_plan = self.nutrition_service.get_active_plan(profile.user_id)
        existing_plan_dto = None
        existing_plan_id = None

        if existing_plan:
            # Load full details as AI context — do NOT delete yet (user hasn't confirmed)
            existing_plan_full = self.nutrition_service.get_plan_with_full_details(existing_plan.id)
            existing_plan_dto = nutrition_plan_model_to_dto(existing_plan_full)
            existing_plan_id = existing_plan.id

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
            nutrition_plan = self.nutrition_service.get_plan_with_full_details(nutrition_plan.id)
        
        message = "Active plans retrieved"
        if not workout_plan and not nutrition_plan:
            message = "No active plans found"
        
        return CombinedPlanResponse(
            workout_plan=WorkoutPlanResponse.model_validate(workout_plan) if workout_plan else None,
            nutrition_plan=NutritionPlanResponse.model_validate(nutrition_plan) if nutrition_plan else None,
            message=message
        )
    
    def save_workout_plan(
        self,
        user_id: int,
        profile_id: int,
        plan_create,
        generated_from_preferences: dict,
        update_plan_id: int = None
    ):
        """Persist a workout plan draft to the database (user-confirmed save)."""
        if update_plan_id:
            # Only NOW delete the old plan details before replacing
            self._delete_workout_plan_details(update_plan_id)
            return self._update_workout_plan_with_details(
                plan_id=update_plan_id,
                plan_create=plan_create,
                generated_from_preferences=generated_from_preferences
            )
        else:
            return self._create_workout_plan_with_details(
                user_id=user_id,
                profile_id=profile_id,
                plan_create=plan_create,
                generated_from_preferences=generated_from_preferences
            )

    def save_nutrition_plan(
        self,
        user_id: int,
        profile_id: int,
        plan_create,
        generated_from_preferences: dict,
        update_plan_id: int = None
    ):
        """Persist a nutrition plan draft to the database (user-confirmed save)."""
        if update_plan_id:
            # Only NOW delete the old plan details before replacing
            self._delete_nutrition_plan_details(update_plan_id)
            return self._update_nutrition_plan_with_meals(
                plan_id=update_plan_id,
                plan_create=plan_create,
                generated_from_preferences=generated_from_preferences
            )
        else:
            return self._create_nutrition_plan_with_meals(
                user_id=user_id,
                profile_id=profile_id,
                plan_create=plan_create,
                generated_from_preferences=generated_from_preferences
            )

    def _generate_workout_draft(
        self,
        profile: Profile,
        preferences: WorkoutPreferences,
        duration_weeks: int = 4,
        existing_plan=None,
        update_plan_id: int = None
    ) -> dict:
        """Internal: call AI and return WorkoutPlanCreate draft dict (no DB writes)."""
        profile_dto = profile_to_dto(profile)
        preferences_dto = workout_preferences_to_dto(preferences)

        # Get strict allowed exercises string based on user's equipment and difficulty
        allowed_exercises_str = self.central_exercise_repo.get_equipment_friendly_exercises_for_ai(
            equipment_availability=preferences.equipment_availability,
            workout_difficulty=preferences.workout_difficulty,
            limit=80
        )

        ai_coach = get_ai_coach_service()
        workout_plan_dto = ai_coach.generate_workout_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan,
            allowed_exercises_str=allowed_exercises_str
        )

        plan_create = workout_plan_dto_to_create(workout_plan_dto, duration_weeks)
        preferences_dict = preferences.model_dump()

        return {
            "draft_plan": plan_create,
            "generated_from_preferences": preferences_dict,
            "update_plan_id": update_plan_id
        }
    
    def _generate_nutrition_plan(
        self,
        profile: Profile,
        preferences: NutritionPreferences,
        duration_weeks: int = 4,
        existing_plan=None,
        update_plan_id: int = None
    ) -> dict:
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
        
        # Get strict allowed foods string based on user's selected diet preference
        allowed_foods_str = self.central_food_repo.get_diet_friendly_foods_for_ai(
            diet_type=profile.dietary_preference if hasattr(profile, 'dietary_preference') else "balanced",
            allergies=getattr(profile, 'allergies', ''),
            exclude_ingredients=getattr(preferences, 'exclude_ingredients', []),
            limit=50
        )
        
        # Generate plan via AI Coach (with existing plan if regenerating)
        ai_coach = get_ai_coach_service()
        nutrition_plan_dto = ai_coach.generate_nutrition_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan,
            allowed_foods_str=allowed_foods_str
        )
        
        # Convert DTO to create schema
        plan_create = nutrition_plan_dto_to_create(nutrition_plan_dto, duration_weeks)
        
        # Store preferences used for generation
        preferences_dict = preferences.model_dump()
        
        # Return the generated plan CREATE structure as a DRAFT.
        return {
            "draft_plan": plan_create,
            "generated_from_preferences": preferences_dict,
            "update_plan_id": update_plan_id
        }
    
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
        
        plan = self.workout_repo.create_plan(
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
            workout_day = self.workout_repo.create_day(plan_id=plan.id, day_data=day_data)

            for exercise_create in day_create.exercises:
                central_exercise = None
                
                # Use provided ID directly if available
                if getattr(exercise_create, 'central_exercise_id', None):
                    central_exercise = self.central_exercise_repo.get_by_id(exercise_create.central_exercise_id)
                
                # Fallback to name search or create new placeholder
                if not central_exercise:
                    catalog_data = {
                        "name": exercise_create.exercise_name,
                        "exercise_type": exercise_create.exercise_type or "Strength",
                        "primary_muscle_group": day_create.focus_area or "Full Body",
                        "equipment_required": "Bodyweight",
                        "difficulty_level": plan_create.difficulty_level or "Beginner",
                        "location": "Any",
                        "instructions": exercise_create.instructions,
                        "video_url": exercise_create.video_url,
                        "image_url": exercise_create.image_url,
                        "is_active": True
                    }
                    central_exercise = self.central_exercise_repo.find_or_create(catalog_data)
                slot_data = {
                    "sets": exercise_create.sets,
                    "reps": exercise_create.reps,
                    "weight_kg": exercise_create.weight_kg,
                    "duration_seconds": exercise_create.duration_seconds,
                    "rest_seconds": exercise_create.rest_seconds,
                    "order_index": exercise_create.order_index
                }
                self.workout_repo.create_exercise_slot(
                    day_id=workout_day.id,
                    central_exercise_id=central_exercise.id,
                    slot_data=slot_data
                )

        return self.workout_service.get_plan_with_details(plan.id)
    
    def _create_nutrition_plan_with_meals(
        self,
        user_id: int,
        profile_id: int,
        plan_create,
        generated_from_preferences: dict
    ) -> NutritionPlan:
        """Create nutrition plan with 7 days and their meals."""
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

        plan = self.nutrition_repo.create_plan(
            user_id=user_id,
            profile_id=profile_id,
            plan_data=plan_data
        )

        for day_create in plan_create.days:
            day_data = {
                "day_number": day_create.day_number,
                "day_name": day_create.day_name,
                "notes": day_create.notes
            }
            nutrition_day = self.nutrition_repo.create_day(plan_id=plan.id, day_data=day_data)

            for meal_create in day_create.meals:
                slot_data = {
                    "meal_type": meal_create.meal_type,
                    "meal_name": meal_create.meal_name,
                    "calories": int(meal_create.calories),
                    "protein_g": meal_create.protein_g,
                    "carbs_g": meal_create.carbs_g,
                    "fats_g": meal_create.fats_g,
                    "fiber_g": meal_create.fiber_g,
                    "ingredients": [ing.model_dump() for ing in (meal_create.ingredients or [])],
                    "instructions": meal_create.instructions,
                    "prep_time_minutes": meal_create.prep_time_minutes,
                    "cook_time_minutes": meal_create.cook_time_minutes,
                    "servings": float(meal_create.servings) if meal_create.servings else 1.0,
                    "order_index": meal_create.order_index
                }
                self.nutrition_repo.create_meal_slot(
                    day_id=nutrition_day.id,
                    slot_data=slot_data
                )

        return self.nutrition_service.get_plan_with_full_details(plan.id)
    

    
    def _delete_workout_plan_details(self, plan_id: int):
        """Delete all workout days and their junction rows for a plan (for update)"""
        for day in self.workout_repo.get_days_by_plan_id(plan_id):
            self.workout_repo.delete_exercise_slots_by_day_id(day.id)
            self.db.delete(day)
        self.db.commit()

    def _delete_nutrition_plan_details(self, plan_id: int):
        """Delete all nutrition days and their meal junction rows for a plan (for update)"""
        for day in self.nutrition_repo.get_days_by_plan_id(plan_id):
            self.nutrition_repo.delete_meal_slots_by_day_id(day.id)
            self.db.delete(day)
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
        
        plan = self.workout_repo.update_plan(plan_id, plan_data)

        for day_create in plan_create.workout_days:
            day_data = {
                "day_name": day_create.day_name,
                "day_number": day_create.day_number,
                "focus_area": day_create.focus_area,
                "estimated_duration": day_create.estimated_duration,
                "notes": day_create.notes
            }
            workout_day = self.workout_repo.create_day(plan_id=plan.id, day_data=day_data)

            for exercise_create in day_create.exercises:
                catalog_data = {
                    "name": exercise_create.exercise_name,
                    "exercise_type": exercise_create.exercise_type or "Strength",
                    "primary_muscle_group": day_create.focus_area or "Full Body",
                    "equipment_required": "Bodyweight",
                    "difficulty_level": plan_create.difficulty_level or "Beginner",
                    "location": "Any",
                    "instructions": exercise_create.instructions,
                    "video_url": exercise_create.video_url,
                    "image_url": exercise_create.image_url,
                    "is_active": True
                }
                central_exercise = self.central_exercise_repo.find_or_create(catalog_data)
                slot_data = {
                    "sets": exercise_create.sets,
                    "reps": exercise_create.reps,
                    "weight_kg": exercise_create.weight_kg,
                    "duration_seconds": exercise_create.duration_seconds,
                    "rest_seconds": exercise_create.rest_seconds,
                    "order_index": exercise_create.order_index
                }
                self.workout_repo.create_exercise_slot(
                    day_id=workout_day.id,
                    central_exercise_id=central_exercise.id,
                    slot_data=slot_data
                )

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

        plan = self.nutrition_repo.update_plan(plan_id, plan_data)

        for day_create in plan_create.days:
            day_data = {
                "day_number": day_create.day_number,
                "day_name": day_create.day_name,
                "notes": day_create.notes
            }
            nutrition_day = self.nutrition_repo.create_day(plan_id=plan.id, day_data=day_data)

            for meal_create in day_create.meals:
                slot_data = {
                    "meal_type": meal_create.meal_type,
                    "meal_name": meal_create.meal_name,
                    "calories": int(meal_create.calories),
                    "protein_g": meal_create.protein_g,
                    "carbs_g": meal_create.carbs_g,
                    "fats_g": meal_create.fats_g,
                    "fiber_g": meal_create.fiber_g,
                    "ingredients": [ing.model_dump() for ing in (meal_create.ingredients or [])],
                    "instructions": meal_create.instructions,
                    "prep_time_minutes": meal_create.prep_time_minutes,
                    "cook_time_minutes": meal_create.cook_time_minutes,
                    "servings": float(meal_create.servings) if meal_create.servings else 1.0,
                    "order_index": meal_create.order_index
                }
                self.nutrition_repo.create_meal_slot(
                    day_id=nutrition_day.id,
                    slot_data=slot_data
                )

        return self.nutrition_service.get_plan_with_full_details(plan.id)
