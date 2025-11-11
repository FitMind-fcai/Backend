"""
Shared components used across all modules.
Includes repositories, services, schemas, and utilities.
"""
from app.shared.services.email_service import EmailService
from app.shared.repositories.base_repository import BaseRepository

__all__ = [
    "EmailService",
    "BaseRepository",
]

