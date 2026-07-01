"""Root conftest: sets environment variables before any app module is imported."""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-chars-ok")
os.environ.setdefault("AUTO_VERIFY_USERS", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fitmind_test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("SENDER_EMAIL", "test@example.com")
os.environ.setdefault("SENDER_PASSWORD", "test-password")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", "")
