"""
OTP (One Time Password) service using Redis.
Handles OTP generation, validation, and expiration logic.
"""
from typing import Optional
from fastapi import HTTPException, status
import redis
from auth_module.core.security import generate_otp, hash_otp, verify_otp
from auth_module.core.config import (
    OTP_EXPIRATION_MINUTES, OTP_MAX_ATTEMPTS,
    REDIS_OTP_PREFIX, REDIS_OTP_ATTEMPTS_PREFIX
)
from auth_module.core.redis_client import get_redis


def create_password_reset_otp(email: str) -> str:
    """
    Generate and store OTP in Redis for password reset.
    
    Args:
        email: User's email address
        
    Returns:
        str: Plain text OTP (to be sent via email)
        
    Raises:
        HTTPException: If Redis is not available
    """
    redis_client = get_redis()
    
    if not redis_client:
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
    redis_client.setex(
        otp_key,
        OTP_EXPIRATION_MINUTES * 60, 
        hashed_otp
    )
    
    # Reset attempts counter
    redis_client.setex(
        attempts_key,
        OTP_EXPIRATION_MINUTES * 60,
        0
    )
    
    return otp


def validate_otp(email: str, otp: str) -> bool:
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
    redis_client = get_redis()
    
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OTP service temporarily unavailable"
        )
    
    otp_key = f"{REDIS_OTP_PREFIX}{email}"
    attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"
    
    # Check if OTP exists
    stored_otp = redis_client.get(otp_key)
    
    if not stored_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found or OTP has expired. Please request a new one."
        )
    
    # Check attempts
    attempts = redis_client.get(attempts_key)
    attempts = int(attempts) if attempts else 0
    
    if attempts >= OTP_MAX_ATTEMPTS:
        # Clear OTP after max attempts
        clear_otp(email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please request a new OTP."
        )
    
    # Verify OTP
    if not verify_otp(otp, stored_otp):
        # Increment failed attempts
        redis_client.incr(attempts_key)
        
        remaining = OTP_MAX_ATTEMPTS - attempts - 1
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OTP. {remaining} attempts remaining."
        )
    
    return True


def clear_otp(email: str) -> None:
    """
    Clear OTP data from Redis.
    
    Should be called after successful password reset or on max attempts.
    
    Args:
        email: User's email address
    """
    redis_client = get_redis()
    
    if redis_client:
        otp_key = f"{REDIS_OTP_PREFIX}{email}"
        attempts_key = f"{REDIS_OTP_ATTEMPTS_PREFIX}{email}"
        
        redis_client.delete(otp_key)
        redis_client.delete(attempts_key)


def is_otp_valid(email: str) -> bool:
    """
    Check if user has a valid (not expired) OTP in Redis.
    
    Args:
        email: User's email address
        
    Returns:
        bool: True if OTP exists and is not expired
    """
    redis_client = get_redis()
    
    if not redis_client:
        return False
    
    otp_key = f"{REDIS_OTP_PREFIX}{email}"
    return redis_client.exists(otp_key) > 0


def get_otp_ttl(email: str) -> int:
    """
    Get remaining time (in seconds) for OTP.
    
    Args:
        email: User's email address
        
    Returns:
        int: Remaining seconds, -1 if expired, -2 if doesn't exist
    """
    redis_client = get_redis()
    
    if not redis_client:
        return -2
    
    otp_key = f"{REDIS_OTP_PREFIX}{email}"
    return redis_client.ttl(otp_key)
