import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from app.database import get_db
from models.user import User
from schema.user import (
    UserLogin, UserResponse, UserCreate, LoginResponse,
    EmailVerificationRequest, VerifyEmailRequest
)
from utils.email_service import send_verification_email, send_resend_verification_email

authRouter = APIRouter(prefix="/auth", tags=["Authentication"])

# JWT Secret
SECRET_KEY = "your-secret-key-change-this"  # TODO: Move to environment variable


def generate_verification_token() -> str:
    """Generate a secure random token for email verification."""
    return secrets.token_urlsafe(32)


@authRouter.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user account and send verification email.
    """
    # Check if user exists
    existing_user = db.query(User).filter(User.email == user.email).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Hash password
    password_bytes = user.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    # Generate verification token
    verification_token = generate_verification_token()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    
    # Create new user
    new_user = User(
        name=user.name,
        email=user.email,
        age=user.age,
        password=hashed_password,
        is_verified=False,
        verification_token=verification_token,
        verification_token_expires=token_expires
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Send verification email
    email_sent = send_verification_email(new_user.email, verification_token)
    
    if not email_sent:
        # Log the error but don't fail registration
        print(f"⚠️ Warning: Could not send verification email to {new_user.email}")
    
    return new_user


@authRouter.post("/login", response_model=LoginResponse)
def login(user: UserLogin, db: Session = Depends(get_db)):
    """
    Login endpoint - authenticates user and returns JWT token.
    
    ⚠️ User must verify their email before logging in.
    """
    # Find user
    db_user = db.query(User).filter(User.email == user.email).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user found with this email"
        )
    
    # Check if email is verified
    if not db_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in. Check your inbox for the verification link."
        )
    
    # Verify password
    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user.password.encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Create JWT token
    token = jwt.encode({
        'id': db_user.id,
        'email': db_user.email
    }, SECRET_KEY, algorithm='HS256')
    
    return {
        'token': token,
        'user': db_user
    }


@authRouter.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verify user's email address.
    
    This endpoint is called when user clicks the link in their verification email.
    """
    # First, try to find user with this verification token
    user = db.query(User).filter(User.verification_token == token).first()
    
    if not user:
        # Token not found - maybe already used or invalid
        # Check if any user was verified with this token recently (already verified case)
        # For better UX, we can't distinguish between "already verified" and "invalid token"
        # without storing verification history, so we show a generic helpful message
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token. If you already verified your email, you can login directly."
        )
    
    # Check if token has expired
    if user.verification_token_expires < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired. Please request a new one."
        )
        
    # Mark user as verified
    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    
    db.commit()
    
    return {
        "message": "Email verified successfully! You can now login.",
        "verified": True
    }


@authRouter.post("/resend-verification")
def resend_verification_email(request: EmailVerificationRequest, db: Session = Depends(get_db)):
    """
    Resend verification email if user didn't receive it or token expired.
    """
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found with this email"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )
    
    # Generate new token
    verification_token = generate_verification_token()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    
    user.verification_token = verification_token
    user.verification_token_expires = token_expires
    
    db.commit()
    
    # Send email
    email_sent = send_resend_verification_email(user.email, verification_token)
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again later."
        )
    
    return {
        "message": "Verification email sent successfully. Please check your inbox."
    }


def verify_token(x_auth_token = Header()):
    try:
        if not x_auth_token:
            raise HTTPException(401, 'Token not found')
        token = jwt.decode(x_auth_token, SECRET_KEY, algorithms=['HS256'])
        if not token:
            raise HTTPException(401, "Token verification failed")
        uid = token.get('id')
        return {
            'id': uid,
            'token': token
        }
    except JWTError:
        raise HTTPException(401, "Token verification failed")


@authRouter.get("/me", response_model=UserResponse)
def get_current_user(db: Session = Depends(get_db), user = Depends(verify_token)):
    """
    Get current authenticated user information.
    """
    user_db = db.query(User).filter(user['id'] == User.id).first()
    if not user_db:
        raise HTTPException(404, "User not found")
    return user_db