from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Float, Text, JSON # type: ignore
from sqlalchemy.sql import func # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from pgvector.sqlalchemy import Vector # type: ignore
from app.db.database import Base
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
# CATALOG TABLES
# ========================================

class CentralExercise(Base):
    """Central exercise catalog — admin-populated, shared across all users"""
    __tablename__ = "central_exercises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    exercise_type = Column(String(50), nullable=False, default="Strength")
    primary_muscle_group = Column(String(100), nullable=False, default="Full Body")
    secondary_muscles = Column(String(255), nullable=True)
    equipment_required = Column(String(100), nullable=False, default="Bodyweight")
    difficulty_level = Column(String(50), nullable=False, default="Beginner")
    location = Column(String(50), nullable=False, default="Any")
    instructions = Column(Text, nullable=True)
    video_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    source = Column(String(50), nullable=False, default="System")
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    is_verified = Column(Boolean, nullable=False, default=True, index=True)
    is_public = Column(Boolean, nullable=False, default=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    name_embedding = Column(Vector(384), nullable=True, comment="paraphrase-multilingual-MiniLM-L12-v2 embedding of name for vector similarity search")

    # Relationships
    exercises = relationship("WorkoutDayExercise", back_populates="central_exercise")


class CentralFood(Base):
    """Central food catalog — USDA Foundation Foods + manual entries, shared across all modules"""
    __tablename__ = "central_foods"

    id = Column(Integer, primary_key=True, index=True)
    food_name = Column(String(255), nullable=False, index=True)
    food_name_ar = Column(String(255), nullable=True)
    food_category = Column(String(100), nullable=True, index=True)

    # Macros per 100g (USDA standard) — multiply by (serving_size_g / 100) for per-serving values
    calories_per_100g = Column(Float, nullable=False)
    protein_per_100g = Column(Float, nullable=False)
    carbs_per_100g = Column(Float, nullable=False)
    fats_per_100g = Column(Float, nullable=False)
    fiber_per_100g = Column(Float, nullable=True)

    # Serving info
    serving_size_g = Column(Float, nullable=True, comment="Gram weight of one standard serving")
    serving_description = Column(String(100), nullable=True, comment="e.g. '1 cup', '1 medium apple'")

    # Metadata
    dietary_tags = Column(JSON, nullable=True, default=list)
    usda_fdc_id = Column(Integer, nullable=True, index=True)
    name_embedding = Column(Vector(384), nullable=True, comment="paraphrase-multilingual-MiniLM-L12-v2 embedding of food_name for vector similarity search")
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    is_verified = Column(Boolean, nullable=False, default=True, index=True)
    is_public = Column(Boolean, nullable=False, default=True, index=True)
    source = Column(String(50), nullable=False, default="USDA")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Reverse relationship — allows eager loading via ingredient → food
    plan_meal_usages = relationship("NutritionPlanMealIngredient", back_populates="food", lazy="dynamic")


# ========================================
# PLANNING TABLES
# ========================================

class WorkoutPlan(Base):
    __tablename__ = "workout_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, index=True, comment="Profile used for plan generation")
    
    plan_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    
    # Plan metadata
    frequency = Column(String(100), nullable=True, comment="e.g., '4 days per week'")
    difficulty_level = Column(String(50), nullable=True)
    estimated_duration_per_session = Column(Integer, nullable=True, comment="Minutes per session")
    
    # Store preferences that generated this plan (for history and regeneration)
    generated_from_preferences = Column(JSON, nullable=True, comment="User preferences used to generate this plan")
    language = Column(String(5), nullable=True, default="en", comment="Language the plan was generated in: en | ar")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workout_days = relationship("WorkoutDay", back_populates="workout_plan", cascade="all, delete-orphan")


class WorkoutDay(Base):
    """Individual workout day/session within a plan"""
    __tablename__ = "workout_days"

    id = Column(Integer, primary_key=True, index=True)
    workout_plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=False, index=True)

    day_name = Column(String(100), nullable=False)
    day_number = Column(Integer, nullable=False)
    focus_area = Column(String(100), nullable=True)
    estimated_duration = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    workout_plan = relationship("WorkoutPlan", back_populates="workout_days")
    exercises = relationship("WorkoutDayExercise", back_populates="workout_day", cascade="all, delete-orphan")


class WorkoutDayExercise(Base):
    """Junction: links a workout day to a central exercise + plan-specific parameters"""
    __tablename__ = "workout_day_exercises"

    id = Column(Integer, primary_key=True, index=True)
    workout_day_id = Column(Integer, ForeignKey("workout_days.id"), nullable=False, index=True)
    central_exercise_id = Column(Integer, ForeignKey("central_exercises.id"), nullable=False, index=True)

    sets = Column(Integer, nullable=True)
    reps = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    rest_seconds = Column(Integer, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)

    # Relationships
    workout_day = relationship("WorkoutDay", back_populates="exercises")
    central_exercise = relationship("CentralExercise", back_populates="exercises")


class NutritionPlan(Base):
    """AI-generated nutrition plan based on user profile and preferences"""
    __tablename__ = "nutrition_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, index=True, comment="Profile used for plan generation")
    
    plan_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    
    # Macronutrient targets
    daily_calories = Column(Integer, nullable=False)
    daily_protein_g = Column(Integer, nullable=False)
    daily_carbs_g = Column(Integer, nullable=False)
    daily_fats_g = Column(Integer, nullable=False)
    
    # Store preferences that generated this plan (for history and regeneration)
    generated_from_preferences = Column(JSON, nullable=True, comment="User preferences used to generate this plan")
    language = Column(String(5), nullable=True, default="en", comment="Language the plan was generated in: en | ar")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    days = relationship("NutritionPlanDay", back_populates="nutrition_plan", cascade="all, delete-orphan", order_by="NutritionPlanDay.day_number")


class NutritionPlanDay(Base):
    """Individual day (Mon-Sun) within a nutrition plan"""
    __tablename__ = "nutrition_plan_days"

    id = Column(Integer, primary_key=True, index=True)
    nutrition_plan_id = Column(Integer, ForeignKey("nutrition_plans.id"), nullable=False, index=True)
    day_number = Column(Integer, nullable=False)
    day_name = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    # Relationships
    nutrition_plan = relationship("NutritionPlan", back_populates="days")
    meals = relationship("NutritionPlanMeal", back_populates="nutrition_plan_day", cascade="all, delete-orphan", order_by="NutritionPlanMeal.order_index")


class NutritionPlanMeal(Base):
    """AI-generated meal within a nutrition plan day — fully self-contained, no FK to food catalog"""
    __tablename__ = "nutrition_plan_meals"

    id = Column(Integer, primary_key=True, index=True)
    nutrition_plan_day_id = Column(Integer, ForeignKey("nutrition_plan_days.id"), nullable=False, index=True)

    # Meal classification
    meal_type = Column(String(50), nullable=False)
    meal_name = Column(String(255), nullable=False)

    # Macros (AI-calculated)
    calories = Column(Integer, nullable=False)
    protein_g = Column(Float, nullable=False)
    carbs_g = Column(Float, nullable=False)
    fats_g = Column(Float, nullable=False)
    fiber_g = Column(Float, nullable=True)

    # Meal details
    # ingredients = Column(Text, nullable=True) # DEPRECATED: Replaced by relational table
    instructions = Column(Text, nullable=True)
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)

    servings = Column(Float, nullable=False, default=1.0)
    order_index = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)

    # Relationships
    nutrition_plan_day = relationship("NutritionPlanDay", back_populates="meals")
    ingredients = relationship("NutritionPlanMealIngredient", back_populates="meal", cascade="all, delete-orphan")


class NutritionPlanMealIngredient(Base):
    """Relational map between a drafted meal and the Central Food database"""
    __tablename__ = "nutrition_plan_meal_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    nutrition_plan_meal_id = Column(Integer, ForeignKey("nutrition_plan_meals.id"), nullable=False, index=True)
    central_food_id = Column(Integer, ForeignKey("central_foods.id"), nullable=False, index=True)
    amount_g = Column(Float, nullable=False)

    # Relationships
    meal = relationship("NutritionPlanMeal", back_populates="ingredients")
    food = relationship("CentralFood", back_populates="plan_meal_usages", lazy="joined")
    # ^ lazy='joined' means every ingredient query automatically JOINs central_foods —
    #   zero extra round-trips, one SQL statement.
