import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from app.auth_module.models.user import User
from app.auth_module.schemas.user import (
    UserLogin, UserResponse, UserCreate, LoginResponse,
    EmailVerificationRequest, ForgotPasswordRequest,
    VerifyOTPRequest, ResetPasswordRequest, DeleteAccountRequest
)
from app.auth_module.services.auth_service import AuthService
from app.auth_module.services.otp_service_redis import OTPService
from app.auth_module.services.email_service import AuthEmailService
from app.core.dependencies import get_current_user
from app.auth_module.core.dependencies import (
    get_auth_service,
    get_otp_service,
    get_auth_email_service
)
from app.shared.services.web_templates import render_status_page, render_resend_form

AUTO_VERIFY = os.getenv("AUTO_VERIFY_USERS", "false").strip().lower() in {"1", "true", "yes"}

authRouter = APIRouter(prefix="/auth", tags=["Authentication"])


# ========== SIGNUP ==========
@authRouter.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Register a new user account.

    - Creates user account with hashed password
    - Generates email verification token in Redis
    - Sends verification email

    Dependencies injected:
        - AuthService: Handles user creation and verification logic
        - AuthEmailService: Sends auth-specific emails
    """
    new_user, _ = auth_service.create_user(user_data, auto_verify=AUTO_VERIFY)
    return new_user


# ========== LOGIN ==========
@authRouter.post("/login", response_model=LoginResponse)
def login(
    credentials: UserLogin,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Authenticate user and return JWT token.

    - Validates email and password
    - Checks email verification status
    - Returns JWT access token

    Dependencies injected:
        - AuthService: Handles authentication logic
    """
    user, access_token = auth_service.authenticate_user(credentials)

    return {
        "token": access_token,
        "user": user
    }


# ========== VERIFY EMAIL ==========
@authRouter.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
def verify_email(
    token: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Verify user's email address via token from email link.

    Renders a browser-facing HTML page (not JSON) since this endpoint is
    meant to be opened directly from the verification email link:
    - Success: confirmation page.
    - Expired/invalid token: page with a form to request a new link
      (posts to /v1/auth/resend-verification).

    Dependencies injected:
        - AuthService: Handles email verification logic
    """
    try:
        auth_service.verify_user_email(token)
    except HTTPException:
        html = render_status_page(
            status="error",
            heading="Link Expired or Invalid",
            message="This verification link is no longer valid. Enter your email below and we'll send you a new one.",
            extra_html=render_resend_form(),
        )
        return HTMLResponse(content=html, status_code=200)

    html = render_status_page(
        status="success",
        heading="Email Verified!",
        message="Your email has been verified successfully. You can now return to the FitMind app and log in.",
    )
    return HTMLResponse(content=html, status_code=200)


# ========== RESEND VERIFICATION ==========
@authRouter.post("/resend-verification")
def resend_verification_email_route(
    request: EmailVerificationRequest,
    auth_service: AuthService = Depends(get_auth_service),
    auth_email_service: AuthEmailService = Depends(get_auth_email_service)
):
    """
    Resend verification email to user.

    - Generates new verification token in Redis
    - Sends new verification email

    Dependencies injected:
        - AuthService: Handles verification token generation
        - AuthEmailService: Sends auth-specific emails
    """
    verification_token = auth_service.resend_verification(request.email)

    # Send email
    email_sent = auth_email_service.send_resend_verification_email(request.email, verification_token)

    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again later."
        )

    return {
        "message": "Verification email has been resent. Please check your inbox.",
        "email": request.email
    }


# ========== FORGOT PASSWORD (Request OTP) ==========
@authRouter.post("/forgot-password")
def forgot_password(
    request: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
    otp_service: OTPService = Depends(get_otp_service),
    auth_email_service: AuthEmailService = Depends(get_auth_email_service)
):
    """
    Request password reset OTP.

    - Validates user exists
    - Generates OTP in Redis
    - Sends OTP via email

    Dependencies injected:
        - AuthService: Validates user exists
        - OTPService: Generates and stores OTP
        - AuthEmailService: Sends auth-specific emails
    """
    # Check if user exists
    user = auth_service.get_user_by_email(request.email, require_verified= True)

    # Generate OTP
    otp = otp_service.create_password_reset_otp(user.email)

    # Send OTP via email
    email_sent = auth_email_service.send_password_reset_otp(user.email, otp)

    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again later."
        )

    return {
        "message": "OTP has been sent to your email. It will expire in 10 minutes.",
        "email": user.email
    }


# ========== VERIFY OTP ==========
@authRouter.post("/verify-otp")
def verify_otp(
    request: VerifyOTPRequest,
    auth_service: AuthService = Depends(get_auth_service),
    otp_service: OTPService = Depends(get_otp_service)
):
    """
    Verify OTP for password reset.

    - Validates OTP from Redis
    - Checks expiration and attempt limits

    Dependencies injected:
        - AuthService: Validates user exists
        - OTPService: Validates OTP
    """
    # Check if user exists
    user = auth_service.get_user_by_email(request.email, require_verified= True)

    # Validate OTP
    otp_service.validate_otp(user.email, request.otp)

    return {
        "message": "OTP verified successfully. You can now reset your password.",
        "email": user.email
    }


# ========== RESET PASSWORD ==========
@authRouter.post("/reset-password")
def reset_password(
    request: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
    otp_service: OTPService = Depends(get_otp_service)
):
    """
    Reset user password after OTP verification.

    - Re-validates OTP
    - Updates password
    - Clears OTP from Redis

    Dependencies injected:
        - AuthService: Handles password reset and user retrieval
        - OTPService: Validates OTP and clears it
    """
    # Get user
    user = auth_service.get_user_by_email(request.email)

    # Validate OTP again
    otp_service.validate_otp(user.email, request.otp)

    # OTP is valid - clear everything
    otp_service.clear_otp(user.email)

    # Reset password
    auth_service.reset_user_password(user, request.new_password)

    # Clear OTP after successful reset
    otp_service.clear_otp(user.email)

    return {
        "message": "Password has been reset successfully. You can now login with your new password.",
        "email": user.email
    }


# ========== CHECK OTP STATUS ==========
@authRouter.get("/otp-status/{email}")
def check_otp_status(
    email: str,
    otp_service: OTPService = Depends(get_otp_service)
):
    """
    Check if user can request OTP and get remaining cooldown/block time.
    
    Returns rate limit status with remaining seconds.
    Useful for frontend to display countdown timers.
    
    Dependencies injected:
        - OTPService: Checks rate limiting status
    """
    status = otp_service.get_rate_limit_status(email)
    return status


# ========== GET CURRENT USER ==========
@authRouter.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get authenticated user's profile information.

    Requires valid JWT token in Authorization header.
    """
    return current_user


# ========== DELETE ACCOUNT ==========
@authRouter.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Permanently delete the authenticated user's account and all associated data
    (profile, plans, tracking logs, device tokens, notification preferences,
    coaching messages). Irreversible — requires the current password to confirm.
    """
    auth_service.delete_account(current_user, request.password)

