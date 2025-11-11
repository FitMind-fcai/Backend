"""
Verification token service using Redis with dependency injection.
Handles email verification token storage and validation.
"""
from typing import Optional
from redis import Redis
from fastapi import HTTPException, status
from app.auth_module.core.security import generate_verification_token
from app.auth_module.core.config import VERIFICATION_TOKEN_EXPIRATION_HOURS
from app.core.config import REDIS_VERIFICATION_PREFIX


class VerificationService:
    """
    Service for managing email verification tokens using Redis.
    """

    def __init__(self, redis_client: Optional[Redis]):
        """
        Initialize VerificationService with Redis client.

        Args:
            redis_client: Redis client instance for token storage
        """
        self.redis_client = redis_client

    def create_verification_token(self, email: str) -> str:
        """
        Generate and store verification token in Redis.

        Args:
            email: User's email address

        Returns:
            str: Verification token (to be sent in email link)

        Raises:
            HTTPException: If Redis is not available
        """
        if not self.redis_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification service temporarily unavailable"
            )

        # Generate token
        token = generate_verification_token()

        # Store token -> email mapping in Redis with expiration
        token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"

        # Store email address as value (expires in 24 hours)
        self.redis_client.setex(
            token_key,
            VERIFICATION_TOKEN_EXPIRATION_HOURS * 3600,
            email
        )

        return token

    def get_email_from_token(self, token: str) -> Optional[str]:
        """
        Get email address associated with verification token.

        Args:
            token: Verification token

        Returns:
            str or None: Email address if token is valid, None otherwise
        """
        if not self.redis_client:
            return None

        token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
        email = self.redis_client.get(token_key)

        return email if email else None

    def validate_verification_token(self, token: str) -> str:
        """
        Validate verification token and return associated email.

        Args:
            token: Verification token

        Returns:
            str: Email address

        Raises:
            HTTPException: If token is invalid or expired
        """
        email = self.get_email_from_token(token)

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )

        return email

    def delete_verification_token(self, token: str) -> None:
        """
        Delete verification token from Redis.

        Should be called after successful email verification.

        Args:
            token: Verification token
        """
        if not self.redis_client:
            return

        token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
        self.redis_client.delete(token_key)

