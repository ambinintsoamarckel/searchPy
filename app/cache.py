import redis.asyncio as redis
from app.config import settings

class CacheManager:
    def __init__(self):
        self.redis_url = settings.REDIS_URL
        self.redis = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)

    async def get(self, key: str):
        return await self.redis.get(key)

    async def set(self, key: str, value: str, expire: int = 300):
        await self.redis.set(key, value, ex=expire)

    async def close(self):
        await self.redis.close()

cache_manager = CacheManager()
