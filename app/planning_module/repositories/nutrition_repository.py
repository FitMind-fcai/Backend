from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc
from typing import List, Optional
from datetime import date
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import NutritionPlan, NutritionPlanDay, NutritionPlanMeal


class NutritionPlanRepository(BaseRepository[NutritionPlan]):
    """Single repository for all nutrition plan operations (plan, days, meal slots)"""

    def __init__(self, db: Session):
        super().__init__(NutritionPlan, db)

    # ------------------------------------------------------------------
    # Plan queries
    # ------------------------------------------------------------------

    def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 10) -> List[NutritionPlan]:
        return (
            self.db.query(NutritionPlan)
            .filter(NutritionPlan.user_id == user_id)
            .order_by(desc(NutritionPlan.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_plan(self, user_id: int) -> Optional[NutritionPlan]:
        today = date.today()
        return (
            self.db.query(NutritionPlan)
            .filter(
                NutritionPlan.user_id == user_id,
                NutritionPlan.start_date <= today,
                (NutritionPlan.end_date >= today) | (NutritionPlan.end_date.is_(None))
            )
            .order_by(desc(NutritionPlan.created_at))
            .first()
        )

    def get_with_full_details(self, plan_id: int) -> Optional[NutritionPlan]:
        """Eagerly load plan -> days -> meals -> ingredients (+ joined food details).
        
        A single SQL round-trip chain:
          1. SELECT nutrition_plan WHERE id = plan_id
          2. SELECT nutrition_plan_days WHERE nutrition_plan_id IN (...)
          3. SELECT nutrition_plan_meals WHERE nutrition_plan_day_id IN (...)
          4. SELECT nutrition_plan_meal_ingredients
               JOIN central_foods ON ...
               WHERE nutrition_plan_meal_id IN (...)
        
        No N+1 queries. The JOIN on central_foods is free because the
        NutritionPlanMealIngredient.food relationship uses lazy='joined'.
        """
        from app.planning_module.models.plan import NutritionPlanMeal, NutritionPlanMealIngredient
        return (
            self.db.query(NutritionPlan)
            .options(
                selectinload(NutritionPlan.days)
                .selectinload(NutritionPlanDay.meals)
                .selectinload(NutritionPlanMeal.ingredients)   # ingredients JOIN food is automatic
            )
            .filter(NutritionPlan.id == plan_id)
            .first()
        )


    def create_plan(self, user_id: int, profile_id: int, plan_data: dict) -> NutritionPlan:
        plan = NutritionPlan(user_id=user_id, profile_id=profile_id, **plan_data)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def update_plan(self, plan_id: int, plan_data: dict) -> Optional[NutritionPlan]:
        plan = self.get_by_id(plan_id)
        if plan:
            for key, value in plan_data.items():
                setattr(plan, key, value)
            self.db.commit()
            self.db.refresh(plan)
        return plan

    def delete_plan(self, plan_id: int) -> bool:
        plan = self.get_by_id(plan_id)
        if plan:
            self.db.delete(plan)
            self.db.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Day queries
    # ------------------------------------------------------------------

    def get_days_by_plan_id(self, plan_id: int) -> List[NutritionPlanDay]:
        return (
            self.db.query(NutritionPlanDay)
            .filter(NutritionPlanDay.nutrition_plan_id == plan_id)
            .order_by(NutritionPlanDay.day_number)
            .all()
        )

    def get_day_by_id(self, day_id: int) -> Optional[NutritionPlanDay]:
        return self.db.query(NutritionPlanDay).filter(NutritionPlanDay.id == day_id).first()

    def create_day(self, plan_id: int, day_data: dict) -> NutritionPlanDay:
        day = NutritionPlanDay(nutrition_plan_id=plan_id, **day_data)
        self.db.add(day)
        self.db.commit()
        self.db.refresh(day)
        return day

    # ------------------------------------------------------------------
    # Meal slot queries
    # ------------------------------------------------------------------

    def get_meals_by_day_id(self, day_id: int) -> List[NutritionPlanMeal]:
        return (
            self.db.query(NutritionPlanMeal)
            .filter(NutritionPlanMeal.nutrition_plan_day_id == day_id)
            .order_by(NutritionPlanMeal.order_index)
            .all()
        )

    def get_meals_by_type(self, day_id: int, meal_type: str) -> List[NutritionPlanMeal]:
        return (
            self.db.query(NutritionPlanMeal)
            .filter(
                NutritionPlanMeal.nutrition_plan_day_id == day_id,
                NutritionPlanMeal.meal_type == meal_type
            )
            .order_by(NutritionPlanMeal.order_index)
            .all()
        )

    def get_meal_by_id(self, meal_id: int) -> Optional[NutritionPlanMeal]:
        return self.db.query(NutritionPlanMeal).filter(NutritionPlanMeal.id == meal_id).first()

    def create_meal_slot(self, day_id: int, slot_data: dict) -> NutritionPlanMeal:
        from app.planning_module.models.plan import NutritionPlanMealIngredient
        ingredients_data = slot_data.pop("ingredients", [])
        
        slot = NutritionPlanMeal(nutrition_plan_day_id=day_id, **slot_data)
        
        for ing_data in ingredients_data:
            # We assume ing_data is a dict with central_food_id and amount_g
            slot.ingredients.append(NutritionPlanMealIngredient(**ing_data))
            
        self.db.add(slot)
        self.db.commit()
        self.db.refresh(slot)
        return slot

    def delete_meal_slots_by_day_id(self, day_id: int):
        self.db.query(NutritionPlanMeal).filter(
            NutritionPlanMeal.nutrition_plan_day_id == day_id
        ).delete()
        self.db.commit()


