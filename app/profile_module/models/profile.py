from sqlalchemy.sql.sqltypes import Float
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base
from app.profile_module.models.enums import Gender, ActivityLevel, FitnessGoal

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    age = Column(Integer, nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    height = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    fitness_goal = Column(Enum(FitnessGoal), nullable=False)
    activity_level = Column(Enum(ActivityLevel), nullable=False)
    dietary_preference = Column(String, nullable=False)
    medical_conditions = Column(String, nullable=False)
    allergies = Column(String, nullable=False)
    injuries = Column(String, nullable=False)
    medications = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())