"""
Shared configuration settings for the entire application.
Contains database, Redis, JWT, SMTP, and other global configurations.
"""
import os
from typing import Optional

# ========== Database Configuration ==========
_raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/fitmind"
)
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+"):
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
DATABASE_URL = _raw_db_url
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "false").strip().lower() in {"1", "true", "yes", "on"}
SQLALCHEMY_LOG_LEVEL = os.getenv("SQLALCHEMY_LOG_LEVEL", "WARNING").upper()

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
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") 
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ========== Email SMTP Configuration ==========
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")  # Set in environment
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")  # Set in environment
APP_URL = os.getenv("APP_URL", "http://localhost:8000")  # Change in production

# ========== CORS Configuration ==========
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000"
    ).split(",")
    if origin.strip()
]

# ========== Password Configuration ==========
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 50

# ========== Firebase / FCM Configuration ==========
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

# ========== AI Coach Configuration ==========
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")  # Set in environment
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
AI_COACH_TEMPERATURE = float(os.getenv("AI_COACH_TEMPERATURE", "0.3"))
AI_COACH_MAX_TOKENS = int(os.getenv("AI_COACH_MAX_TOKENS", "4000"))

# Evaluation-specific Groq settings (keeps evaluation independent from coach provider)
EVAL_GROQ_API_KEY = os.getenv("EVAL_GROQ_API_KEY", GROQ_API_KEY)
EVAL_GROQ_MODEL = os.getenv("EVAL_GROQ_MODEL", GROQ_MODEL)

# Max attempts for the INITIAL plan generation call when the model returns
# malformed JSON or output that fails schema validation (regenerate instead
# of failing the request).
AI_MAX_GENERATION_RETRIES = int(os.getenv("AI_MAX_GENERATION_RETRIES", "2"))

# Provider-agnostic LLM settings (used by AI Coach)
# Supported providers include: groq, openrouter, openai, together, deepinfra, fireworks.
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-120b")

# Optional provider-specific keys (fallback when AI_API_KEY is not set)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")

# Optional OpenRouter headers
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "FitMind")