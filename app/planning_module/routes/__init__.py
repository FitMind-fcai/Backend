from app.planning_module.routes.workout_routes import workout_plan_router as workout_router
from app.planning_module.routes.nutrition_routes import nutrition_plan_router as nutrition_router
from app.planning_module.routes.plan_generation_routes import plan_generation_router

__all__ = [
    "workout_router",
    "nutrition_router",
    "plan_generation_router"
]
