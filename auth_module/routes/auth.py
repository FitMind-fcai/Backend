from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from auth_module.models.user import User
from auth_module.schemas.user import (
    UserLogin, UserResponse, UserCreate, LoginResponse,
    EmailVerificationRequest, VerifyEmailRequest, ForgotPasswordRequest,
    VerifyOTPRequest, ResetPasswordRequest
)
from auth_module.services.auth_service import (
    create_user, authenticate_user, verify_user_email,
    resend_verification, get_user_by_email, reset_user_password
)
from auth_module.services.otp_service_redis import (
    create_password_reset_otp, validate_otp, clear_otp
)
from auth_module.services.email_service import (
    send_verification_email, send_resend_verification_email,
    send_password_reset_otp
)
from auth_module.core.dependencies import get_current_user

authRouter = APIRouter(prefix="/auth", tags=["Authentication"])


# ========== SIGNUP ==========
@authRouter.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account.
    
    - Creates user account with hashed password
    - Generates email verification token in Redis
    - Sends verification email
    """
    # Create user using service (returns user and token from Redis)
    new_user, verification_token = create_user(user_data, db)
    
    # Send verification email
    email_sent = send_verification_email(new_user.email, verification_token)
    
    if not email_sent:
        print(f"Warning: Could not send verification email to {new_user.email}")
    
    return new_user


# ========== LOGIN ==========
@authRouter.post("/login", response_model=LoginResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    
    - Validates email and password
    - Checks email verification status
    - Returns JWT access token
    """
    user, access_token = authenticate_user(credentials, db)
    
    return {
        "token": access_token,
        "user": user
    }


# ========== VERIFY EMAIL ==========
@authRouter.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verify user's email address via token from email link.
    
    - Validates verification token
    - Marks user as verified
    - Clears verification token
    """
    user = verify_user_email(token, db)
    
    return {
        "message": "Email verified successfully! You can now login.",
        "verified": True
    }


# ========== RESEND VERIFICATION ==========
@authRouter.post("/resend-verification")
def resend_verification_email_route(request: EmailVerificationRequest, db: Session = Depends(get_db)):
    """
    Resend verification email to user.
    
    - Generates new verification token in Redis
    - Sends new verification email
    """
    verification_token = resend_verification(request.email, db)
    
    # Send email
    email_sent = send_resend_verification_email(request.email, verification_token)
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again later."
        )
    
    return {"message": "Verification email sent successfully"}
    


# ========== GET CURRENT USER ==========
@authRouter.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's information.
    
    Requires: Valid JWT token in x-auth-token header
    """
    return current_user


# ========== FORGOT PASSWORD ==========
@authRouter.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Initiate password reset by sending OTP to user's email.
    
    - Generates 4-digit OTP
    - Stores hashed OTP in Redis with expiration
    - Sends OTP via email
    """
    user = get_user_by_email(request.email, db)
    
    # Generate and store OTP in Redis
    otp = create_password_reset_otp(user.email)
    
    # Send OTP via email
    email_sent = send_password_reset_otp(user.email, otp)
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again later."
        )
    
    return {
        "message": "OTP sent to your email. Valid for 10 minutes.",
        "email": user.email
    }


# ========== VERIFY OTP ==========
@authRouter.post("/verify-reset-otp")
def verify_reset_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Verify OTP for password reset.
    
    - Validates OTP from Redis
    - Checks expiration and attempts
    - Tracks failed attempts
    """
    # Verify user exists
    user = get_user_by_email(request.email, db)
    
    # Validate OTP from Redis (raises exception if invalid)
    validate_otp(request.email, request.otp)
    
    return {
        "message": "OTP verified successfully. You can now reset your password.",
        "verified": True
    }


# ========== RESET PASSWORD ==========
@authRouter.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset user's password after OTP verification.
    
    - Verifies OTP one final time from Redis
    - Updates password
    - Clears OTP data from Redis
    """
    user = get_user_by_email(request.email, db)
    
    # Validate OTP from Redis again (raises exception if invalid)
    validate_otp(request.email, request.otp)
    
    # Reset password
    reset_user_password(user, request.new_password, db)
    
    # Clear OTP from Redis
    clear_otp(request.email)
    
    return {
        "message": "Password reset successfully. You can now login with your new password.",
        "success": True
    }
