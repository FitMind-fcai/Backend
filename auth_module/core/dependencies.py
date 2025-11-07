"""
FastAPI dependencies for authentication.
Provides reusable dependency functions for route protection.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError

from app.database import get_db
from auth_module.core.security import verify_access_token
from auth_module.models.user import User


# HTTP Bearer token scheme for extracting JWT from Authorization header
security = HTTPBearer()


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
        
    Usage:
        @router.get("/protected")
        async def protected_route(current_user: User = Depends(get_current_user)):
            return {"user": current_user.email}
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
    
    # Fetch user from database
    user = db.query(User).filter(User.id == user_id, User.email == email).first()
    
    if user is None:
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
        
    Usage:
        @router.get("/verified-only")
        async def verified_route(current_user: User = Depends(get_current_verified_user)):
            return {"message": "Access granted to verified users only"}
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
        
    Usage:
        @router.get("/public-or-private")
        async def flexible_route(current_user: User | None = Depends(get_optional_current_user)):
            if current_user:
                return {"message": f"Welcome back, {current_user.name}"}
            return {"message": "Welcome, guest"}
    """
    try:
        token = credentials.credentials
        payload = verify_access_token(token)
        
        user_id: int = payload.get("id")
        email: str = payload.get("email")
        
        if user_id is None or email is None:
            return None
        
        user = db.query(User).filter(User.id == user_id, User.email == email).first()
        return user
        
    except (JWTError, Exception):
        return None
