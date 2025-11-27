"""
Profile service with proper dependency injection.
Contains business logic for profile management.
"""
from fastapi import HTTPException, status
from app.profile_module.models.profile import Profile
from app.profile_module.schemas.profile import ProfileBase, ProfileUpdate
from app.profile_module.repositories.profile_repository import ProfileRepository

class ProfileService:
    """
    Profile service handling profile creation, retrieval, and updates.
    Uses dependency injection for repositories.
    """

    def __init__(self, profile_repository: ProfileRepository):
        """
        Initialize ProfileService with injected dependencies.

        Args:
            profile_repository: Repository for profile data access
        """
        self.profile_repo = profile_repository

    def create_profile(self, user_id: int, profile_data: ProfileBase) -> Profile:
        """
        Create a new profile for a user.

        Args:
            user_id: ID of the user
            profile_data: Profile creation data

        Returns:
            Profile: Created profile object

        Raises:
            HTTPException 400: If profile already exists for the user
        """
        # Check if profile exists
        if self.profile_repo.get_by_user_id(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile already exists for this user"
            )

        # Create profile
        return self.profile_repo.create_profile(
            user_id=user_id,
            age=profile_data.age,
            gender=profile_data.gender,
            height=profile_data.height,
            weight=profile_data.weight,
            fitness_goal=profile_data.fitness_goal,
            activity_level=profile_data.activity_level,
            dietary_preference=profile_data.dietary_preference,
            medical_conditions=profile_data.medical_conditions,
            allergies=profile_data.allergies,
            injuries=profile_data.injuries,
            medications=profile_data.medications
        )

    def get_profile_by_user_id(self, user_id: int) -> Profile:
        """
        Get profile by user ID.

        Args:
            user_id: ID of the user

        Returns:
            Profile: Profile object

        Raises:
            HTTPException 404: If profile not found
        """
        profile = self.profile_repo.get_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        return profile

    def update_profile(self, user_id: int, profile_data: ProfileUpdate) -> Profile:
        """
        Update existing profile.

        Args:
            user_id: ID of the user
            profile_data: Profile update data

        Returns:
            Profile: Updated profile object

        Raises:
            HTTPException 404: If profile not found
        """
        profile = self.get_profile_by_user_id(user_id)
        
        update_data = profile_data.model_dump(exclude_unset=True)
        return self.profile_repo.update(profile.id, update_data)
