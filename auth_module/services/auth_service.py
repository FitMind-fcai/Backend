from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from auth_module.models.user import User
from auth_module.schemas.user import UserCreate, UserLogin
from auth_module.core.security import hash_password, verify_password, create_access_token
from auth_module.services.verification_service import (
    create_verification_token, validate_verification_token, delete_verification_token
)


def create_user(user_data: UserCreate, db: Session) -> tuple[User, str]:
    """
    Create a new user account and generate verification token.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        tuple[User, str]: User object and verification token
        
    Raises:
        HTTPException 400: If email already exists
    """
    # Check if user exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        age=user_data.age,
        password=hash_password(user_data.password),
        is_verified=False
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Create verification token in Redis
    verification_token = create_verification_token(new_user.email)
    
    return new_user, verification_token


def authenticate_user(credentials: UserLogin, db: Session) -> tuple[User, str]:
    """
    Authenticate user and generate access token.
    
    Args:
        credentials: Login credentials (email and password)
        db: Database session
        
    Returns:
        tuple[User, str]: User object and JWT access token
        
    Raises:
        HTTPException 401: If credentials are invalid
        HTTPException 403: If email is not verified
    """
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in"
        )
    
    access_token = create_access_token(user.id, user.email)
    
    return user, access_token


def verify_user_email(token: str, db: Session) -> User:
    """
    Verify user's email address using verification token from Redis.
    
    Args:
        token: Email verification token
        db: Database session
        
    Returns:
        User: Verified user object
        
    Raises:
        HTTPException 400: If token is invalid or expired
        HTTPException 404: If user not found
    """
    # Validate token and get email from Redis
    email = validate_verification_token(token)
    
    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Mark user as verified
    user.is_verified = True
    db.commit()
    db.refresh(user)
    
    # Delete token from Redis after successful verification
    delete_verification_token(token)
    
    return user


def resend_verification(email: str, db: Session) -> str:
    """
    Resend verification email to user.
    
    Args:
        email: User's email address
        db: Database session
        
    Returns:
        str: New verification token
        
    Raises:
        HTTPException 404: If user not found
        HTTPException 400: If email already verified
    """
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Generate new token in Redis (old one will be overwritten/expired)
    verification_token = create_verification_token(email)
    
    return verification_token


def reset_user_password(user: User, new_password: str, db: Session) -> None:
    """
    Reset user's password.
    
    Args:
        user: User object
        new_password: New password (plain text)
        db: Database session
    """
    user.password = hash_password(new_password)
    db.commit()
    



def get_user_by_email(email: str, db: Session) -> User:
    """
    Get user by email address.
    
    Args:
        email: User's email address
        db: Database session
        
    Returns:
        User: User object
        
    Raises:
        HTTPException 404: If user not found
    """
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user
