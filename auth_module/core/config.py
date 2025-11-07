"""
Configuration settings for authentication module.
Contains all constants and configuration values.
"""
import os
from datetime import timedelta

# ========== JWT Configuration ==========
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this")  # TODO: Move to environment variable
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ========== OTP Configuration ==========
OTP_LENGTH = 4
OTP_EXPIRATION_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# ========== Email Verification Configuration ==========
VERIFICATION_TOKEN_EXPIRATION_HOURS = 24

# ========== Email SMTP Configuration ==========
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "fitmind.dev.fcai@gmail.com"
SENDER_PASSWORD = "reiislglpgbmoafr"  # Use app password for Gmail
APP_URL = "http://localhost:8000"  # Change in production

# ========== Password Configuration ==========
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 50

# ========== Redis Configuration ==========
# Use environment variable for Docker, fallback to localhost for local dev
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = 0
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)  # Set if Redis has password
REDIS_DECODE_RESPONSES = True  # Auto decode bytes to strings

# Redis Key Prefixes
REDIS_OTP_PREFIX = "otp:"  # otp:user@email.com
REDIS_OTP_ATTEMPTS_PREFIX = "otp_attempts:"  # otp_attempts:user@email.com
REDIS_VERIFICATION_PREFIX = "verify:"  # verify:token_string
