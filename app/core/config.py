"""
Shared configuration settings for the entire application.
Contains database, Redis, JWT, SMTP, and other global configurations.
"""
import os
from typing import Optional

# ========== Database Configuration ==========
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:ahmad123@localhost:5432/fitmind"
)

# ========== Redis Configuration ==========
# Use environment variable for Docker, fallback to localhost for local dev
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = 0
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)  # Set if Redis has password
REDIS_DECODE_RESPONSES = True  # Auto decode bytes to strings

# Redis Key Prefixes (can be extended by individual modules)
REDIS_OTP_PREFIX = "otp:"  # otp:user@email.com
REDIS_OTP_ATTEMPTS_PREFIX = "otp_attempts:"  # otp_attempts:user@email.com
REDIS_VERIFICATION_PREFIX = "verify:"  # verify:token_string

# ========== JWT Configuration ==========
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this")  # TODO: Move to environment variable
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ========== Email SMTP Configuration ==========
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "fitmind.dev.fcai@gmail.com"
SENDER_PASSWORD = "reiislglpgbmoafr"  # Use app password for Gmail
APP_URL = os.getenv("APP_URL", "http://localhost:8000")  # Change in production

# ========== Password Configuration ==========
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 50