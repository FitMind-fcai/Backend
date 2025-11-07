"""
Service layer for authentication business logic.
Contains auth, email, OTP, and verification services.
"""
from auth_module.services import auth_service
from auth_module.services import email_service
from auth_module.services import otp_service_redis
from auth_module.services import verification_service

__all__ = [
    "auth_service",
    "email_service",
    "otp_service_redis",
    "verification_service",
]
