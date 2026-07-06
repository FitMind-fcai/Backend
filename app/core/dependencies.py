"""
Shared FastAPI dependencies for the entire application.
Provides reusable dependency functions for authentication, database access, and shared services.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError

from app.db.database import get_db
from app.core.security import verify_access_token
from app.auth_module.models.user import User
from app.auth_module.repositories.user_repository import UserRepository
from app.shared.services.email_service import EmailService


# HTTP Bearer token scheme for extracting JWT from Authorization header
security = HTTPBearer()


# ========== User Authentication Dependencies ==========

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user from JWT token.

    Extracts JWT from Authorization header, validates it, and retrieves user from database.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session

    Returns:
        User: Current authenticated user object

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Extract token from credentials
        token = credentials.credentials

        # Verify and decode JWT token
        payload = verify_access_token(token)

        # Extract user info from payload
        user_id: int = payload.get("id")
        email: str = payload.get("email")

        if user_id is None or email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Fetch user from database using repository
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)

    if user is None or user.email != email:
        raise credentials_exception

    return user


def get_current_verified_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to get current authenticated AND verified user.

    Ensures the user has verified their email before accessing protected routes.

    Args:
        current_user: Current authenticated user from get_current_user dependency

    Returns:
        User: Current verified user object

    Raises:
        HTTPException 403: If user email is not verified

    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email to access this resource."
        )

    return current_user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User | None:
    """
    Optional dependency to get current user if token is provided.

    Similar to get_current_user but returns None if token is invalid/missing
    instead of raising an exception. Useful for routes that work for both
    authenticated and anonymous users.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session

    Returns:
        User | None: Current user if authenticated, None otherwise
    """
    try:
        token = credentials.credentials
        payload = verify_access_token(token)

        user_id: int = payload.get("id")
        email: str = payload.get("email")

        if user_id is None or email is None:
            return None

        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)

        if user and user.email == email:
            return user
        return None

    except (JWTError, Exception):
        return None


# ========== Shared Service Dependencies ==========

def get_email_service() -> EmailService:
    """
    Provide base EmailService instance.

    This is a shared service that provides generic email sending functionality.
    Modules can extend this for their specific email needs (see AuthEmailService).

    Returns:
        EmailService: Base email service instance

    Usage:
        @router.post("/send-notification")
        def send_notification(
            email_service: EmailService = Depends(get_email_service)
        ):
            email_service.send_email(
                recipient_email="user@example.com",
                subject="Notification",
                html_content="<h1>Hello</h1>"
            )
    """
    return EmailService()


__all__ = [
    # User authentication
    "get_current_user",
    "get_current_verified_user",
    "get_optional_current_user",
    "security",
    # Shared services
    "get_email_service",
]
