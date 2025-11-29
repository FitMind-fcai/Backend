from app.planning_module.routes.workout_routes import router as workout_router
from app.planning_module.routes.nutrition_routes import router as nutrition_router

__all__ = [
    "workout_router",
    "nutrition_router"
]
