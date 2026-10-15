"""Redis 客户端封装：查询缓存与限流共用

设计原则：Redis 不可用时自动降级 —— 缓存读写直接跳过，限流退回进程内实现，
绝不让「本地没起 Redis」阻断演示或测试。
"""
import logging

from app.core.config import settings

logger = logging.getLogger("app.redis")

_client = None


def _connect():
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        logger.info("Redis 已连接：%s", settings.redis_url)
        return client
    except Exception as exc:  # 连不上不是致命错误，降级即可
        logger.warning("Redis 不可用，缓存与限流将降级为进程内实现：%s", exc)
        return None


def get_client():
    """返回 Redis 客户端；不可用时返回 None（结果会被缓存，避免反复重连）"""
    global _client
    if _client is None:
        _client = _connect() or False
    return _client or None


def ping() -> bool:
    """探活"""
    client = get_client()
    if not client:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False


def cache_get(key: str) -> str | None:
    client = get_client()
    if not client:
        return None
    try:
        return client.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int | None = None) -> None:
    client = get_client()
    if not client:
        return
    try:
        client.set(key, value, ex=ttl or settings.cache_ttl_seconds)
    except Exception:
        pass


def eval_script(script: str, keys: list[str], args: list) -> int | None:
    """执行 Lua 脚本（限流用）；Redis 不可用时返回 None，由调用方降级"""
    client = get_client()
    if not client:
        return None
    try:
        return client.eval(script, len(keys), *keys, *args)
    except Exception:
        return None
