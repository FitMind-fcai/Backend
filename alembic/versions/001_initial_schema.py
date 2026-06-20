"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ENUM types ---
    gender_enum = sa.Enum("MALE", "FEMALE", name="gender")
    activity_enum = sa.Enum("SEDENTARY", "LIGHTLY_ACTIVE", "MODERATELY_ACTIVE", "VERY_ACTIVE", "EXTRA_ACTIVE", name="activitylevel")
    goal_enum = sa.Enum("LOSE_WEIGHT", "TRY_AI_COACH", "GET_BULKS", "IMPROVE_ENDURANCE", name="fitnessgoal")
    meal_type_enum = sa.Enum("BREAKFAST", "LUNCH", "DINNER", "SNACK", name="mealtype")

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, unique=True, index=True, nullable=False),
        sa.Column("password", sa.String, nullable=False),
        sa.Column("is_verified", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- profiles ---
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("age", sa.Integer, nullable=False),
        sa.Column("gender", gender_enum, nullable=False),
        sa.Column("height", sa.Float, nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("fitness_goal", goal_enum, nullable=False),
        sa.Column("activity_level", activity_enum, nullable=False),
        sa.Column("dietary_preference", sa.String, nullable=False),
        sa.Column("medical_conditions", sa.String, nullable=False),
        sa.Column("allergies", sa.String, nullable=False),
        sa.Column("injuries", sa.String, nullable=False),
        sa.Column("medications", sa.String, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- central_exercises ---
    op.create_table(
        "central_exercises",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("exercise_type", sa.String(50), nullable=False, server_default="Strength"),
        sa.Column("primary_muscle_group", sa.String(100), nullable=False, server_default="Full Body"),
        sa.Column("secondary_muscles", sa.String(255), nullable=True),
        sa.Column("equipment_required", sa.String(100), nullable=False, server_default="Bodyweight"),
        sa.Column("difficulty_level", sa.String(50), nullable=False, server_default="Beginner"),
        sa.Column("location", sa.String(50), nullable=False, server_default="Any"),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("video_url", sa.String(500), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="System"),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("name_embedding", Vector(384), nullable=True),
    )

    # --- central_foods ---
    op.create_table(
        "central_foods",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("food_name", sa.String(255), nullable=False, index=True),
        sa.Column("food_name_ar", sa.String(255), nullable=True),
        sa.Column("food_category", sa.String(100), nullable=True, index=True),
        sa.Column("calories_per_100g", sa.Float, nullable=False),
        sa.Column("protein_per_100g", sa.Float, nullable=False),
        sa.Column("carbs_per_100g", sa.Float, nullable=False),
        sa.Column("fats_per_100g", sa.Float, nullable=False),
        sa.Column("fiber_per_100g", sa.Float, nullable=True),
        sa.Column("serving_size_g", sa.Float, nullable=True),
        sa.Column("serving_description", sa.String(100), nullable=True),
        sa.Column("dietary_tags", sa.JSON, nullable=True),
        sa.Column("usda_fdc_id", sa.Integer, nullable=True, index=True),
        sa.Column("name_embedding", Vector(384), nullable=True),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="USDA"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- workout_plans ---
    op.create_table(
        "workout_plans",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profiles.id"), nullable=False, index=True),
        sa.Column("plan_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("frequency", sa.String(100), nullable=True),
        sa.Column("difficulty_level", sa.String(50), nullable=True),
        sa.Column("estimated_duration_per_session", sa.Integer, nullable=True),
        sa.Column("generated_from_preferences", sa.JSON, nullable=True),
        sa.Column("language", sa.String(5), nullable=True, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- workout_days ---
    op.create_table(
        "workout_days",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("workout_plan_id", sa.Integer, sa.ForeignKey("workout_plans.id"), nullable=False, index=True),
        sa.Column("day_name", sa.String(100), nullable=False),
        sa.Column("day_number", sa.Integer, nullable=False),
        sa.Column("focus_area", sa.String(100), nullable=True),
        sa.Column("estimated_duration", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # --- workout_day_exercises ---
    op.create_table(
        "workout_day_exercises",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("workout_day_id", sa.Integer, sa.ForeignKey("workout_days.id"), nullable=False, index=True),
        sa.Column("central_exercise_id", sa.Integer, sa.ForeignKey("central_exercises.id"), nullable=False, index=True),
        sa.Column("sets", sa.Integer, nullable=True),
        sa.Column("reps", sa.Integer, nullable=True),
        sa.Column("weight_kg", sa.Float, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("rest_seconds", sa.Integer, nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # --- nutrition_plans ---
    op.create_table(
        "nutrition_plans",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profiles.id"), nullable=False, index=True),
        sa.Column("plan_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("daily_calories", sa.Integer, nullable=False),
        sa.Column("daily_protein_g", sa.Integer, nullable=False),
        sa.Column("daily_carbs_g", sa.Integer, nullable=False),
        sa.Column("daily_fats_g", sa.Integer, nullable=False),
        sa.Column("generated_from_preferences", sa.JSON, nullable=True),
        sa.Column("language", sa.String(5), nullable=True, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- nutrition_plan_days ---
    op.create_table(
        "nutrition_plan_days",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("nutrition_plan_id", sa.Integer, sa.ForeignKey("nutrition_plans.id"), nullable=False, index=True),
        sa.Column("day_number", sa.Integer, nullable=False),
        sa.Column("day_name", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # --- nutrition_plan_meals ---
    op.create_table(
        "nutrition_plan_meals",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("nutrition_plan_day_id", sa.Integer, sa.ForeignKey("nutrition_plan_days.id"), nullable=False, index=True),
        sa.Column("meal_type", sa.String(50), nullable=False),
        sa.Column("meal_name", sa.String(255), nullable=False),
        sa.Column("calories", sa.Integer, nullable=False),
        sa.Column("protein_g", sa.Float, nullable=False),
        sa.Column("carbs_g", sa.Float, nullable=False),
        sa.Column("fats_g", sa.Float, nullable=False),
        sa.Column("fiber_g", sa.Float, nullable=True),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("prep_time_minutes", sa.Integer, nullable=True),
        sa.Column("cook_time_minutes", sa.Integer, nullable=True),
        sa.Column("servings", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # --- nutrition_plan_meal_ingredients ---
    op.create_table(
        "nutrition_plan_meal_ingredients",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("nutrition_plan_meal_id", sa.Integer, sa.ForeignKey("nutrition_plan_meals.id"), nullable=False, index=True),
        sa.Column("central_food_id", sa.Integer, sa.ForeignKey("central_foods.id"), nullable=False, index=True),
        sa.Column("amount_g", sa.Float, nullable=False),
    )

    # --- workout_logs ---
    op.create_table(
        "workout_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("central_exercise_id", sa.Integer, sa.ForeignKey("central_exercises.id"), nullable=True, index=True),
        sa.Column("workout_day_exercise_id", sa.Integer, sa.ForeignKey("workout_day_exercises.id"), nullable=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("sets_completed", sa.Integer, nullable=False),
        sa.Column("reps_completed", sa.Integer, nullable=False),
        sa.Column("weight_used", sa.Float, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_workout_logs_user_date", "workout_logs", ["user_id", "log_date"])

    # --- meal_logs ---
    op.create_table(
        "meal_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("central_food_id", sa.Integer, sa.ForeignKey("central_foods.id"), nullable=True, index=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("meal_type", meal_type_enum, nullable=False),
        sa.Column("meal_name", sa.String(255), nullable=False),
        sa.Column("servings", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("serving_size_g_snapshot", sa.Float, nullable=True),
        sa.Column("serving_description_snapshot", sa.String(100), nullable=True),
        sa.Column("calories", sa.Float, nullable=False),
        sa.Column("protein_g", sa.Float, nullable=False),
        sa.Column("carbs_g", sa.Float, nullable=False),
        sa.Column("fats_g", sa.Float, nullable=False),
        sa.Column("log_method", sa.String(20), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_meal_logs_user_date", "meal_logs", ["user_id", "log_date"])
    op.create_index("idx_meal_logs_user_date_type", "meal_logs", ["user_id", "log_date", "meal_type"])

    # --- sleep_logs ---
    op.create_table(
        "sleep_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("sleep_hours", sa.Float, nullable=False),
        sa.Column("sleep_quality", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_sleep_logs_user_date", "sleep_logs", ["user_id", "log_date"])

    # --- hydration_logs ---
    op.create_table(
        "hydration_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("water_ml", sa.Float, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_hydration_logs_user_date", "hydration_logs", ["user_id", "log_date"])

    # --- weight_logs ---
    op.create_table(
        "weight_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_weight_logs_user_date", "weight_logs", ["user_id", "log_date"])

    # --- device_tokens ---
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token", sa.String, unique=True, nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- notification_preferences ---
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("meal_reminders_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("workout_reminders_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("hydration_reminders_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("sleep_reminders_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("hydration_interval_hours", sa.Integer, server_default="2", nullable=False),
        sa.Column("meal_reminder_minutes_before", sa.Integer, server_default="15", nullable=False),
        sa.Column("workout_reminder_hour", sa.Integer, server_default="7", nullable=False),
        sa.Column("sleep_reminder_hour", sa.Integer, server_default="21", nullable=False),
        sa.Column("coaching_reminders_enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("coaching_daily_hour", sa.Integer, server_default="20", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- coaching_messages ---
    op.create_table(
        "coaching_messages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", sa.String(30), nullable=False, index=True),
        sa.Column("urgency", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("is_dismissed", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("coaching_messages")
    op.drop_table("notification_preferences")
    op.drop_table("device_tokens")
    op.drop_table("weight_logs")
    op.drop_table("hydration_logs")
    op.drop_table("sleep_logs")
    op.drop_table("meal_logs")
    op.drop_table("workout_logs")
    op.drop_table("nutrition_plan_meal_ingredients")
    op.drop_table("nutrition_plan_meals")
    op.drop_table("nutrition_plan_days")
    op.drop_table("nutrition_plans")
    op.drop_table("workout_day_exercises")
    op.drop_table("workout_days")
    op.drop_table("workout_plans")
    op.drop_table("central_foods")
    op.drop_table("central_exercises")
    op.drop_table("profiles")
    op.drop_table("users")

    sa.Enum(name="gender").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="activitylevel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="fitnessgoal").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="mealtype").drop(op.get_bind(), checkfirst=True)
