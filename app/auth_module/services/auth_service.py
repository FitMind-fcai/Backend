"""
Authentication service with proper dependency injection.
Contains business logic for user authentication, registration, and verification.
"""
from fastapi import HTTPException, status
from app.auth_module.models.user import User
from app.auth_module.schemas.user import UserCreate, UserLogin
from app.auth_module.core.security import hash_password, verify_password, create_access_token
from app.auth_module.repositories.user_repository import UserRepository
from app.auth_module.services.verification_service import VerificationService
from app.auth_module.services.email_service import AuthEmailService


class AuthService:
    """
    Authentication service handling user registration, login, and verification.
    Uses dependency injection for repositories and other services.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        verification_service: VerificationService,
        auth_email_service: AuthEmailService
    ):
        """
        Initialize AuthService with injected dependencies.

        Args:
            user_repository: Repository for user data access
            verification_service: Service for email verification
            auth_email_service: Service for sending auth-specific emails
        """
        self.user_repo = user_repository
        self.verification_service = verification_service
        self.email_service = auth_email_service

    def create_user(self, user_data: UserCreate) -> tuple[User, str]:
        """
        Create a new user account and generate verification token.

        Args:
            user_data: User registration data

        Returns:
            tuple[User, str]: User object and verification token

        Raises:
            HTTPException 400: If email already exists
        """
        # Check if user exists
        if self.user_repo.email_exists(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user
        hashed_password = hash_password(user_data.password)
        new_user = self.user_repo.create_user(
            name=user_data.name,
            email=user_data.email,
            age=user_data.age,
            hashed_password=hashed_password
        )

        # Create verification token
        verification_token = self.verification_service.create_verification_token(new_user.email)

        return new_user, verification_token

    def authenticate_user(self, credentials: UserLogin) -> tuple[User, str]:
        """
        Authenticate user and generate access token.

        Args:
            credentials: Login credentials (email and password)

        Returns:
            tuple[User, str]: User object and JWT access token

        Raises:
            HTTPException 401: If credentials are invalid
            HTTPException 403: If email is not verified
        """
        # Get user by email
        user = self.user_repo.get_by_email(credentials.email)

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

    def verify_user_email(self, token: str) -> User:
        """
        Verify user's email address using verification token.

        Args:
            token: Email verification token

        Returns:
            User: Verified user object

        Raises:
            HTTPException 400: If token is invalid or expired
            HTTPException 404: If user not found
        """
        # Validate token and get email
        email = self.verification_service.validate_verification_token(token)

        # Find user by email
        user = self.user_repo.get_by_email(email)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Mark user as verified
        user = self.user_repo.mark_as_verified(user)

        # Delete token after successful verification
        self.verification_service.delete_verification_token(token)

        return user

    def resend_verification(self, email: str) -> str:
        """
        Resend verification email to user.

        Args:
            email: User's email address

        Returns:
            str: New verification token

        Raises:
            HTTPException 404: If user not found
            HTTPException 400: If email already verified
        """
        user = self.user_repo.get_by_email(email)

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

        # Generate new token (old one will be overwritten/expired)
        verification_token = self.verification_service.create_verification_token(email)

        return verification_token

    def reset_user_password(self, user: User, new_password: str) -> None:
        """
        Reset user's password.

        Args:
            user: User object
            new_password: New password (plain text)
        """
        hashed_password = hash_password(new_password)
        self.user_repo.update_password(user, hashed_password)

    def get_user_by_email(self, email: str) -> User:
        """
        Get user by email address.

        Args:
            email: User's email address

        Returns:
            User: User object

        Raises:
            HTTPException 404: If user not found
        """
        user = self.user_repo.get_by_email(email)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return user

