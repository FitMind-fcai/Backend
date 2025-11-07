"""
Verification token service using Redis.
Handles email verification token storage and validation.
"""
from typing import Optional
from fastapi import HTTPException, status
from auth_module.core.security import generate_verification_token
from auth_module.core.config import (
    VERIFICATION_TOKEN_EXPIRATION_HOURS,
    REDIS_VERIFICATION_PREFIX
)
from auth_module.core.redis_client import get_redis


def create_verification_token(email: str) -> str:
    """
    Generate and store verification token in Redis.
    
    Args:
        email: User's email address
        
    Returns:
        str: Verification token (to be sent in email link)
        
    Raises:
        HTTPException: If Redis is not available
    """
    redis_client = get_redis()
    
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service temporarily unavailable"
        )
    
    # Generate token
    token = generate_verification_token()
    
    # Store token -> email mapping in Redis with expiration
    token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
    
    # Store email address as value (expires in 24 hours)
    redis_client.setex(
        token_key,
        VERIFICATION_TOKEN_EXPIRATION_HOURS * 3600,  
        email
    )
    
    return token


def get_email_from_token(token: str) -> Optional[str]:
    """
    Get email address associated with verification token.
    
    Args:
        token: Verification token
        
    Returns:
        str or None: Email address if token is valid, None otherwise
    """
    redis_client = get_redis()
    
    if not redis_client:
        return None
    
    token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
    email = redis_client.get(token_key)
    
    return email if email else None


def validate_verification_token(token: str) -> str:
    """
    Validate verification token and return associated email.
    
    Args:
        token: Verification token
        
    Returns:
        str: Email address
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    email = get_email_from_token(token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    return email


def delete_verification_token(token: str) -> None:
    """
    Delete verification token from Redis.
    
    Should be called after successful email verification.
    
    Args:
        token: Verification token
    """
    redis_client = get_redis()
    
    if redis_client:
        token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
        redis_client.delete(token_key)


def is_token_valid(token: str) -> bool:
    """
    Check if verification token exists and is not expired.
    
    Args:
        token: Verification token
        
    Returns:
        bool: True if token exists and is valid
    """
    redis_client = get_redis()
    
    if not redis_client:
        return False
    
    token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
    return redis_client.exists(token_key) > 0


def get_token_ttl(token: str) -> int:
    """
    Get remaining time (in seconds) for verification token.
    
    Args:
        token: Verification token
        
    Returns:
        int: Remaining seconds, -1 if expired, -2 if doesn't exist
    """
    redis_client = get_redis()
    
    if not redis_client:
        return -2
    
    token_key = f"{REDIS_VERIFICATION_PREFIX}{token}"
    return redis_client.ttl(token_key)


def get_all_pending_verifications(pattern: str = "*") -> dict:
    """
    Get all pending verification tokens (for admin/debugging).
    
    Args:
        pattern: Pattern to match tokens
        
    Returns:
        dict: Mapping of tokens to emails
    """
    redis_client = get_redis()
    
    if not redis_client:
        return {}
    
    full_pattern = f"{REDIS_VERIFICATION_PREFIX}{pattern}"
    tokens = redis_client.keys(full_pattern)
    
    result = {}
    for token_key in tokens:
        email = redis_client.get(token_key)
        token = token_key.replace(REDIS_VERIFICATION_PREFIX, "")
        result[token] = email
    
    return result
