"""
Security utilities for authentication.
Handles password hashing, JWT tokens, and token generation.
"""
import secrets
import random
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from auth_module.core.config import (
    JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_HOURS,
    OTP_LENGTH, OTP_EXPIRATION_MINUTES, VERIFICATION_TOKEN_EXPIRATION_HOURS
)


# ========== PASSWORD HASHING ==========

def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Hashed password
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


# ========== JWT TOKEN ==========

def create_access_token(user_id: int, email: str) -> str:
    """
    Create JWT access token.
    
    Args:
        user_id: User's database ID
        email: User's email address
        
    Returns:
        str: Encoded JWT token
    """
    payload = {
        'id': user_id,
        'email': email,
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def verify_access_token(token: str) -> dict:
    """
    Verify JWT token and return payload.
    
    Args:
        token: JWT token string
        
    Returns:
        dict: Token payload containing user_id and email
        
    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise JWTError("Invalid or expired token")


# ========== EMAIL VERIFICATION TOKEN ==========

def generate_verification_token() -> str:
    """
    Generate secure random token for email verification.
    
    Returns:
        str: URL-safe random token (32 bytes)
    """
    return secrets.token_urlsafe(32)


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
    
    Args:
        otp: Plain text OTP
        
    Returns:
        str: Hashed OTP
    """
    otp_bytes = otp.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(otp_bytes, salt)
    return hashed.decode('utf-8')


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Verify OTP against hash.
    
    Args:
        plain_otp: Plain text OTP
        hashed_otp: Hashed OTP from database
        
    Returns:
        bool: True if OTP matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plain_otp.encode('utf-8'), 
            hashed_otp.encode('utf-8')
        )
    except Exception:
        return False


def get_otp_expiration() -> datetime:
    """
    Get expiration time for OTP.
    
    Returns:
        datetime: Expiration timestamp (10 minutes from now)
    """
    return datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRATION_MINUTES)
