"""语义检索：混合召回（向量 + BM25）+ RRF 融合 + 可配置 Rerank（按租户隔离）

链路：向量召回 + BM25 关键词召回 → RRF 融合 → rerank 精排 → top_k
- hybrid_retrieval_enabled=false 时回退纯向量召回（演示对比/排障用）
- rerank_strategy=none 时跳过精排（或用 conditional 按候选数触发）
- retrieval_cache_enabled=true 时，查询向量与最终结果进 Redis 缓存

【为什么要混合检索】（面试高频）
  向量召回 = 语义相近（"怎么退货"能召到"退换货政策"），但对精确关键词
  （政策编号、商品型号）容易漏召；BM25 关键词通路互补；两路用 RRF 融合。
  中文分词 jieba + rank_bm25；BM25 语料每次从 Milvus 拉本租户 chunk（有上限），
  语料大了应换 Milvus sparse 向量 / ES 增量索引（README 改进项）。

【两层缓存设计】① 查询向量缓存：同一句话重复问省一次本地模型推理；
  ② 最终结果缓存：相同问题直接命中。缓存键 = 输入 + 检索策略参数
  （tenant_id / top_k / rerank 策略 / 混合开关）——策略一变旧键自然失配，
  避免"改了配置还吃到旧结果"的经典缓存坑。
"""
import hashlib
import json
import time
from datetime import datetime

from app.core.config import settings
from app.core.redis import cache_get, cache_set, get_kb_version
from app.rag import bm25, embedding, fusion, metrics, reranker, semantic_cache, vector_store
from app.rag.temporal import effective_expr

# BGE 中文模型的 query 前缀，提升召回
# （BGE 官方建议：检索任务给 query 加指令前缀，文档侧不加——只对 query 编码时使用）
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def _embedding_cache_key(text: str) -> str:
    return "emb:" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def _result_cache_key(query: str, top_k: int, tenant_id: int | None,
                      effective_at: datetime | None = None,
                      mode: str = "auto") -> str:
    # 缓存键必须带业务时间、知识库内容版本与检索策略：
    # 政策有新版本、文档更新或路由策略变化后，旧缓存自然失配。
    # 政策按天生效，缓存键用日期即可；避免 datetime.now() 的微秒导致缓存全失效
    at = effective_at.date().isoformat() if effective_at else "-"
    raw = (
        f"{tenant_id}|{top_k}|{mode}|{settings.rerank_strategy}|"
        f"{settings.hybrid_retrieval_enabled}|{get_kb_version()}|{at}|{query}"
    )
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


def _vector_hits(query: str, tenant_id: int | None, limit: int,
                 effective_at: datetime | None = None,
                 query_vector: list[float] | None = None) -> list[dict]:
    """向量召回：按租户分区 + 业务时间窗口过滤

    query_vector 可由调用方预先生成（语义缓存需要先算一次），避免重复推理。
    """
    query_vector = query_vector or _query_vector(query)
    collection = vector_store.init_collection()
    collection.load()
    # nprobe：IVF 索引每次探测的聚类簇数——越大召回越全、延迟越高（精度/延迟旋钮）
    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    # expr 同时表达空间（tenant）与时间（政策版本）两个维度的隔离；
    # 向量检索绝不能跨商家，也不能拿新政策回答老订单。
    expr_parts = []
    if tenant_id is not None:
        expr_parts.append(f"tenant_id == {int(tenant_id)}")
    time_expr = effective_expr(effective_at)
    if time_expr:
        expr_parts.append(time_expr)
    expr = " and ".join(expr_parts) or None
    results = collection.search(
        data=[query_vector],
        anns_field="vector",
        param=search_params,
        limit=limit,
        output_fields=[
            "text", "doc_id", "chunk_index", "doc_version",
            "policy_key", "effective_from", "effective_to",
        ],
        expr=expr,
    )
    return [
        {
            "text": hit.entity.get("text"),
            "doc_id": hit.entity.get("doc_id"),
            "chunk_index": hit.entity.get("chunk_index"),
            "doc_version": hit.entity.get("doc_version"),
            "policy_key": hit.entity.get("policy_key"),
            "effective_from": hit.entity.get("effective_from"),
            "effective_to": hit.entity.get("effective_to"),
            "score": float(hit.score),
        }
        for hit in results[0]
    ]


def _bm25_hits(query: str, tenant_id: int | None,
               effective_at: datetime | None = None) -> list[dict]:
    """BM25 关键词召回：语料限定在当前租户与业务时间窗口"""
    if effective_at is None:
        corpus = vector_store.fetch_chunks(tenant_id, settings.bm25_corpus_limit)
    else:
        corpus = vector_store.fetch_chunks(
            tenant_id, settings.bm25_corpus_limit, effective_at
        )
    return bm25.search(query, corpus, settings.bm25_top_k)


def _top_by_score(hits: list[dict], k: int) -> list[dict]:
    return sorted(hits, key=lambda h: h["score"], reverse=True)[:k]


def _apply_rerank(query: str, hits: list[dict], k: int,
                  force: bool = False) -> list[dict]:
    """按 rerank_strategy 决定是否精排

    force=True 时忽略 conditional 的候选数阈值（自适应路由已经判定需要精排），
    但全局 rerank_strategy=none 仍然生效，保留一键关闭能力的统一入口。
    """
    strategy = (settings.rerank_strategy or "always").lower()
    if strategy == "none" or len(hits) < 2:
        return _top_by_score(hits, k)
    if (
        not force
        and strategy == "conditional"
        and len(hits) < settings.rerank_min_candidates
    ):
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
        # reranker 不可用则降级为召回结果——精排是"锦上添花"，绝不能阻断问答主链路
        return _top_by_score(hits, k)


_VALID_MODES = {"none", "vector", "hybrid", "hybrid_rerank", "auto"}


def _resolve_mode(strategy: str | None) -> str:
    """把路由策略归一化；auto 保持原有「按配置组合链路」的语义"""
    mode = (strategy or "auto").strip().lower()
    if mode not in _VALID_MODES:
        mode = "auto"
    return mode


def search_with_meta(query: str, top_k: int | None = None,
                     tenant_id: int | None = None,
                     effective_at: datetime | None = None,
                     strategy: str | None = None,
                     allow_semantic_cache: bool = True
                     ) -> tuple[list[dict], dict]:
    """检索并返回观测元数据（策略 / 缓存命中 / 耗时）

    strategy=None/auto：沿用原有「混合 + 可配置精排」；
    none：不检索；vector：只走向量；hybrid：混合但不精排；
    hybrid_rerank：混合 + 强制精排（仍受全局 rerank_strategy=none 约束）。
    """
    start = time.perf_counter()
    k = top_k or settings.top_k
    mode = _resolve_mode(strategy)

    def _done(hits: list[dict], cache: str, similarity: float | None = None):
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        metrics.record(mode, cache, elapsed_ms, len(hits))
        meta = {
            "strategy": mode,
            "cache": cache,
            "elapsed_ms": elapsed_ms,
            "hits": len(hits),
        }
        if similarity is not None:
            meta["similarity"] = similarity
        return hits, meta

    if mode == "none":
        return _done([], "off")

    cache_key = _result_cache_key(query, k, tenant_id, effective_at, mode)
    if settings.retrieval_cache_enabled:
        cached = cache_get(cache_key)
        if cached:
            return _done(json.loads(cached), "exact")

    # 查询向量只算一次：语义缓存与向量召回共用
    query_vector = _query_vector(query)
    if allow_semantic_cache:
        semantic = semantic_cache.lookup(
            query, query_vector, tenant_id, effective_at, mode
        )
        if semantic:
            hits, similarity = semantic
            return _done(hits, "semantic", similarity)

    vector_hits = _vector_hits(
        query, tenant_id, settings.retrieve_top_k, effective_at, query_vector
    )
    if mode in ("auto", "hybrid", "hybrid_rerank") and settings.hybrid_retrieval_enabled:
        hits = fusion.rrf(
            [vector_hits, _bm25_hits(query, tenant_id, effective_at)],
            settings.rrf_k,
        )
    else:
        hits = vector_hits

    if not hits:
        return _done([], "miss")

    if mode in ("vector", "hybrid"):
        top_hits = _top_by_score(hits, k)
    elif mode == "auto":
        top_hits = _apply_rerank(query, hits, k)
    else:  # hybrid_rerank：路由已判定需要精排，忽略 conditional 阈值
        top_hits = _apply_rerank(query, hits, k, force=True)

    if settings.retrieval_cache_enabled:
        cache_set(cache_key, json.dumps(top_hits, ensure_ascii=False))
    if allow_semantic_cache:
        semantic_cache.store(
            query, query_vector, top_hits, tenant_id, effective_at, mode
        )
    return _done(top_hits, "miss")


def search(query: str, top_k: int | None = None,
           tenant_id: int | None = None,
           effective_at: datetime | None = None,
           strategy: str | None = None) -> list[dict]:
    """检索与问题最相关的文档块（兼容原调用方，只返回结果）

    tenant_id 非空时按租户隔离；effective_at 非空时只返回该业务时间点
    生效的政策版本（订单问题传订单成交时间，普通问题传当前时间）。
    """
    hits, _ = search_with_meta(
        query, top_k=top_k, tenant_id=tenant_id,
        effective_at=effective_at, strategy=strategy,
    )
    return hits
