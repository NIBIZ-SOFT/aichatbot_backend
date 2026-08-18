import redis.asyncio as redis
from typing import Optional
from app.core.config import settings

redis_client: Optional[redis.Redis] = None

async def init_redis() -> redis.Redis:
    global redis_client
    if not redis_client:
        redis_client = redis.from_url(
            settings.get_redis_url(),
            encoding="utf-8",
            decode_responses=True
        )
    return redis_client

async def get_redis() -> redis.Redis:
    if not redis_client:
        return await init_redis()
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
