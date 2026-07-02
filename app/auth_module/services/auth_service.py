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

    def create_user(self, user_data: UserCreate, auto_verify: bool = False) -> tuple[User, str]:
        """
        Create a new user account and generate verification token.

        Args:
            user_data: User registration data
            auto_verify: If True, skip email and auto-verify

        Returns:
            tuple[User, str]: User object and verification token

        Raises:
            HTTPException 400: If email already exists
        """
        if self.user_repo.email_exists(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        hashed_password = hash_password(user_data.password)
        db = self.user_repo.db

        user = User(
            name=user_data.name,
            email=user_data.email,
            password=hashed_password,
            is_verified=auto_verify,
        )
        db.add(user)
        db.flush()

        if auto_verify:
            db.commit()
            db.refresh(user)
            return user, ""

        verification_token = self.verification_service.create_verification_token(user.email)
        email_sent = self.email_service.send_verification_email(user.email, verification_token)

        if not email_sent:
            db.rollback()
            self.verification_service.delete_verification_token(verification_token)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not send verification email. Please try again later."
            )

        db.commit()
        db.refresh(user)
        return user, verification_token

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

    def delete_account(self, user: User, password: str) -> None:
        """
        Permanently delete a user account and all of their data.

        Args:
            user: The authenticated user requesting deletion
            password: Current password, required to confirm this irreversible action

        Raises:
            HTTPException 401: If the password is incorrect

        Deletion order matters:
          1. workout_logs first — they reference workout_day_exercises, which is
             about to cascade away in step 3, so they'd otherwise dangle.
          2. Other tracking logs — independent leaf tables, order-agnostic.
          3. Workout/nutrition plans — deleted via ORM `session.delete()` per row
             (not a bulk `.delete()` query) so the `cascade="all, delete-orphan"`
             already configured on these models actually fires, removing
             days/meals/exercises/ingredients underneath each plan.
          4. Profile.
          5. Catalog attribution (central_foods/central_exercises.created_by_user_id)
             is nulled, not cascaded — these are shared catalog rows other users'
             plans may still reference.
          6. The user row itself — device_tokens, notification_preferences, and
             coaching_messages are already ON DELETE CASCADE at the DB level.
        """
        if not verify_password(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password"
            )

        # Imported locally to avoid a circular import: tracking_module/planning_module
        # routes import AuthService (via get_current_verified_user), so importing their
        # models at module load time here would create an import cycle.
        from app.profile_module.models.profile import Profile
        from app.planning_module.models.plan import WorkoutPlan, NutritionPlan, CentralFood, CentralExercise
        from app.tracking_module.models.workout_log import WorkoutLog
        from app.tracking_module.models.meal_log import MealLog
        from app.tracking_module.models.sleep_log import SleepLog
        from app.tracking_module.models.hydration_log import HydrationLog
        from app.tracking_module.models.weight_log import WeightLog

        db = self.user_repo.db
        try:
            db.query(WorkoutLog).filter(WorkoutLog.user_id == user.id).delete(synchronize_session=False)
            db.query(MealLog).filter(MealLog.user_id == user.id).delete(synchronize_session=False)
            db.query(SleepLog).filter(SleepLog.user_id == user.id).delete(synchronize_session=False)
            db.query(HydrationLog).filter(HydrationLog.user_id == user.id).delete(synchronize_session=False)
            db.query(WeightLog).filter(WeightLog.user_id == user.id).delete(synchronize_session=False)

            for plan in db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).all():
                db.delete(plan)
            for plan in db.query(NutritionPlan).filter(NutritionPlan.user_id == user.id).all():
                db.delete(plan)

            db.query(Profile).filter(Profile.user_id == user.id).delete(synchronize_session=False)

            db.query(CentralFood).filter(CentralFood.created_by_user_id == user.id).update(
                {CentralFood.created_by_user_id: None}, synchronize_session=False
            )
            db.query(CentralExercise).filter(CentralExercise.created_by_user_id == user.id).update(
                {CentralExercise.created_by_user_id: None}, synchronize_session=False
            )

            db.delete(user)
            db.commit()
        except Exception:
            db.rollback()
            raise

    def get_user_by_email(self, email: str, require_verified: bool = False) -> User:
        """
        Get user by email address.

        Args:
            email: User's email address
            require_verified: If True, raises exception if user not verified

        Returns:
            User: User object

        Raises:
            HTTPException 404: If user not found
            HTTPException 403: If user not verified and require_verified=True
        """
        user = self.user_repo.get_by_email(email)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if require_verified and not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email before using this feature"
            )

        return user

