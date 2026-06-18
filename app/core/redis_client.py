"""
Shared Redis client for caching and temporary data storage.
Available for use across all modules.
"""
import redis
from typing import Optional
import os
from app.core.config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, REDIS_DECODE_RESPONSES
)

REDIS_SSL = os.getenv("REDIS_SSL", "false").strip().lower() in {"1", "true", "yes"}


class RedisClient:
    """Singleton Redis client wrapper."""

    _instance: Optional[redis.Redis] = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        """
        Get Redis client instance (singleton pattern).

        Returns:
            redis.Redis: Redis client instance
        """
        if cls._instance is None:
            cls._instance = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=REDIS_DECODE_RESPONSES,
                socket_connect_timeout=5,
                socket_timeout=5,
                ssl=REDIS_SSL,
            )

            # Test connection
            try:
                cls._instance.ping()
                print("✅ Redis connected successfully")
            except redis.ConnectionError:
                print("⚠️ Warning: Could not connect to Redis. Using fallback storage.")
                cls._instance = None

        return cls._instance

    @classmethod
    def close(cls):
        """Close Redis connection."""
        if cls._instance:
            cls._instance.close()
            cls._instance = None


def get_redis() -> Optional[redis.Redis]:
    """
    Dependency function to get Redis client.

    Returns:
        redis.Redis or None: Redis client if available, None if not connected
    """
    try:
        return RedisClient.get_client()
    except Exception as e:
        print(f"Redis connection error: {e}")
        return None

