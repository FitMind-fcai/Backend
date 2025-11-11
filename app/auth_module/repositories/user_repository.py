"""
User repository for data access operations.
Handles all database operations related to User model.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.shared.repositories.base_repository import BaseRepository
from app.auth_module.models.user import User


class UserRepository(BaseRepository[User]):
    """
    Repository for User model with specific query methods.
    """

    def __init__(self, db: Session):
        """
        Initialize UserRepository.

        Args:
            db: Database session
        """
        super().__init__(User, db)

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            email: User's email address

        Returns:
            User instance or None if not found
        """
        return self.get_by_filter(email=email)

    def email_exists(self, email: str) -> bool:
        """
        Check if email already exists in database.

        Args:
            email: Email address to check

        Returns:
            True if email exists, False otherwise
        """
        return self.exists(email=email)

    def create_user(self, name: str, email: str, age: int, hashed_password: str) -> User:
        """
        Create a new user with the given details.

        Args:
            name: User's name
            email: User's email address
            age: User's age
            hashed_password: User's hashed password

        Returns:
            Created User instance
        """
        user_data = {
            "name": name,
            "email": email,
            "age": age,
            "password": hashed_password,
            "is_verified": False
        }
        return self.create(user_data)

    def update_password(self, user: User, new_hashed_password: str) -> User:
        """
        Update user's password.

        Args:
            user: User instance
            new_hashed_password: New hashed password

        Returns:
            Updated User instance
        """
        user.password = new_hashed_password
        self.db.commit()
        self.db.refresh(user)
        return user

    def mark_as_verified(self, user: User) -> User:
        """
        Mark user's email as verified.

        Args:
            user: User instance

        Returns:
            Updated User instance
        """
        user.is_verified = True
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_verified_users(self, skip: int = 0, limit: int = 100):
        """
        Get all verified users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of verified User instances
        """
        return self.get_all_by_filter(skip=skip, limit=limit, is_verified=True)

    def get_unverified_users(self, skip: int = 0, limit: int = 100):
        """
        Get all unverified users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of unverified User instances
        """
        return self.get_all_by_filter(skip=skip, limit=limit, is_verified=False)
"""
Shared repository interfaces and base classes.
"""
from app.shared.repositories.base_repository import BaseRepository

__all__ = ["BaseRepository"]

