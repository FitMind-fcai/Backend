from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    height = Column(Integer, nullable=False)
    weight = Column(Integer, nullable=False)
    fitness_goal = Column(String, nullable=False)
    activity_level = Column(String, nullable=False)
    dietary_preference = Column(String, nullable=False)
    medical_conditions = Column(String, nullable=False)
    allergies = Column(String, nullable=False)
    injuries = Column(String, nullable=False)
    medications = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())