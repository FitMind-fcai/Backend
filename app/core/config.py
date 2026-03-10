"""
Shared configuration settings for the entire application.
Contains database, Redis, JWT, SMTP, and other global configurations.
"""
import os
from typing import Optional

# ========== Database Configuration ==========
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/fitmind"
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
REDIS_OTP_RESEND_COOLDOWN_PREFIX = "otp_cooldown:"  # otp_cooldown:user@email.com
REDIS_OTP_HOURLY_COUNT_PREFIX = "otp_hourly:"  # otp_hourly:user@email.com
REDIS_OTP_DAILY_COUNT_PREFIX = "otp_daily:"  # otp_daily:user@email.com
REDIS_OTP_BLOCKED_PREFIX = "otp_blocked:"  # otp_blocked:user@email.com
REDIS_VERIFICATION_PREFIX = "verify:"  # verify:token_string

# ========== JWT Configuration ==========
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # Required — must be set in environment
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ========== Email SMTP Configuration ==========
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")  # Set in environment
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")  # Set in environment
APP_URL = os.getenv("APP_URL", "http://localhost:8000")  # Change in production

# ========== Password Configuration ==========
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 50

# ========== AI Coach Configuration ==========
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")  # Set in environment
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
AI_COACH_TEMPERATURE = float(os.getenv("AI_COACH_TEMPERATURE", "0.3"))
AI_COACH_MAX_TOKENS = int(os.getenv("AI_COACH_MAX_TOKENS", "4000"))