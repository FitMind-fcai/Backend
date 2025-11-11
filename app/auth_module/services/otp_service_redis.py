"""
OTP (One Time Password) service using Redis with dependency injection.
Handles OTP generation, validation, and expiration logic.
"""
from typing import Optional
from redis import Redis
from fastapi import HTTPException, status
from app.auth_module.core.security import generate_otp, hash_otp, verify_otp
from app.auth_module.core.config import OTP_EXPIRATION_MINUTES, OTP_MAX_ATTEMPTS
from app.core.config import REDIS_OTP_PREFIX, REDIS_OTP_ATTEMPTS_PREFIX


class OTPService:
    """
    Service for managing OTP (One Time Password) using Redis.
    """

    def __init__(self, redis_client: Optional[Redis]):
        """
        Initialize OTPService with Redis client.

        Args:
            redis_client: Redis client instance for OTP storage
        """
        self.redis_client = redis_client

    def create_password_reset_otp(self, email: str) -> str:
        """
        Generate and store OTP in Redis for password reset.

        Args:
            email: User's email address

        Returns:
            str: Plain text OTP (to be sent via email)

        Raises:
            HTTPException: If Redis is not available
        """
        if not self.redis_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OTP service temporarily unavailable"
            )

        # Generate OTP
        otp = generate_otp()

        # Hash OTP before storing
        hashed_otp = hash_otp(otp)

        # Store in Redis with expiration
        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"

        # Store hashed OTP (expires in 10 minutes)
        self.redis_client.setex(
            otp_key,
            OTP_EXPIRATION_MINUTES * 60,
            hashed_otp
        )

        # Reset attempts counter
        self.redis_client.setex(
            attempts_key,
            OTP_EXPIRATION_MINUTES * 60,
            0
        )

        return otp

    def validate_otp(self, email: str, otp: str) -> bool:
        """
        Validate OTP from Redis for password reset.

        Args:
            email: User's email address
            otp: Plain text OTP to verify

        Returns:
            bool: True if OTP is valid

        Raises:
            HTTPException: If OTP is invalid, expired, or max attempts exceeded
        """
        if not self.redis_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OTP service temporarily unavailable"
            )

        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"

        # Check if OTP exists
        stored_otp = self.redis_client.get(otp_key)

        if not stored_otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No OTP found or OTP has expired. Please request a new one."
            )

        # Check attempts
        attempts = self.redis_client.get(attempts_key)
        attempts = int(attempts) if attempts else 0

        if attempts >= OTP_MAX_ATTEMPTS:
            # Clear OTP after max attempts
            self.clear_otp(email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum OTP verification attempts ({OTP_MAX_ATTEMPTS}) exceeded. Please request a new OTP."
            )

        # Increment attempts
        self.redis_client.incr(attempts_key)

        # Verify OTP
        if not verify_otp(otp, stored_otp):
            remaining_attempts = OTP_MAX_ATTEMPTS - (attempts + 1)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OTP. {remaining_attempts} attempts remaining."
            )

        return True

    def clear_otp(self, email: str) -> None:
        """
        Clear OTP and attempts from Redis.

        Should be called after successful OTP verification or password reset.

        Args:
            email: User's email address
        """
        if not self.redis_client:
            return

        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"

        self.redis_client.delete(otp_key)
        self.redis_client.delete(attempts_key)

