from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Float, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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


class WorkoutPlan(Base):
    """AI-generated workout plan based on user profile and preferences"""
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workout_days = relationship("WorkoutDay", back_populates="workout_plan", cascade="all, delete-orphan")


class WorkoutDay(Base):
    """Individual workout day/session within a plan"""
    __tablename__ = "workout_days"
    
    id = Column(Integer, primary_key=True, index=True)
    workout_plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=False, index=True)
    
    day_name = Column(String(100), nullable=False, comment="e.g., 'Monday', 'Day 1', 'Upper Body'")
    day_number = Column(Integer, nullable=False, comment="Sequential day in plan")
    focus_area = Column(String(100), nullable=True, comment="e.g., 'Chest & Triceps', 'Legs'")
    estimated_duration = Column(Integer, nullable=True, comment="Session duration in minutes")
    notes = Column(Text, nullable=True, comment="Additional instructions for the day")
    
    # Relationships
    workout_plan = relationship("WorkoutPlan", back_populates="workout_days")
    exercises = relationship("Exercise", back_populates="workout_day", cascade="all, delete-orphan")


class Exercise(Base):
    """Individual exercise within a workout day"""
    __tablename__ = "exercises"
    
    id = Column(Integer, primary_key=True, index=True)
    workout_day_id = Column(Integer, ForeignKey("workout_days.id"), nullable=False, index=True)
    
    exercise_name = Column(String(255), nullable=False)
    exercise_type = Column(String(50), nullable=True, comment="Strength, Cardio, Flexibility, etc.")
    
    # Exercise parameters
    sets = Column(Integer, nullable=True)
    reps = Column(Integer, nullable=True, comment="Reps per set or total reps")
    weight_kg = Column(Float, nullable=True, comment="Recommended weight")
    duration_seconds = Column(Integer, nullable=True, comment="For time-based exercises")
    rest_seconds = Column(Integer, nullable=True, comment="Rest between sets")
    
    # Instructions & Media
    instructions = Column(Text, nullable=True)
    video_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    
    # Order
    order_index = Column(Integer, nullable=False, default=0, comment="Exercise order in the day")
    
    # Relationships
    workout_day = relationship("WorkoutDay", back_populates="exercises")


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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    meals = relationship("Meal", back_populates="nutrition_plan", cascade="all, delete-orphan")


class Meal(Base):
    """Recommended meal within a nutrition plan"""
    __tablename__ = "meals"
    
    id = Column(Integer, primary_key=True, index=True)
    nutrition_plan_id = Column(Integer, ForeignKey("nutrition_plans.id"), nullable=False, index=True)
    
    meal_type = Column(String(50), nullable=False, comment="Breakfast, Lunch, Dinner, Snack")
    meal_name = Column(String(255), nullable=False)
    
    # Nutritional info
    calories = Column(Integer, nullable=False)
    protein_g = Column(Integer, nullable=False)
    carbs_g = Column(Integer, nullable=False)
    fats_g = Column(Integer, nullable=False)
    
    # Recipe details
    ingredients = Column(Text, nullable=True, comment="List of ingredients")
    instructions = Column(Text, nullable=True, comment="Cooking instructions")
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    servings = Column(Integer, nullable=True, default=1)
    
    # Media
    image_url = Column(String(500), nullable=True)
    
    # Order
    order_index = Column(Integer, nullable=False, default=0, comment="Meal order in the day")
    
    # Relationships
    nutrition_plan = relationship("NutritionPlan", back_populates="meals")
