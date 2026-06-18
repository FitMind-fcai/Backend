import os
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import logging
from app.auth_module.routes import authRouter
from app.db.database import create_tables, engine
from app.core.config import SQLALCHEMY_LOG_LEVEL, CORS_ALLOWED_ORIGINS
from app.profile_module.routes import profileRouter
from app.planning_module.routes import (
    workout_router,
    nutrition_router,
    plan_generation_router
)
from app.tracking_module.routes import tracking_router
from app.recommendation_system.routes.recommendations import recommendation_router

# Load environment variables from .env file
load_dotenv()

# Configure logging (console only for Docker/terminal debugging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Console output visible in docker-compose logs
    ]
)

# Set specific log levels for AI services
logging.getLogger('app.ai_services.ai_coach.vector_db_service').setLevel(logging.INFO)
logging.getLogger('app.ai_services.ai_coach.ai_coach_service').setLevel(logging.INFO)

# Keep SQL logs quiet by default; can be overridden via SQLALCHEMY_LOG_LEVEL.
_sql_log_level = getattr(logging, SQLALCHEMY_LOG_LEVEL, logging.WARNING)
logging.getLogger('sqlalchemy.engine').setLevel(_sql_log_level)
logging.getLogger('sqlalchemy.pool').setLevel(_sql_log_level)

app = FastAPI(
    title="FitMind API",
    description="""FitMind Backend API with Authentication, Profile Management, and AI-Powered Fitness Planning.

    ## Authentication
    Most endpoints require a JWT Bearer token. To authenticate:
    1. Use `/v1/auth/login` to get your token
    2. Click the **🔓 Authorize** button (top right)
    3. Enter: `Bearer YOUR_TOKEN` or just `YOUR_TOKEN`
    4. All protected endpoints will now include your token automatically
    """,
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True  # Keeps auth token after page refresh
    }
)

_raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
def startup_event():
    # Enable pgvector extension and ensure the name_embedding column exists.
    # This is idempotent — safe to run on every start.
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text(
                "ALTER TABLE central_foods "
                "ADD COLUMN IF NOT EXISTS name_embedding vector(384)"
            ))
            conn.execute(text(
                "ALTER TABLE central_exercises "
                "ADD COLUMN IF NOT EXISTS name_embedding vector(384)"
            ))
            conn.commit()
        print("✅ pgvector extension and name_embedding columns ready.")
    except Exception as exc:
        print(f"⚠️  pgvector setup skipped (non-fatal): {exc}")

    create_tables()
    print("✅ Database tables created successfully!")

# ── API v1 Router ────────────────────────────────────────────────────────────
v1_router = APIRouter(prefix="/v1")

v1_router.include_router(authRouter, tags=["Authentication"])
v1_router.include_router(profileRouter, tags=["Profiles"])
v1_router.include_router(plan_generation_router, tags=["Plan Generation"])
v1_router.include_router(workout_router, tags=["Workout Plans"])
v1_router.include_router(nutrition_router, tags=["Nutrition Plans"])
v1_router.include_router(tracking_router)  # tags are set per-endpoint
v1_router.include_router(recommendation_router)

app.include_router(v1_router)

