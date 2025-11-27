"""
Dependency injection providers for profile module.
Provides factory functions for services and repositories.
"""
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.profile_module.repositories.profile_repository import ProfileRepository
from app.profile_module.services.profile_service import ProfileService

# ========== Repository Providers ==========

def get_profile_repository(db: Session = Depends(get_db)) -> ProfileRepository:
    """
    Provide ProfileRepository instance.

    Args:
        db: Database session (injected)

    Returns:
        ProfileRepository: Profile repository instance
    """
    return ProfileRepository(db)


# ========== Service Providers ==========

def get_profile_service(
    profile_repo: ProfileRepository = Depends(get_profile_repository)
) -> ProfileService:
    """
    Provide ProfileService instance with dependencies injected.

    Args:
        profile_repo: Profile repository (injected)

    Returns:
        ProfileService: Profile service instance
    """
    return ProfileService(profile_repo)
