"""
Authentication module specific configuration.
Contains only auth-related constants (OTP, Email Verification).
Shared configs (JWT, Redis, SMTP, Password) are in app.core.config
"""

# ========== OTP Configuration ==========
OTP_LENGTH = 5
OTP_EXPIRATION_MINUTES = 10
OTP_MAX_ATTEMPTS = 4

# ========== Email Verification Configuration ==========
VERIFICATION_TOKEN_EXPIRATION_HOURS = 24

