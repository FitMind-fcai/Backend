"""
Redis client for authentication module.
Re-exports shared Redis client from app.core.redis_client
"""

# Re-export shared Redis client for backward compatibility
from app.core.redis_client import RedisClient, get_redis

__all__ = ["RedisClient", "get_redis"]
