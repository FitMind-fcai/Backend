from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import DATABASE_URL, SQLALCHEMY_ECHO
import os

# Create Base class here to avoid circular imports
Base = declarative_base()

# Pool sized to match the anyio thread-pool limit so no request ever blocks
# waiting for a DB connection.  Both values are tunable via env vars.
_pool_size    = int(os.getenv("DB_POOL_SIZE", "20"))
_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))

engine = create_engine(
    DATABASE_URL,
    echo=SQLALCHEMY_ECHO,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_pre_ping=True,   # drop stale connections before handing them out
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create all tables
def create_tables():
    # Import models here to register them with Base
    Base.metadata.create_all(bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
