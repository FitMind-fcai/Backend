from fastapi import FastAPI
from app.auth_module.routes import authRouter
from app.db.database import create_tables

app = FastAPI(
    title="FitMind API",
    description="FitMind Backend API with Authentication",
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True  # Keeps auth token after page refresh
    }
)

# Create database tables on startup
@app.on_event("startup")
def startup_event():
    create_tables()
    print("✅ Database tables created successfully!")

app.include_router(authRouter, tags=["Authentication"])


