from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.core.config import DATABASE_URL
from app.db.database import Base

# Import every model so Base.metadata is complete
from app.auth_module.models.user import User  # noqa: F401
from app.profile_module.models.profile import Profile  # noqa: F401
from app.planning_module.models.plan import (  # noqa: F401
    CentralExercise, CentralFood,
    WorkoutPlan, WorkoutDay, WorkoutDayExercise,
    NutritionPlan, NutritionPlanDay, NutritionPlanMeal, NutritionPlanMealIngredient,
)
from app.tracking_module.models.workout_log import WorkoutLog  # noqa: F401
from app.tracking_module.models.meal_log import MealLog  # noqa: F401
from app.tracking_module.models.sleep_log import SleepLog  # noqa: F401
from app.tracking_module.models.hydration_log import HydrationLog  # noqa: F401
from app.tracking_module.models.weight_log import WeightLog  # noqa: F401
from app.notification_module.models.device_token import DeviceToken  # noqa: F401
from app.notification_module.models.notification_preference import NotificationPreference  # noqa: F401
from app.recommendation_system.models.coaching_message import CoachingMessage  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
