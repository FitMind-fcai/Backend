"""
Redis client for authentication module.
Re-exports shared Redis client from app.core.redis_client
"""

from app.core.redis_client import RedisClient, get_redis

__all__ = ["RedisClient", "get_redis"]
