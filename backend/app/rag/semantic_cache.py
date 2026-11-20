"""方向 D：语义缓存（embedding 近邻复用检索结果）

与精确缓存的区别：用户把「退货政策是几天」换成「几天内可以退货」，
精确哈希匹配不到，但 embedding 很近，可以直接复用检索结果，
省掉一次 BM25 + 精排（甚至一次向量召回）的成本。

一致性设计：
- 键包含 tenant_id + kb_version + 业务日期 + 检索策略；
- 文档更新时 kb_version 递增，旧缓存自然失配；
- 订单类问题默认不走语义缓存（allow_semantic_cache=False），
  避免把「某笔订单适用什么政策」缓存成通用答案。

存储：优先 Redis；本地没起 Redis 时降级为进程内字典（TTL + 容量上限），
保证单机演示也能看到缓存命中。
"""
import json
import threading
import time
from datetime import datetime

import numpy as np

from app.core.config import settings
from app.core.redis import cache_get, cache_set, get_client, get_kb_version
from app.rag.router import intent_keywords

# 进程内降级存储：key -> (过期时间戳, JSON 字符串)
_local: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def _bucket_key(tenant_id: int | None,
                effective_at: datetime | None, strategy: str) -> str:
    at = effective_at.date().isoformat() if effective_at else "-"
    return f"sem:{int(tenant_id or 0)}:{get_kb_version()}:{at}:{strategy}"


def _read(key: str) -> str | None:
    if get_client():
        return cache_get(key)
    with _lock:
        item = _local.get(key)
        if not item:
            return None
        expires_at, payload = item
        if expires_at <= time.time():
            _local.pop(key, None)
            return None
        return payload


def _write(key: str, payload: str) -> None:
    if get_client():
        cache_set(key, payload, ttl=settings.semantic_cache_ttl_seconds)
        return
    with _lock:
        _local[key] = (
            time.time() + settings.semantic_cache_ttl_seconds,
            payload,
        )
        # 简单的全局容量上限，防止进程内缓存无限增长
        if len(_local) > 500:
            oldest = sorted(_local.items(), key=lambda kv: kv[1][0])[:100]
            for old_key, _ in oldest:
                _local.pop(old_key, None)


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    if va.shape != vb.shape:
        return 0.0
    na = float(np.linalg.norm(va)) or 1.0
    nb = float(np.linalg.norm(vb)) or 1.0
    return float(va @ vb / (na * nb))


def lookup(query: str, query_vector: list[float], tenant_id: int | None,
           effective_at: datetime | None, strategy: str
           ) -> tuple[list[dict], float] | None:
    """返回 (缓存的检索结果, 相似度)；未命中或低于阈值返回 None"""
    if not settings.semantic_cache_enabled:
        return None
    raw = _read(_bucket_key(tenant_id, effective_at, strategy))
    if not raw:
        return None
    try:
        entries = json.loads(raw).get("entries", [])
    except Exception:
        return None

    best_score = 0.0
    best_hits = None
    query_intent = set(intent_keywords(query))
    for entry in entries:
        score = _cosine(query_vector, entry.get("v") or [])
        if score < settings.semantic_cache_threshold:
            continue
        entry_intent = set(entry.get("intent") or [])
        # 意图一致性校验：必须共享业务词；双方都没有业务词时要求近乎同句，
        # 避免「退货政策」命中「价保政策」这类高相似但答非所问的缓存。
        if query_intent and entry_intent:
            if not (query_intent & entry_intent):
                continue
        elif query_intent or entry_intent:
            continue
        elif score < 0.93:
            continue
        if score > best_score:
            best_score = score
            best_hits = entry.get("hits")
    if best_hits is None or best_score < settings.semantic_cache_threshold:
        return None
    return best_hits, round(best_score, 4)


def store(query: str, query_vector: list[float], hits: list[dict],
          tenant_id: int | None, effective_at: datetime | None,
          strategy: str) -> None:
    """写入语义缓存；空结果不缓存，避免一次检索失败长期粘住"""
    if not settings.semantic_cache_enabled or not hits:
        return
    key = _bucket_key(tenant_id, effective_at, strategy)
    raw = _read(key)
    try:
        entries = json.loads(raw).get("entries", []) if raw else []
    except Exception:
        entries = []
    entries.append({
        "q": query,
        "v": query_vector,
        "intent": intent_keywords(query),
        "hits": hits,
        "ts": time.time(),
    })
    entries = entries[-settings.semantic_cache_max_entries:]
    _write(key, json.dumps({"entries": entries}, ensure_ascii=False))


def clear_local() -> None:
    """清空进程内缓存（测试/评测用）"""
    with _lock:
        _local.clear()
