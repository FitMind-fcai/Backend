from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.profile_module.models.enums import Gender, ActivityLevel, FitnessGoal

class ProfileBase(BaseModel):
    user_id: int
    age: int
    gender: Gender = Field(..., description="Gender of the user", examples=["Male", "Female"])
    height: float
    weight: float
    fitness_goal: FitnessGoal = Field(..., description="User's fitness goal", examples=["Lose Weight", "Build Muscle"])
    activity_level: ActivityLevel = Field(..., description="User's activity level", examples=["Sedentary", "Moderately Active"])
    dietary_preference: str
    medical_conditions: str
    allergies: str
    injuries: str
    medications: str

class ProfileUpdate(BaseModel):
    user_id: int
    age: Optional[int] = None
    gender: Optional[Gender] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    fitness_goal: Optional[FitnessGoal] = None
    activity_level: Optional[ActivityLevel] = None
    dietary_preference: Optional[str] = None
    medical_conditions: Optional[str] = None
    allergies: Optional[str] = None
    injuries: Optional[str] = None
    medications: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True