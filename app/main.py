from fastapi import FastAPI, HTTPException, Depends, status
from routes.auth import authRouter
from app.database import create_tables

app = FastAPI()

# Create database tables on startup
@app.on_event("startup")
def startup_event():
    create_tables()
    print("✅ Database tables created successfully!")

app.include_router(authRouter, tags=["Authentication"])
