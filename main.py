from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from app.auth_module.routes import authRouter
from app.db.database import create_tables
from app.profile_module.routes import profileRouter
from app.planning_module.routes import (
    workout_router,
    nutrition_router,
    plan_generation_router
)

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="FitMind API",
    description="""FitMind Backend API with Authentication, Profile Management, and AI-Powered Fitness Planning.
    
    ## Authentication
    Most endpoints require a JWT Bearer token. To authenticate:
    1. Use `/auth/login` to get your token
    2. Click the **🔓 Authorize** button (top right)
    3. Enter: `Bearer YOUR_TOKEN` or just `YOUR_TOKEN`
    4. All protected endpoints will now include your token automatically
    """,
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True  # Keeps auth token after page refresh
    }
)

# Custom OpenAPI schema to properly document Bearer token
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security scheme for Bearer token
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token in the format: `Bearer <token>` or just `<token>`"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Create database tables on startup
@app.on_event("startup")
def startup_event():
    create_tables()
    print("✅ Database tables created successfully!")

app.include_router(authRouter,tags=["Authentication"])
app.include_router(profileRouter, tags=["Profiles"])
app.include_router(plan_generation_router, tags=["Plan Generation"])
app.include_router(workout_router, tags=["Workout Plans"])
app.include_router(nutrition_router, tags=["Nutrition Plans"])



