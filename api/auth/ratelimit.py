"""Fixed-window rate limits in Redis (db 5, key prefix aiwazz:)."""
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass
class Limit:
    allowed: bool
    retry_after: int


async def hit(redis: Redis, prefix: str, key: str, limit: int, window_sec: int) -> Limit:
    """Count one attempt for `key`; allowed while the count within the window is ≤ limit."""
    k = f"{prefix}rl:{key}"
    async with redis.pipeline(transaction=True) as p:
        p.incr(k)
        p.expire(k, window_sec, nx=True)
        p.ttl(k)
        count, _, ttl = await p.execute()
    return Limit(allowed=count <= limit, retry_after=max(int(ttl), 1))


async def reset(redis: Redis, prefix: str, key: str) -> None:
    await redis.delete(f"{prefix}rl:{key}")
