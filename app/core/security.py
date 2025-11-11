"""
Shared security utilities for the entire application.
Handles password hashing, JWT tokens, and secure token generation.
"""
import secrets
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from app.core.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_HOURS


# ========== BCRYPT HASHING (Generic) ==========

def hash_string(text: str) -> str:
    """
    Hash any string using bcrypt (can be used for passwords, OTPs, tokens, etc.).

    Args:
        text: Plain text string to hash

    Returns:
        str: Hashed string
    """
    text_bytes = text.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(text_bytes, salt)
    return hashed.decode('utf-8')


def verify_hash(plain_text: str, hashed_text: str) -> bool:
    """
    Verify plain text against bcrypt hash.

    Args:
        plain_text: Plain text string
        hashed_text: Hashed string from storage

    Returns:
        bool: True if text matches hash, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plain_text.encode('utf-8'),
            hashed_text.encode('utf-8')
        )
    except Exception:
        return False


# ========== CONVENIENCE WRAPPERS ==========

def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.
    Convenience wrapper around hash_string.

    Args:
        password: Plain text password

    Returns:
        str: Hashed password
    """
    return hash_string(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.
    Convenience wrapper around verify_hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database

    Returns:
        bool: True if password matches, False otherwise
    """
    return verify_hash(plain_password, hashed_password)


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


# ========== SECURE TOKEN GENERATION ==========

def generate_secure_token(num_bytes: int = 32) -> str:
    """
    Generate secure random token for various purposes (verification, reset, etc.).

    Args:
        num_bytes: Number of random bytes to generate (default 32)

    Returns:
        str: URL-safe random token
    """
    return secrets.token_urlsafe(num_bytes)

