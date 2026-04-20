from datetime import date
from typing import Optional

from fastapi import HTTPException, status

from app.tracking_module.models.enums import LogMethod
from app.tracking_module.repositories.workout_log_repository import WorkoutLogRepository
from app.tracking_module.repositories.meal_log_repository import MealLogRepository
from app.tracking_module.repositories.weight_log_repository import WeightLogRepository
from app.shared.repositories.central_food_repository import CentralFoodRepository
from app.shared.repositories.central_exercise_repository import CentralExerciseRepository
from app.tracking_module.schemas.tracking import (
    WorkoutLogCreateText,
    MealLogCreateText,
    WeightLogCreateText,
    ManualFoodCreate,
    ManualExerciseCreate,
)


class TrackingService:
    def __init__(
        self,
        workout_repo: WorkoutLogRepository,
        meal_repo: MealLogRepository,
        weight_repo: WeightLogRepository,
        central_food_repo: CentralFoodRepository,
        central_exercise_repo: CentralExerciseRepository,
    ):
        self.workout_repo = workout_repo
        self.meal_repo = meal_repo
        self.weight_repo = weight_repo
        self.central_food_repo = central_food_repo
        self.central_exercise_repo = central_exercise_repo

    def create_workout_log_text(self, user_id: int, payload: WorkoutLogCreateText):
        return self.workout_repo.create_log(
            user_id=user_id,
            central_exercise_id=payload.central_exercise_id,
            workout_day_exercise_id=payload.workout_day_exercise_id,
            log_date=payload.log_date,
            sets_completed=payload.sets_completed,
            reps_completed=payload.reps_completed,
            weight_used=payload.weight_used,
            duration_seconds=payload.duration_seconds,
            notes=payload.notes.strip() if payload.notes else None,
        )

    def list_workout_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None):
        return self.workout_repo.list_logs(user_id=user_id, skip=skip, limit=limit, log_date=log_date)

    def get_workout_log(self, user_id: int, log_id: int):
        log = self.workout_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout log not found.")
        return log

    def delete_workout_log(self, user_id: int, log_id: int):
        log = self.get_workout_log(user_id=user_id, log_id=log_id)
        self.workout_repo.delete(log.id)
        return {"message": "Workout log deleted successfully."}

    def create_meal_log_text(self, user_id: int, payload: MealLogCreateText):
        serving_size_g_snapshot = payload.serving_size_g_snapshot
        serving_description_snapshot = payload.serving_description_snapshot
        meal_name = payload.meal_name.strip() if payload.meal_name else None

        calories = payload.calories
        protein_g = payload.protein_g
        carbs_g = payload.carbs_g
        fats_g = payload.fats_g

        if payload.central_food_id is not None:
            food = self.central_food_repo.get_by_id(payload.central_food_id)
            if not food:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Central food not found.",
                )
            serving_size_g_snapshot = float(food.serving_size_g or 100.0)
            serving_description_snapshot = food.serving_description or f"{serving_size_g_snapshot:g} g"
            meal_name = meal_name or food.food_name

            # Auto-calculate totals from central per-100g values and consumed servings.
            grams_consumed = serving_size_g_snapshot * payload.servings
            multiplier = grams_consumed / 100.0
            calories = (food.calories_per_100g or 0) * multiplier
            protein_g = (food.protein_per_100g or 0) * multiplier
            carbs_g = (food.carbs_per_100g or 0) * multiplier
            fats_g = (food.fats_per_100g or 0) * multiplier
        elif not serving_description_snapshot:
            serving_description_snapshot = "manual serving"

        return self.meal_repo.create_log(
            user_id=user_id,
            central_food_id=payload.central_food_id,
            log_date=payload.log_date,
            meal_type=payload.meal_type.strip(),
            meal_name=meal_name,
            servings=payload.servings,
            serving_size_g_snapshot=serving_size_g_snapshot,
            serving_description_snapshot=serving_description_snapshot,
            calories=round(calories, 2),
            protein_g=round(protein_g, 2),
            carbs_g=round(carbs_g, 2),
            fats_g=round(fats_g, 2),
            log_method=LogMethod.TEXT.value,
            image_url=None,
        )

    def list_meal_logs(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
    ):
        return self.meal_repo.list_logs(
            user_id=user_id,
            skip=skip,
            limit=limit,
            log_date=log_date,
            meal_type=meal_type,
        )

    def get_meal_log(self, user_id: int, log_id: int):
        log = self.meal_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal log not found.")
        return log

    def delete_meal_log(self, user_id: int, log_id: int):
        log = self.get_meal_log(user_id=user_id, log_id=log_id)
        self.meal_repo.delete(log.id)
        return {"message": "Meal log deleted successfully."}

    def create_weight_log_text(self, user_id: int, payload: WeightLogCreateText):
        return self.weight_repo.create_log(
            user_id=user_id,
            log_date=payload.log_date,
            weight=payload.weight,
            notes=payload.notes.strip() if payload.notes else None,
        )

    def list_weight_logs(self, user_id: int, skip: int = 0, limit: int = 50, log_date: Optional[date] = None):
        return self.weight_repo.list_logs(user_id=user_id, skip=skip, limit=limit, log_date=log_date)

    def get_weight_log(self, user_id: int, log_id: int):
        log = self.weight_repo.get_by_id(log_id)
        if not log or log.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weight log not found.")
        return log

    def delete_weight_log(self, user_id: int, log_id: int):
        log = self.get_weight_log(user_id=user_id, log_id=log_id)
        self.weight_repo.delete(log.id)
        return {"message": "Weight log deleted successfully."}

    def search_foods(self, user_id: int, query: str, limit: int = 20):
        foods = self.central_food_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)
        results = []
        for food in foods:
            serving_size = float(food.serving_size_g or 100.0)
            multiplier = serving_size / 100.0
            results.append(
                {
                    "id": food.id,
                    "food_name": food.food_name,
                    "food_category": food.food_category,
                    "serving_size_g": serving_size,
                    "serving_description": food.serving_description or f"{serving_size:g} g",
                    "calories_per_serving": round((food.calories_per_100g or 0) * multiplier, 2),
                    "protein_g_per_serving": round((food.protein_per_100g or 0) * multiplier, 2),
                    "carbs_g_per_serving": round((food.carbs_per_100g or 0) * multiplier, 2),
                    "fats_g_per_serving": round((food.fats_per_100g or 0) * multiplier, 2),
                    "fiber_g_per_serving": round((food.fiber_per_100g or 0) * multiplier, 2),
                    "source": food.source,
                }
            )
        return results

    def search_exercises(self, user_id: int, query: str, limit: int = 20):
        return self.central_exercise_repo.search_for_tracking(query=query.strip(), user_id=user_id, limit=limit)

    def create_manual_food(self, user_id: int, payload: ManualFoodCreate):
        factor = 100.0 / payload.serving_size_g
        food_data = {
            "food_name": payload.food_name.strip(),
            "food_category": payload.food_category,
            "calories_per_100g": payload.calories_per_serving * factor,
            "protein_per_100g": payload.protein_g_per_serving * factor,
            "carbs_per_100g": payload.carbs_g_per_serving * factor,
            "fats_per_100g": payload.fats_g_per_serving * factor,
            "fiber_per_100g": (payload.fiber_g_per_serving or 0) * factor,
            "serving_size_g": payload.serving_size_g,
            "serving_description": payload.serving_description,
            "dietary_tags": [],
            "usda_fdc_id": None,
        }
        return self.central_food_repo.create_manual_food(user_id=user_id, food_data=food_data)

    def create_manual_exercise(self, user_id: int, payload: ManualExerciseCreate):
        exercise_data = {
            "name": payload.name.strip(),
            "exercise_type": payload.exercise_type,
            "primary_muscle_group": payload.primary_muscle_group,
            "secondary_muscles": payload.secondary_muscles,
            "equipment_required": payload.equipment_required,
            "difficulty_level": payload.difficulty_level,
            "location": payload.location,
            "instructions": payload.instructions,
            "video_url": None,
            "image_url": None,
        }
        return self.central_exercise_repo.create_manual_exercise(user_id=user_id, exercise_data=exercise_data)
