"""
Authentication module specific security utilities.
Handles OTP and email verification tokens.
Shared security functions (password hashing, JWT) are in app.core.security
"""
import random
from datetime import datetime, timedelta, timezone
from app.core.security import generate_secure_token, hash_string, verify_hash
from app.auth_module.core.config import (
    OTP_LENGTH, OTP_EXPIRATION_MINUTES, VERIFICATION_TOKEN_EXPIRATION_HOURS
)

# Re-export shared security functions for backward compatibility
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)

__all__ = [
    # Auth-specific functions
    "generate_otp",
    "hash_otp",
    "verify_otp",
    "get_otp_expiration",
    "generate_verification_token",
    "get_verification_token_expires",
    # Re-exported shared functions
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_access_token",
]


# ========== EMAIL VERIFICATION TOKEN ==========

def generate_verification_token() -> str:
    """
    Generate secure random token for email verification.
    
    Returns:
        str: URL-safe random token (32 bytes)
    """
    return generate_secure_token(32)


def get_verification_token_expires() -> datetime:
    """
    Get expiration time for verification token.
    
    Returns:
        datetime: Expiration timestamp (24 hours from now)
    """
    return datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_EXPIRATION_HOURS)


# ========== OTP (One Time Password) ==========

def generate_otp() -> str:
    """
    Generate OTP (One Time Password).
    
    Returns:
        str: Random numeric OTP (e.g., "1234")
    """
    return ''.join([str(random.randint(0, 9)) for _ in range(OTP_LENGTH)])


def hash_otp(otp: str) -> str:
    """
    Hash OTP for secure storage.
    Convenience wrapper around shared hash_string function.

    Args:
        otp: Plain text OTP
        
    Returns:
        str: Hashed OTP
    """
    return hash_string(otp)


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Verify OTP against hash.
    Convenience wrapper around shared verify_hash function.

    Args:
        plain_otp: Plain text OTP
        hashed_otp: Hashed OTP from database
        
    Returns:
        bool: True if OTP matches, False otherwise
    """
    return verify_hash(plain_otp, hashed_otp)

def get_otp_expiration() -> datetime:
    """
    Get expiration time for OTP.
    
    Returns:
        datetime: Expiration timestamp (10 minutes from now)
    """
    return datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRATION_MINUTES)
