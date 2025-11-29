"""
OTP (One Time Password) service using Redis with dependency injection.
Handles OTP generation, validation, expiration logic, and rate limiting.

Security Layers:
1. Max 5 verification attempts per OTP
2. 5-minute cooldown after max failed attempts
3. Max 3 requests per hour
4. Max 5 requests per day
"""
from typing import Optional
from redis import Redis
from fastapi import HTTPException, status
from app.auth_module.core.security import generate_otp, hash_otp, verify_otp
from app.auth_module.core.config import (
    OTP_EXPIRATION_MINUTES, 
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_MINUTES,
    OTP_MAX_REQUESTS_PER_HOUR,
    OTP_MAX_REQUESTS_PER_DAY,
    OTP_HOURLY_BLOCK_DURATION_HOURS,
    OTP_DAILY_BLOCK_DURATION_HOURS
)
from app.core.config import (
    REDIS_OTP_PREFIX, 
    REDIS_OTP_ATTEMPTS_PREFIX,
    REDIS_OTP_RESEND_COOLDOWN_PREFIX,
    REDIS_OTP_HOURLY_COUNT_PREFIX,
    REDIS_OTP_DAILY_COUNT_PREFIX,
    REDIS_OTP_BLOCKED_PREFIX
)


class OTPService:
    """
    Service for managing OTP (One Time Password) using Redis with rate limiting.
    
    Security Layers:
    1. Max verification attempts per OTP
    2. Cooldown after max failed attempts
    3. Hourly request limit
    4. Daily request limit
    """

    def __init__(self, redis_client: Optional[Redis]):
        """
        Initialize OTPService with Redis client.

        Args:
            redis_client: Redis client instance for OTP storage and rate limiting
        """
        self.redis_client = redis_client

    def create_password_reset_otp(self, email: str) -> str:
        """
        Generate and store OTP in Redis for password reset with rate limiting.

        Args:
            email: User's email address

        Returns:
            str: Plain text OTP (to be sent via email)

        Raises:
            HTTPException: If Redis unavailable or rate limits exceeded
        """
        if not self.redis_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OTP service temporarily unavailable"
            )

        # Check rate limiting layers
        self._check_if_blocked(email)
        self._check_resend_cooldown(email)
        self._check_hourly_limit(email)
        self._check_daily_limit(email)

        # Generate OTP
        otp = generate_otp()
        hashed_otp = hash_otp(otp)

        # Store OTP with expiration
        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"

        self.redis_client.setex(
            otp_key,
            OTP_EXPIRATION_MINUTES * 60,
            hashed_otp
        )

        # Reset verification attempts counter
        self.redis_client.setex(
            attempts_key,
            OTP_EXPIRATION_MINUTES * 60,
            0
        )

        # Increment request counters
        self._increment_request_counters(email)

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
            # Set cooldown before allowing resend
            self._set_resend_cooldown(email)
            
            # Clear OTP after max attempts
            self.clear_otp(email)
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Maximum OTP verification attempts ({OTP_MAX_ATTEMPTS}) exceeded. "
                               f"Please wait {OTP_RESEND_COOLDOWN_MINUTES} minutes before requesting a new OTP.",
                    "remaining_seconds": OTP_RESEND_COOLDOWN_MINUTES * 60,
                    "reason": "max_attempts"
                }
            )

        # Increment attempts
        self.redis_client.incr(attempts_key)

        # Verify OTP
        if not verify_otp(otp, stored_otp):
            remaining_attempts = OTP_MAX_ATTEMPTS - (attempts + 1)
            
            if remaining_attempts > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid OTP. {remaining_attempts} attempt(s) remaining."
                )
            else:
                # Last attempt failed - set cooldown
                self._set_resend_cooldown(email)
                self.clear_otp(email)
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": f"Invalid OTP. Maximum attempts exceeded. "
                                   f"Please wait {OTP_RESEND_COOLDOWN_MINUTES} minutes before requesting a new OTP.",
                        "remaining_seconds": OTP_RESEND_COOLDOWN_MINUTES * 60,
                        "reason": "max_attempts"
                    }
                )

        # OTP is valid - clear everything
        self.clear_otp(email)
        return True

    def clear_otp(self, email: str) -> None:
        """
        Clear OTP and verification attempts from Redis.
        Does NOT clear rate limiting counters.

        Args:
            email: User's email address
        """
        if not self.redis_client:
            return

        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"

        self.redis_client.delete(otp_key)
        self.redis_client.delete(attempts_key)

    def get_rate_limit_status(self, email: str) -> dict:
        """
        Get current rate limiting status for an email.
        
        Args:
            email: User's email address
            
        Returns:
            dict: {
                "can_request": bool,
                "reason": str | None,
                "remaining_seconds": int | None
            }
        """
        if not self.redis_client:
            return {"can_request": True, "reason": None, "remaining_seconds": None}
        
        # Check if blocked
        blocked_key = f"{REDIS_OTP_BLOCKED_PREFIX}{email}"
        if self.redis_client.exists(blocked_key):
            ttl = self.redis_client.ttl(blocked_key)
            block_reason = self.redis_client.get(blocked_key)
            return {
                "can_request": False,
                "reason": block_reason if isinstance(block_reason, str) else "blocked",
                "remaining_seconds": ttl if ttl > 0 else 0
            }
        
        # Check cooldown
        cooldown_key = f"{REDIS_OTP_RESEND_COOLDOWN_PREFIX}{email}"
        if self.redis_client.exists(cooldown_key):
            ttl = self.redis_client.ttl(cooldown_key)
            return {
                "can_request": False,
                "reason": "cooldown",
                "remaining_seconds": ttl if ttl > 0 else 0
            }
        
        return {"can_request": True, "reason": None, "remaining_seconds": None}

    # ========== Private Helper Methods ==========

    def _check_if_blocked(self, email: str) -> None:
        """Check if user is currently blocked from requesting OTP."""
        blocked_key = f"{REDIS_OTP_BLOCKED_PREFIX}{email}"
        
        if self.redis_client.exists(blocked_key):
            ttl = self.redis_client.ttl(blocked_key)
            hours = ttl // 3600
            minutes = (ttl % 3600) // 60
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Too many OTP requests. Please try again in {hours}h {minutes}m.",
                    "remaining_seconds": ttl,
                    "reason": "blocked"
                }
            )

    def _check_resend_cooldown(self, email: str) -> None:
        """Check if user is in cooldown period after failed attempts."""
        cooldown_key = f"{REDIS_OTP_RESEND_COOLDOWN_PREFIX}{email}"
        
        if self.redis_client.exists(cooldown_key):
            ttl = self.redis_client.ttl(cooldown_key)
            minutes = ttl // 60
            seconds = ttl % 60
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Please wait {minutes}m {seconds}s before requesting a new OTP.",
                    "remaining_seconds": ttl,
                    "reason": "cooldown"
                }
            )

    def _check_hourly_limit(self, email: str) -> None:
        """Check hourly request limit."""
        hourly_key = f"{REDIS_OTP_HOURLY_COUNT_PREFIX}{email}"
        count = self.redis_client.get(hourly_key)
        count = int(count) if count else 0

        if count >= OTP_MAX_REQUESTS_PER_HOUR:
            # Block for 1 hour
            blocked_key = f"{REDIS_OTP_BLOCKED_PREFIX}{email}"
            self.redis_client.setex(
                blocked_key,
                OTP_HOURLY_BLOCK_DURATION_HOURS * 3600,
                "hourly_limit"
            )
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Too many OTP requests. Maximum {OTP_MAX_REQUESTS_PER_HOUR} per hour. "
                               f"Please try again in {OTP_HOURLY_BLOCK_DURATION_HOURS} hour(s).",
                    "remaining_seconds": OTP_HOURLY_BLOCK_DURATION_HOURS * 3600,
                    "reason": "hourly_limit"
                }
            )

    def _check_daily_limit(self, email: str) -> None:
        """Check daily request limit."""
        daily_key = f"{REDIS_OTP_DAILY_COUNT_PREFIX}{email}"
        count = self.redis_client.get(daily_key)
        count = int(count) if count else 0

        if count >= OTP_MAX_REQUESTS_PER_DAY:
            # Block for 24 hours
            blocked_key = f"{REDIS_OTP_BLOCKED_PREFIX}{email}"
            self.redis_client.setex(
                blocked_key,
                OTP_DAILY_BLOCK_DURATION_HOURS * 3600,
                "daily_limit"
            )
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Too many OTP requests. Maximum {OTP_MAX_REQUESTS_PER_DAY} per day. "
                               f"Please try again in {OTP_DAILY_BLOCK_DURATION_HOURS} hours.",
                    "remaining_seconds": OTP_DAILY_BLOCK_DURATION_HOURS * 3600,
                    "reason": "daily_limit"
                }
            )

    def _set_resend_cooldown(self, email: str) -> None:
        """Set cooldown period after max failed verification attempts."""
        cooldown_key = f"{REDIS_OTP_RESEND_COOLDOWN_PREFIX}{email}"
        self.redis_client.setex(
            cooldown_key,
            OTP_RESEND_COOLDOWN_MINUTES * 60,
            "max_attempts_reached"
        )

    def _increment_request_counters(self, email: str) -> None:
        """Increment hourly and daily request counters."""
        hourly_key = f"{REDIS_OTP_HOURLY_COUNT_PREFIX}{email}"
        daily_key = f"{REDIS_OTP_DAILY_COUNT_PREFIX}{email}"

        # Increment or create hourly counter (expires in 1 hour)
        if self.redis_client.exists(hourly_key):
            self.redis_client.incr(hourly_key)
        else:
            self.redis_client.setex(hourly_key, 3600, 1)

        # Increment or create daily counter (expires in 24 hours)
        if self.redis_client.exists(daily_key):
            self.redis_client.incr(daily_key)
        else:
            self.redis_client.setex(daily_key, 86400, 1)

