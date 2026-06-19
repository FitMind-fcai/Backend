from concurrent.futures import ThreadPoolExecutor
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
from app.planning_module.models import CentralFood
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
from app.ai_services.ai_coach.context_builder import get_context_builder
from app.planning_module.core.planning_engine import PlanningEngine


class PlanGenerationService:

    def __init__(self, db: Session):
        self.db = db
        self.workout_service = WorkoutPlanService(db)
        self.nutrition_service = NutritionPlanService(db)
        self.workout_repo = WorkoutPlanRepository(db)
        self.central_exercise_repo = CentralExerciseRepository(db)
        self.nutrition_repo = NutritionPlanRepository(db)
        self.central_food_repo = CentralFoodRepository(db)
        self.planning_engine = PlanningEngine()
    
    def generate_workout_plan(
        self,
        profile: Profile,
        preferences: WorkoutPreferences,
        duration_weeks: int = 4,
        lang: str = "en",
        model_override: str = None,
        skip_judge: bool = False,
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
            update_plan_id=existing_plan_id,
            lang=lang,
            model_override=model_override,
            skip_judge=skip_judge,
        )

    def generate_nutrition_plan(
        self,
        profile: Profile,
        preferences: NutritionPreferences,
        duration_weeks: int = 4,
        lang: str = "en",
        model_override: str = None,
        skip_judge: bool = False,
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
            update_plan_id=existing_plan_id,
            lang=lang,
            model_override=model_override,
            skip_judge=skip_judge,
        )

    def generate_combined_plans(
        self,
        profile: Profile,
        workout_preferences: "WorkoutPreferences",
        nutrition_preferences: "NutritionPreferences",
        duration_weeks: int = 4,
        lang: str = "en",
        model_override: str = None,
        skip_judge: bool = False,
    ) -> dict:
        """
        Generate workout and nutrition plan drafts concurrently.

        Both LLM generations run in parallel via ThreadPoolExecutor — cuts total
        wall-clock time roughly in half compared to calling each endpoint separately.
        Returns a dict with 'workout_draft' and 'nutrition_draft' keys.
        """
        with ThreadPoolExecutor(max_workers=2) as pool:
            workout_future = pool.submit(
                self.generate_workout_plan, profile, workout_preferences, duration_weeks, lang, model_override, skip_judge
            )
            nutrition_future = pool.submit(
                self.generate_nutrition_plan, profile, nutrition_preferences, duration_weeks, lang, model_override, skip_judge
            )
            workout_draft   = workout_future.result()
            nutrition_draft = nutrition_future.result()

        return {"workout_draft": workout_draft, "nutrition_draft": nutrition_draft}

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
            existing = self.workout_repo.get_by_id(update_plan_id)
            if not existing or existing.user_id != user_id:
                raise ValueError(f"Workout plan {update_plan_id} not found for this user")
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
        # Authoritative nutrition numbers are always computed on server from ingredients.
        self._hydrate_nutrition_macros_from_ingredients(plan_create)

        if update_plan_id:
            existing = self.nutrition_repo.get_by_id(update_plan_id)
            if not existing or existing.user_id != user_id:
                raise ValueError(f"Nutrition plan {update_plan_id} not found for this user")
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
        update_plan_id: int = None,
        lang: str = "en",
        model_override: str = None,
        skip_judge: bool = False,
    ) -> dict:
        """Internal: call AI and return WorkoutPlanCreate draft dict (no DB writes)."""
        profile_dto     = profile_to_dto(profile)
        preferences_dto = workout_preferences_to_dto(preferences)

        # Phase 1 — Planning Engine computes targets (fast, CPU-only; must run first
        # because the exercise DB query needs planning_output.goal)
        planning_output = self.planning_engine.compute(
            weight_kg=float(profile.weight or 70),
            height_cm=float(profile.height or 170),
            age=int(profile.age or 25),
            gender=profile.gender,
            activity_level=profile.activity_level,
            fitness_goal=profile.fitness_goal,
            training_days_per_week=int(preferences.workout_days_per_week or 4),
            session_duration_minutes=int(preferences.session_duration_minutes or 60),
        )

        ai_coach         = get_ai_coach_service()
        context_builder  = get_context_builder(ai_coach.llm)

        # Phase 2 — three independent tasks run in parallel:
        #   • DB exercise fetch   (SQL, ~100-200ms)
        #   • Context builder     (targeted RAG queries + fast LLM → KB-grounded rules)
        # Both depend only on planning_output which is already done.
        with ThreadPoolExecutor(max_workers=2) as pool:
            exercises_future = pool.submit(
                self.central_exercise_repo.get_equipment_friendly_exercises_for_ai,
                equipment_availability=preferences.equipment_availability,
                workout_difficulty=preferences.workout_difficulty,
                focus_areas=preferences.focus_areas,
                limit=60,
                goal=planning_output.goal,
                injuries=str(profile.injuries or ""),
            )
            rules_future = pool.submit(
                context_builder.build_workout_rules, profile_dto
            )
            allowed_exercises_str = exercises_future.result()
            medical_rules         = rules_future.result()

        # Phase 3 — LLM generation + single-pass judge/fix
        workout_plan_dto = ai_coach.generate_workout_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan,
            allowed_exercises_str=allowed_exercises_str,
            planning_output=planning_output,
            medical_rules=medical_rules,
            language=lang,
            model_override=model_override,
            skip_judge=skip_judge,
        )

        plan_create      = workout_plan_dto_to_create(workout_plan_dto, duration_weeks)
        plan_create.language = lang
        preferences_dict = preferences.model_dump()

        return {
            "draft_plan": plan_create,
            "generated_from_preferences": preferences_dict,
            "update_plan_id": update_plan_id,
        }
    
    def _generate_nutrition_plan(
        self,
        profile: Profile,
        preferences: NutritionPreferences,
        duration_weeks: int = 4,
        existing_plan=None,
        update_plan_id: int = None,
        lang: str = "en",
        model_override: str = None,
        skip_judge: bool = False,
    ) -> dict:
        """Internal: call AI and return NutritionPlanCreate draft dict (no DB writes)."""
        profile_dto     = profile_to_dto(profile)
        preferences_dto = nutrition_preferences_to_dto(preferences)

        # Phase 1 — Planning Engine computes macro targets (fast, CPU-only; must run
        # first because the food DB query needs planning_output.goal / calories / protein)
        planning_output = self.planning_engine.compute(
            weight_kg=float(profile.weight or 70),
            height_cm=float(profile.height or 170),
            age=int(profile.age or 25),
            gender=profile.gender,
            activity_level=profile.activity_level,
            fitness_goal=profile.fitness_goal,
            custom_calorie_target=getattr(preferences, "custom_calorie_target", None),
            meals_per_day=int(getattr(preferences, "meals_per_day", 3) or 3),
        )

        ai_coach        = get_ai_coach_service()
        context_builder = get_context_builder(ai_coach.llm)

        # Phase 2 — two independent tasks run in parallel:
        #   • DB food fetch       (SQL, ~100-200ms)
        #   • Context builder     (targeted RAG queries + fast LLM → KB-grounded rules)
        with ThreadPoolExecutor(max_workers=2) as pool:
            foods_future = pool.submit(
                self.central_food_repo.get_diet_friendly_foods_for_ai,
                diet_type=profile.dietary_preference if hasattr(profile, "dietary_preference") else "balanced",
                allergies=getattr(profile, "allergies", ""),
                exclude_ingredients=getattr(preferences, "exclude_ingredients", []),
                limit=50,
                goal=planning_output.goal,
                target_calories=planning_output.nutrition.calories,
                target_protein_g=planning_output.nutrition.protein_g,
            )
            rules_future = pool.submit(
                context_builder.build_nutrition_rules, profile_dto
            )
            allowed_foods_str = foods_future.result()
            medical_rules     = rules_future.result()

        # Phase 3 — LLM generation + single-pass judge/fix
        nutrition_plan_dto = ai_coach.generate_nutrition_plan(
            user_profile=profile_dto,
            preferences=preferences_dto,
            duration_weeks=duration_weeks,
            existing_plan=existing_plan,
            allowed_foods_str=allowed_foods_str,
            planning_output=planning_output,
            medical_rules=medical_rules,
            language=lang,
            model_override=model_override,
            skip_judge=skip_judge,
        )

        plan_create = nutrition_plan_dto_to_create(nutrition_plan_dto, duration_weeks)
        plan_create.language = lang

        # Authoritative macro numbers are always recomputed from DB ingredient records.
        self._hydrate_nutrition_macros_from_ingredients(plan_create)

        preferences_dict = preferences.model_dump()

        return {
            "draft_plan": plan_create,
            "generated_from_preferences": preferences_dict,
            "update_plan_id": update_plan_id,
        }

    def _hydrate_nutrition_macros_from_ingredients(self, nutrition_plan):
        """Compute meal/day/plan macros from ingredient amounts and central_food records."""
        referenced_food_ids = {
            ing.central_food_id
            for day in nutrition_plan.days
            for meal in day.meals
            for ing in (meal.ingredients or [])
        }

        foods_by_id = {}
        if referenced_food_ids:
            foods = (
                self.db.query(CentralFood)
                .filter(CentralFood.id.in_(list(referenced_food_ids)))
                .all()
            )
            foods_by_id = {food.id: food for food in foods}

        day_totals = []
        for day in nutrition_plan.days:
            day_calories = day_protein = day_carbs = day_fats = 0.0
            for meal in day.meals:
                meal_calories = meal_protein = meal_carbs = meal_fats = meal_fiber = 0.0

                for ing in (meal.ingredients or []):
                    food = foods_by_id.get(ing.central_food_id)
                    if not food:
                        continue
                    amount_g = float(ing.amount_g or 0)
                    if amount_g <= 0:
                        continue
                    ratio = amount_g / 100.0
                    meal_calories += float(food.calories_per_100g) * ratio
                    meal_protein += float(food.protein_per_100g) * ratio
                    meal_carbs += float(food.carbs_per_100g) * ratio
                    meal_fats += float(food.fats_per_100g) * ratio
                    meal_fiber += float(food.fiber_per_100g or 0.0) * ratio

                meal.calories = round(meal_calories, 1)
                meal.protein_g = round(meal_protein, 2)
                meal.carbs_g = round(meal_carbs, 2)
                meal.fats_g = round(meal_fats, 2)
                meal.fiber_g = round(meal_fiber, 2)

                day_calories += meal_calories
                day_protein += meal_protein
                day_carbs += meal_carbs
                day_fats += meal_fats

            day_totals.append((day_calories, day_protein, day_carbs, day_fats))

        if day_totals:
            days_count = float(len(day_totals))
            nutrition_plan.daily_calories = round(sum(x[0] for x in day_totals) / days_count, 1)
            nutrition_plan.daily_protein_g = round(sum(x[1] for x in day_totals) / days_count, 2)
            nutrition_plan.daily_carbs_g = round(sum(x[2] for x in day_totals) / days_count, 2)
            nutrition_plan.daily_fats_g = round(sum(x[3] for x in day_totals) / days_count, 2)

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
            "generated_from_preferences": generated_from_preferences,
            "language": getattr(plan_create, "language", "en"),
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
            "generated_from_preferences": generated_from_preferences,
            "language": getattr(plan_create, "language", "en"),
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
            "generated_from_preferences": generated_from_preferences,
            "language": getattr(plan_create, "language", "en"),
        }

        plan = self.workout_repo.update_plan(plan_id, plan_data)
        if plan is None:
            raise ValueError(f"Workout plan {plan_id} not found")

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
            "generated_from_preferences": generated_from_preferences,
            "language": getattr(plan_create, "language", "en"),
        }

        plan = self.nutrition_repo.update_plan(plan_id, plan_data)
        if plan is None:
            raise ValueError(f"Nutrition plan {plan_id} not found")

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
