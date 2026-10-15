"""检索与 RAG 质量测试：BM25 / RRF 融合 / rerank 策略 / 混合开关 / 评测指标

外部依赖全部打桩（mock 向量 + mock reranker），不联网、不依赖 Milvus 与 BGE。
"""
import pytest

from app.core.config import settings
from app.rag import bm25, embedding, fusion, reranker, retriever, vector_store


class _Entity:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key):
        return self._data.get(key)


class _Hit:
    def __init__(self, score: float, chunk: dict):
        self.score = score
        self.entity = _Entity(chunk)


class _FakeCollection:
    """返回预设命中列表的伪向量集合：列表顺序即向量召回排名"""

    def __init__(self, hits: list[dict]):
        self._hits = hits
        self.search_kwargs = None

    def load(self):
        pass

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        return [[_Hit(0.9 - i * 0.1, h) for i, h in enumerate(self._hits)]]


def _chunk(doc_id: int, text: str = "", chunk_index: int = 0) -> dict:
    return {"doc_id": doc_id, "chunk_index": chunk_index, "text": text or f"文档{doc_id}片段"}


def _install(monkeypatch, vector_hits, corpus=(), strategy="none", hybrid=False, rerank=None):
    """统一打桩检索链路的各外部依赖，返回伪向量集合（便于断言入参）"""
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled", hybrid)
    monkeypatch.setattr(settings, "rerank_strategy", strategy)
    monkeypatch.setattr(embedding, "embed", lambda texts: [[0.0] * 768 for _ in texts])

    collection = _FakeCollection(list(vector_hits))
    monkeypatch.setattr(vector_store, "init_collection", lambda: collection)
    monkeypatch.setattr(vector_store, "fetch_chunks", lambda tenant_id=None, limit=0: list(corpus))
    if rerank is not None:
        monkeypatch.setattr(reranker, "rerank", rerank)
    return collection


def test_bm25_orders_by_keyword_relevance():
    """BM25 通路：关键词命中的块排在前面，完全不相关的被丢弃"""
    # 语料至少 3 篇，命中词只出现在 1 篇，BM25 的 IDF 才为正值
    corpus = [
        {"doc_id": 1, "chunk_index": 0, "text": "退货政策：七天内可以无理由退货"},
        {"doc_id": 2, "chunk_index": 0, "text": "配送时效：四十八小时内发货"},
        {"doc_id": 3, "chunk_index": 0, "text": "会员积分：消费一元累计一积分"},
    ]
    hits = bm25.search("退货怎么申请", corpus, top_k=2)
    assert hits and hits[0]["doc_id"] == 1
    assert all(hit["score"] > 0 for hit in hits)


def test_rrf_fuses_rankings_and_dedupes():
    """RRF：多路排名融合去重，双路命中的条目分数最高"""
    first = [_chunk(1), _chunk(2)]
    second = [_chunk(2), _chunk(3)]
    merged = fusion.rrf([first, second], k=60)

    keys = [(item["doc_id"], item["chunk_index"]) for item in merged]
    assert len(keys) == len(set(keys)) == 3
    assert merged[0]["doc_id"] == 2  # 两路都靠前，融合分最高
    assert merged[0]["score"] > merged[1]["score"]


def test_hybrid_disabled_skips_bm25(monkeypatch):
    """关闭混合检索时回退纯向量召回，不构建 BM25 语料"""
    called = {"fetch": False}

    def _fetch(tenant_id=None, limit=0):
        called["fetch"] = True
        return []

    collection = _install(monkeypatch, [_chunk(2)], hybrid=False)
    monkeypatch.setattr(vector_store, "fetch_chunks", _fetch)

    results = retriever.search("退货怎么申请", top_k=3, tenant_id=None)
    assert [r["doc_id"] for r in results] == [2]
    assert called["fetch"] is False
    assert collection.search_kwargs["expr"] is None  # 未指定租户时不加过滤


def test_hybrid_enabled_recalls_keyword_only_doc(monkeypatch):
    """开启混合检索后，只在关键词通路命中的文档也能被召回"""
    corpus = [
        _chunk(1, "退货政策：七天内可以无理由退货"),
        _chunk(4, "配送时效：四十八小时内发货"),
        _chunk(5, "会员积分：消费一元累计一积分"),
    ]
    _install(monkeypatch, [_chunk(2)], corpus=corpus, hybrid=True)

    results = retriever.search("退货怎么申请", top_k=3, tenant_id=None)
    assert 1 in [r["doc_id"] for r in results]


def test_rerank_none_skips_reranker(monkeypatch):
    """rerank_strategy=none 时保留向量召回顺序，不调用精排模型"""
    called = {"n": 0}

    def _spy(query, passages):
        called["n"] += 1
        return list(reversed(list(enumerate(passages))))

    _install(monkeypatch, [_chunk(1), _chunk(2)], strategy="none", rerank=_spy)
    results = retriever.search("问题", top_k=2, tenant_id=None)

    assert [r["doc_id"] for r in results] == [1, 2]
    assert called["n"] == 0


def test_rerank_always_reorders_by_model(monkeypatch):
    """rerank_strategy=always 时按精排分数重排"""
    _install(
        monkeypatch,
        [_chunk(1), _chunk(2)],
        strategy="always",
        rerank=lambda query, passages: [(1, 0.9), (0, 0.1)],
    )
    results = retriever.search("问题", top_k=2, tenant_id=None)

    assert [r["doc_id"] for r in results] == [2, 1]


def test_eval_metrics_smoke():
    """评测脚本可跑通并给出合理指标（mock 模型，无网可复现）"""
    from evals.run_eval import evaluate

    report = evaluate(top_k=3)
    assert report["queries"] >= 1
    assert 0.0 <= report["hit_rate"] <= 1.0
    assert 0.0 <= report["mrr"] <= 1.0
    assert report["hit_rate"] >= 0.75  # 小语料下混合检索应能命中大部分问题
    assert len(report["details"]) == report["queries"]
