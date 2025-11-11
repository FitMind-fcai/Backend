"""
Dependency injection providers for auth module.
Provides factory functions for services and repositories.
Similar to @Provides in Dagger/Hilt for Android.
"""
from fastapi import Depends
from sqlalchemy.orm import Session
from typing import Optional
from redis import Redis

from app.db.database import get_db
from app.core.redis_client import get_redis
from app.auth_module.repositories.user_repository import UserRepository
from app.auth_module.services.verification_service import VerificationService
from app.auth_module.services.otp_service_redis import OTPService
from app.auth_module.services.auth_service import AuthService
from app.shared.services.email_service import EmailService
from app.auth_module.services.email_service import AuthEmailService


# ========== Repository Providers ==========

def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """
    Provide UserRepository instance.

    Args:
        db: Database session (injected)

    Returns:
        UserRepository: User repository instance

    Usage:
        @router.get("/users")
        def get_users(user_repo: UserRepository = Depends(get_user_repository)):
            return user_repo.get_all()
    """
    return UserRepository(db)


# ========== Service Providers ==========

def get_verification_service(redis_client: Optional[Redis] = Depends(get_redis)) -> VerificationService:
    """
    Provide VerificationService instance.

    Args:
        redis_client: Redis client (injected)

    Returns:
        VerificationService: Verification service instance
    """
    return VerificationService(redis_client)


def get_auth_email_service() -> AuthEmailService:
    """
    Provide AuthEmailService instance with injected base EmailService.

    Returns:
        AuthEmailService: Auth-specific email service instance
    """
    base_email_service = EmailService()
    return AuthEmailService(base_email_service)


def get_otp_service(redis_client: Optional[Redis] = Depends(get_redis)) -> OTPService:
    """
    Provide OTPService instance.

    Args:
        redis_client: Redis client (injected)

    Returns:
        OTPService: OTP service instance
    """
    return OTPService(redis_client)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    verification_service: VerificationService = Depends(get_verification_service),
    auth_email_service: AuthEmailService = Depends(get_auth_email_service)
) -> AuthService:
    """
    Provide AuthService instance with all dependencies injected.

    This is like @Provides in Dagger/Hilt - it automatically injects
    all required dependencies.

    Args:
        user_repo: User repository (injected)
        verification_service: Verification service (injected)
        auth_email_service: Auth email service (injected)

    Returns:
        AuthService: Auth service instance with all dependencies

    Usage:
        @router.post("/register")
        def register(
            user_data: UserCreate,
            auth_service: AuthService = Depends(get_auth_service)
        ):
            return auth_service.create_user(user_data)
    """
    return AuthService(user_repo, verification_service, auth_email_service)


# Re-export from core dependencies for convenience
from app.core.dependencies import (
    get_current_user,
    get_current_verified_user,
    get_optional_current_user,
    security
)

__all__ = [
    # Repository providers
    "get_user_repository",
    # Service providers
    "get_verification_service",
    "get_auth_email_service",
    "get_otp_service",
    "get_auth_service",
    # User authentication dependencies
    "get_current_user",
    "get_current_verified_user",
    "get_optional_current_user",
    "security",
]

