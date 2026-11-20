"""方向 D：自适应检索路由 + 语义缓存测试

覆盖：三档路由规则、强制策略/开关回退、按策略选择检索链路、
语义缓存近邻命中与租户隔离。
"""
from datetime import datetime

from app.core.config import settings
from app.rag import retriever, router, semantic_cache


def _hit(doc_id: int, score: float = 0.9) -> dict:
    return {
        "text": f"doc{doc_id}",
        "doc_id": doc_id,
        "chunk_index": 0,
        "score": score,
        "doc_version": 1,
        "policy_key": "",
        "effective_from": 0,
        "effective_to": 0,
    }


# ===== 路由规则 =====

def test_router_three_tiers(monkeypatch):
    monkeypatch.setattr(settings, "adaptive_retrieval_enabled", True)
    monkeypatch.setattr(settings, "retrieval_force_strategy", "")

    assert router.classify_query("你好").strategy == "none"
    assert router.classify_query("今天天气怎么样").strategy == "none"
    assert router.classify_query("退货政策是几天").strategy == "vector"
    assert router.classify_query("会员积分怎么算").strategy == "vector"
    assert router.classify_query("退货需要什么条件").strategy == "hybrid_rerank"
    assert router.classify_query("对比一下退货和换货的区别").strategy == "hybrid_rerank"
    assert router.classify_query(
        "我的订单 ZG2026111100031 能退吗"
    ).strategy == "hybrid_rerank"


def test_router_force_strategy_and_switch(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_force_strategy", "vector")
    assert router.classify_query("对比退货和换货的区别").strategy == "vector"

    monkeypatch.setattr(settings, "retrieval_force_strategy", "")
    monkeypatch.setattr(settings, "adaptive_retrieval_enabled", False)
    assert router.classify_query("你好").strategy == "auto"


# ===== 检索策略 =====

def test_vector_strategy_skips_bm25(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(retriever, "_query_vector", lambda query: [1.0, 0.0])
    monkeypatch.setattr(
        retriever, "_vector_hits", lambda *args, **kwargs: [_hit(1)]
    )
    calls = {"bm25": 0}

    def fake_bm25(*args, **kwargs):
        calls["bm25"] += 1
        return [_hit(2, 0.1)]

    monkeypatch.setattr(retriever, "_bm25_hits", fake_bm25)

    hits, meta = retriever.search_with_meta(
        "退货政策是几天", tenant_id=1, strategy="vector"
    )

    assert meta["strategy"] == "vector"
    assert meta["cache"] == "miss"
    assert [hit["doc_id"] for hit in hits] == [1]
    assert calls["bm25"] == 0


def test_hybrid_strategy_uses_rrf(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled", True)
    monkeypatch.setattr(retriever, "_query_vector", lambda query: [1.0, 0.0])
    monkeypatch.setattr(
        retriever, "_vector_hits", lambda *args, **kwargs: [_hit(1)]
    )
    monkeypatch.setattr(
        retriever, "_bm25_hits", lambda *args, **kwargs: [_hit(2, 0.1)]
    )

    hits, meta = retriever.search_with_meta(
        "退货政策是几天", tenant_id=1, strategy="hybrid"
    )

    assert meta["strategy"] == "hybrid"
    assert {hit["doc_id"] for hit in hits} == {1, 2}


def test_hybrid_rerank_forces_rerank(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled", True)
    monkeypatch.setattr(settings, "rerank_strategy", "conditional")
    monkeypatch.setattr(settings, "rerank_min_candidates", 8)
    monkeypatch.setattr(retriever, "_query_vector", lambda query: [1.0, 0.0])
    monkeypatch.setattr(
        retriever, "_vector_hits", lambda *args, **kwargs: [_hit(1)]
    )
    monkeypatch.setattr(
        retriever, "_bm25_hits", lambda *args, **kwargs: [_hit(2, 0.1)]
    )
    monkeypatch.setattr(
        retriever.reranker, "rerank", lambda query, texts: [(1, 0.99), (0, 0.5)]
    )

    hits, meta = retriever.search_with_meta(
        "对比退货和换货的区别", tenant_id=1, strategy="hybrid_rerank"
    )

    assert meta["strategy"] == "hybrid_rerank"
    assert hits[0]["doc_id"] == 2


def test_none_strategy_skips_retrieval(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    calls = {"embed": 0}

    def fake_embed(query):
        calls["embed"] += 1
        return [1.0, 0.0]

    monkeypatch.setattr(retriever, "_query_vector", fake_embed)

    hits, meta = retriever.search_with_meta("你好", tenant_id=1, strategy="none")

    assert hits == []
    assert meta["cache"] == "off"
    assert calls["embed"] == 0


# ===== 语义缓存 =====

def test_semantic_cache_hits_paraphrase_and_isolates_tenant(monkeypatch):
    semantic_cache.clear_local()
    monkeypatch.setattr(semantic_cache, "get_client", lambda: None)
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", True)
    monkeypatch.setattr(settings, "semantic_cache_threshold", 0.9)

    vectors = {
        "退货政策是几天": [1.0, 0.0],
        "几天内可以退货": [0.98, 0.05],
        "物流一般几天到": [0.0, 1.0],
    }
    monkeypatch.setattr(
        retriever, "_query_vector", lambda query: vectors.get(query, [0.0, 1.0])
    )
    calls = {"vector": 0}

    def fake_vector(*args, **kwargs):
        calls["vector"] += 1
        return [_hit(1)]

    monkeypatch.setattr(retriever, "_vector_hits", fake_vector)
    monkeypatch.setattr(retriever, "_bm25_hits", lambda *args, **kwargs: [])

    at = datetime(2026, 11, 18)
    _, first = retriever.search_with_meta(
        "退货政策是几天", tenant_id=1, effective_at=at, strategy="vector"
    )
    hits, second = retriever.search_with_meta(
        "几天内可以退货", tenant_id=1, effective_at=at, strategy="vector"
    )

    assert first["cache"] == "miss"
    assert second["cache"] == "semantic"
    assert second["similarity"] >= 0.9
    assert [hit["doc_id"] for hit in hits] == [1]
    assert calls["vector"] == 1

    # 其他租户不能复用该商家的缓存
    _, other_tenant = retriever.search_with_meta(
        "几天内可以退货", tenant_id=2, effective_at=at, strategy="vector"
    )
    assert other_tenant["cache"] == "miss"
    assert calls["vector"] == 2


def test_semantic_cache_rejects_unrelated_query(monkeypatch):
    semantic_cache.clear_local()
    monkeypatch.setattr(semantic_cache, "get_client", lambda: None)
    monkeypatch.setattr(settings, "semantic_cache_enabled", True)
    monkeypatch.setattr(settings, "semantic_cache_threshold", 0.85)

    at = datetime(2026, 11, 18)
    semantic_cache.store(
        "退货政策是几天", [1.0, 0.0], [_hit(1)], 1, at, "vector"
    )

    assert semantic_cache.lookup(
        "物流一般几天到", [0.0, 1.0], 1, at, "vector"
    ) is None


def test_semantic_cache_rejects_same_template_different_intent(monkeypatch):
    """高相似但业务意图不同（退货 vs 价保）必须拒绝，防止答非所问"""
    semantic_cache.clear_local()
    monkeypatch.setattr(semantic_cache, "get_client", lambda: None)
    monkeypatch.setattr(settings, "semantic_cache_enabled", True)
    monkeypatch.setattr(settings, "semantic_cache_threshold", 0.85)

    at = datetime(2026, 11, 18)
    semantic_cache.store(
        "退货政策是几天", [1.0, 0.0], [_hit(1)], 1, at, "vector"
    )

    assert semantic_cache.lookup(
        "价保政策是几天", [0.99, 0.1], 1, at, "vector"
    ) is None
