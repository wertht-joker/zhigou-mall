"""语义检索：混合召回（向量 + BM25）+ RRF 融合 + 可配置 Rerank（按租户隔离）

链路：向量召回 + BM25 关键词召回 → RRF 融合 → rerank 精排 → top_k
- hybrid_retrieval_enabled=false 时回退纯向量召回
- rerank_strategy=none 时跳过精排（或用 conditional 按候选数触发）
- retrieval_cache_enabled=true 时，查询向量与最终结果进 Redis 缓存
"""
import hashlib
import json

from app.core.config import settings
from app.core.redis import cache_get, cache_set
from app.rag import bm25, embedding, fusion, reranker, vector_store

# BGE 中文模型的 query 前缀，提升召回
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def _embedding_cache_key(text: str) -> str:
    return "emb:" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def _result_cache_key(query: str, top_k: int, tenant_id: int | None) -> str:
    raw = f"{tenant_id}|{top_k}|{settings.rerank_strategy}|{settings.hybrid_retrieval_enabled}|{query}"
    return "ret:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _query_vector(query: str) -> list[float]:
    """查询向量化（结果按文本哈希缓存到 Redis）"""
    text = QUERY_PREFIX + query
    if settings.retrieval_cache_enabled:
        cached = cache_get(_embedding_cache_key(text))
        if cached:
            return json.loads(cached)
    vector = embedding.embed([text])[0]
    if settings.retrieval_cache_enabled:
        cache_set(_embedding_cache_key(text), json.dumps(vector))
    return vector


def _vector_hits(query: str, tenant_id: int | None, limit: int) -> list[dict]:
    """向量召回：按租户分区过滤"""
    query_vector = _query_vector(query)
    collection = vector_store.init_collection()
    collection.load()
    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    expr = f"tenant_id == {int(tenant_id)}" if tenant_id is not None else None
    results = collection.search(
        data=[query_vector],
        anns_field="vector",
        param=search_params,
        limit=limit,
        output_fields=["text", "doc_id", "chunk_index"],
        expr=expr,
    )
    return [
        {
            "text": hit.entity.get("text"),
            "doc_id": hit.entity.get("doc_id"),
            "chunk_index": hit.entity.get("chunk_index"),
            "score": float(hit.score),
        }
        for hit in results[0]
    ]


def _bm25_hits(query: str, tenant_id: int | None) -> list[dict]:
    """BM25 关键词召回：语料限定在当前租户"""
    corpus = vector_store.fetch_chunks(tenant_id, settings.bm25_corpus_limit)
    return bm25.search(query, corpus, settings.bm25_top_k)


def _top_by_score(hits: list[dict], k: int) -> list[dict]:
    return sorted(hits, key=lambda h: h["score"], reverse=True)[:k]


def _apply_rerank(query: str, hits: list[dict], k: int) -> list[dict]:
    """按 rerank_strategy 决定是否精排"""
    strategy = (settings.rerank_strategy or "always").lower()
    if strategy == "none" or len(hits) < 2:
        return _top_by_score(hits, k)
    if strategy == "conditional" and len(hits) < settings.rerank_min_candidates:
        return _top_by_score(hits, k)
    try:
        ranked = reranker.rerank(query, [h["text"] for h in hits])
        top_hits = []
        for idx, score in ranked[:k]:
            hit = dict(hits[idx])
            hit["score"] = round(float(score), 4)
            top_hits.append(hit)
        return top_hits
    except Exception:
        # reranker 不可用则降级为召回结果
        return _top_by_score(hits, k)


def search(query: str, top_k: int | None = None,
           tenant_id: int | None = None) -> list[dict]:
    """检索与问题最相关的文档块（tenant_id 非空时按租户隔离）"""
    k = top_k or settings.top_k

    cache_key = _result_cache_key(query, k, tenant_id)
    if settings.retrieval_cache_enabled:
        cached = cache_get(cache_key)
        if cached:
            return json.loads(cached)

    vector_hits = _vector_hits(query, tenant_id, settings.retrieve_top_k)
    if settings.hybrid_retrieval_enabled:
        hits = fusion.rrf([vector_hits, _bm25_hits(query, tenant_id)], settings.rrf_k)
    else:
        hits = vector_hits

    if not hits:
        return []

    top_hits = _apply_rerank(query, hits, k)
    if settings.retrieval_cache_enabled:
        cache_set(cache_key, json.dumps(top_hits, ensure_ascii=False))
    return top_hits
