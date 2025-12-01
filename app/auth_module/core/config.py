"""
Authentication module specific configuration.
Contains only auth-related constants (OTP, Email Verification).
Shared configs (JWT, Redis, SMTP, Password) are in app.core.config
"""

# ========== OTP Configuration ==========
OTP_LENGTH = 5
OTP_EXPIRATION_MINUTES = 10
OTP_MAX_ATTEMPTS = 4

# ========== OTP Rate Limiting Configuration ==========
OTP_RESEND_COOLDOWN_MINUTES = 2  # Wait time between each OTP request
OTP_MAX_REQUESTS_PER_HOUR = 3  # Max OTP requests per hour
OTP_MAX_REQUESTS_PER_DAY = 5  # Max OTP requests per day
OTP_HOURLY_BLOCK_DURATION_HOURS = 1  # Block duration after hourly limit
OTP_DAILY_BLOCK_DURATION_HOURS = 24  # Block duration after daily limit

# ========== Email Verification Configuration ==========
VERIFICATION_TOKEN_EXPIRATION_HOURS = 24

