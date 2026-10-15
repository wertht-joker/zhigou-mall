"""令牌桶限流

优先用 Redis（多实例共享配额），Redis 不可用时退回进程内内存桶。
限流键 = 接口标识 + 调用方身份（访问令牌哈希 / 客户端 IP）。
"""
import hashlib
import threading
import time

from fastapi import Request

from app.core import redis as redis_cache
from app.core.config import settings
from app.core.errors import RateLimitError

# 原子化令牌桶：返回 1 放行、0 拒绝
_TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = math.max(0, now - ts) / 1000
tokens = math.min(capacity, tokens + delta * refill)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / refill) * 1000)
return allowed
"""


class MemoryTokenBucket:
    """进程内令牌桶（Redis 不可用时的兜底实现）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, capacity: float, refill: float) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, ts = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - ts) * refill)
            if tokens >= 1:
                tokens -= 1
                allowed = True
            else:
                allowed = False
            self._buckets[key] = (tokens, now)
            return allowed

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


_memory = MemoryTokenBucket()


def reset_memory_buckets() -> None:
    """清空进程内令牌桶（测试用）"""
    _memory.clear()


def _identity(request: Request) -> str:
    """限流身份：优先用访问令牌（做哈希，避免明文入键），否则退回客户端 IP"""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return "t" + hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
    client = request.client
    return "ip" + (client.host if client else "unknown")


def allow(key: str) -> bool:
    """消费一个令牌，返回是否放行"""
    capacity = settings.rate_limit_capacity
    refill = settings.rate_limit_refill_per_second
    redis_result = redis_cache.eval_script(
        _TOKEN_BUCKET_LUA, [f"rl:{key}"], [capacity, refill, int(time.time() * 1000)]
    )
    if redis_result is not None:
        return bool(int(redis_result))
    return _memory.allow(key, capacity, refill)


def rate_limit(tag: str):
    """生成一个限流依赖：按「接口标识 + 调用方」维度限流"""

    async def _dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        if not allow(f"{tag}:{_identity(request)}"):
            raise RateLimitError()

    return _dependency
