"""
Profile repository for data access operations.
Handles all database operations related to Profile model.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.shared.repositories.base_repository import BaseRepository
from app.profile_module.models.profile import Profile
from app.profile_module.models.enums import Gender, ActivityLevel, FitnessGoal

class ProfileRepository(BaseRepository[Profile]):
    """
    Repository for Profile model with specific query methods.
    """

    def __init__(self, db: Session):
        """
        Initialize ProfileRepository.

        Args:
            db: Database session
        """
        super().__init__(Profile, db)

    def get_by_user_id(self, user_id: int) -> Optional[Profile]:
        """
        Get profile by user ID.

        Args:
            user_id: User ID

        Returns:
            Profile instance or None if not found
        """
        return self.get_by_filter(user_id=user_id)

    def create_profile(
        self,
        user_id: int,
        age: int,
        gender: Gender,
        height: int,
        weight: int,
        fitness_goal: FitnessGoal,
        activity_level: ActivityLevel,
        dietary_preference: str,
        medical_conditions: str,
        allergies: str,
        injuries: str,
        medications: str
    ) -> Profile:
        """
        Create a new profile with the given details.

        Args:
            user_id: ID of the user
            age: Age of the user
            gender: Gender of the user
            height: Height in cm
            weight: Weight in kg
            fitness_goal: Fitness goal
            activity_level: Activity level
            dietary_preference: Dietary preference
            medical_conditions: Medical conditions
            allergies: Allergies
            injuries: Injuries
            medications: Medications

        Returns:
            Created Profile instance
        """
        profile_data = {
            "user_id": user_id,
            "age": age,
            "gender": gender,
            "height": height,
            "weight": weight,
            "fitness_goal": fitness_goal,
            "activity_level": activity_level,
            "dietary_preference": dietary_preference,
            "medical_conditions": medical_conditions,
            "allergies": allergies,
            "injuries": injuries,
            "medications": medications
        }
        return self.create(profile_data)
