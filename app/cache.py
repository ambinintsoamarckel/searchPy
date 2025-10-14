"""Cache management module."""
import redis.asyncio as redis
from app.config import settings

class CacheManager:
    """A class to manage the Redis cache."""
    def __init__(self):
        """Initialize the CacheManager."""
        self.redis_url = settings.REDIS_URL
        self.redis = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)

    async def get(self, key: str):
        """Get a value from the cache."""
        return await self.redis.get(key)

    async def set(self, key: str, value: str, expire: int = 300):
        """Set a value in the cache."""
        await self.redis.set(key, value, ex=expire)

    async def close(self):
        """Close the Redis connection."""
        await self.redis.close()

cache_manager = CacheManager()
