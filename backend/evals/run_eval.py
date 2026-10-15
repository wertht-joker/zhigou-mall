"""检索质量评测脚本：hit rate / MRR / recall@k

用本地小语料 + mock 向量 / mock reranker 跑完整的「向量召回 + BM25 → RRF → rerank」
链路，因此在 CI 与无网环境下也能复现，不依赖 Milvus / BGE 真实模型。

用法：在 backend/ 目录下执行
    python -m evals.run_eval
真实模型评测只需把 mock 换成 embedding / reranker 的真实实现即可。
"""
import json
import math
import zlib
from pathlib import Path

from app.core.config import settings
from app.rag import bm25, embedding, reranker, retriever, vector_store

DATASET_PATH = Path(__file__).with_name("dataset.json")
# mock 向量维度（与真实 768 维无关，只要能稳定区分语义即可）
_HASH_DIM = 256


def _hash_vector(text: str) -> list[float]:
    """hashing trick：把分词结果散列到固定维度，得到稳定可复现的 mock 向量"""
    vec = [0.0] * _HASH_DIM
    for token in bm25.tokenize(text):
        vec[zlib.crc32(token.encode("utf-8")) % _HASH_DIM] += 1.0
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


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
    """用余弦相似度模拟 Milvus 检索（评测语料单一，忽略 expr 过滤）"""

    def __init__(self, chunks: list[dict]):
        self._chunks = chunks
        self._vectors = [_hash_vector(c["text"]) for c in chunks]

    def load(self):
        pass

    def search(self, data, anns_field, param, limit, output_fields, expr=None):
        query = data[0]
        scored = sorted(
            zip(self._vectors, self._chunks),
            key=lambda pair: _cosine(query, pair[0]),
            reverse=True,
        )
        return [[_Hit(_cosine(query, vec), chunk) for vec, chunk in scored[:limit]]]


def _mock_rerank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    """mock 精排：按 query 与 passage 的分词重叠度打分（词重叠越多越相关）"""
    query_tokens = set(bm25.tokenize(query))
    scored = [
        (idx, float(len(query_tokens & set(bm25.tokenize(p)))))
        for idx, p in enumerate(passages)
    ]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def _first_relevant_rank(doc_ids: list[int], relevant: set[int]) -> int | None:
    for rank, doc_id in enumerate(doc_ids, start=1):
        if doc_id in relevant:
            return rank
    return None


def evaluate(top_k: int = 3) -> dict:
    """跑一遍评测集，返回汇总指标与逐条明细"""
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    corpus = dataset["corpus"]
    queries = dataset["queries"]

    origin = {
        "embed": embedding.embed,
        "rerank": reranker.rerank,
        "init_collection": vector_store.init_collection,
        "fetch_chunks": vector_store.fetch_chunks,
        "cache_enabled": settings.retrieval_cache_enabled,
    }
    collection = _FakeCollection(corpus)
    embedding.embed = lambda texts: [_hash_vector(t) for t in texts]
    reranker.rerank = _mock_rerank
    vector_store.init_collection = lambda: collection
    vector_store.fetch_chunks = lambda tenant_id=None, limit=0: corpus
    settings.retrieval_cache_enabled = False  # 评测要求确定性，关掉缓存

    hit_count = 0
    mrr_sum = 0.0
    recall_sum = 0.0
    details = []
    try:
        for item in queries:
            results = retriever.search(item["query"], top_k=top_k, tenant_id=None)
            doc_ids = [hit["doc_id"] for hit in results]
            relevant = set(item["relevant_doc_ids"])
            rank = _first_relevant_rank(doc_ids, relevant)
            recall = len(set(doc_ids) & relevant) / len(relevant) if relevant else 0.0

            hit_count += 1 if rank else 0
            mrr_sum += 1.0 / rank if rank else 0.0
            recall_sum += recall
            details.append({
                "query": item["query"],
                "retrieved_doc_ids": doc_ids,
                "relevant_doc_ids": sorted(relevant),
                "hit": bool(rank),
                "first_relevant_rank": rank,
                "recall": round(recall, 4),
            })
    finally:
        # 恢复被替换的模块属性与配置，避免污染其他调用方
        embedding.embed = origin["embed"]
        reranker.rerank = origin["rerank"]
        vector_store.init_collection = origin["init_collection"]
        vector_store.fetch_chunks = origin["fetch_chunks"]
        settings.retrieval_cache_enabled = origin["cache_enabled"]

    total = len(queries)
    return {
        "queries": total,
        "top_k": top_k,
        "hit_rate": round(hit_count / total, 4) if total else 0.0,
        "mrr": round(mrr_sum / total, 4) if total else 0.0,
        "recall_at_k": round(recall_sum / total, 4) if total else 0.0,
        "details": details,
    }


def main() -> None:
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
