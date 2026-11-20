"""方向 D 离线评测：自适应路由 + 语义缓存

指标：
1. 路由准确率：规则路由 vs 人工标注的三档策略；
2. 成本收益：自适应路由的相对成本 vs「永远 hybrid + rerank」；
3. 语义缓存：同义改写的命中率，以及跨意图的误命中率。

运行：
    python -m evals.adaptive_eval
"""
import json
import os
from datetime import datetime

from app.core.config import settings
from app.rag import router, semantic_cache

DATASET_PATH = os.path.join(os.path.dirname(__file__), "adaptive_dataset.json")
BASE_COST = router.STRATEGY_COST["hybrid_rerank"]


def _load() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def evaluate_routing(cases: list[dict]) -> dict:
    settings.adaptive_retrieval_enabled = True
    settings.retrieval_force_strategy = ""

    correct = 0
    adaptive_cost = 0
    confusion: dict[str, int] = {}
    mistakes = []
    for case in cases:
        decision = router.classify_query(
            case["query"], has_order=bool(case.get("has_order"))
        )
        expected = case["expected"]
        confusion[f"{expected} -> {decision.strategy}"] = (
            confusion.get(f"{expected} -> {decision.strategy}", 0) + 1
        )
        correct += int(decision.strategy == expected)
        adaptive_cost += decision.cost
        if decision.strategy != expected:
            mistakes.append({
                "query": case["query"],
                "expected": expected,
                "got": decision.strategy,
                "reason": decision.reason,
            })

    total = len(cases)
    baseline_cost = total * BASE_COST
    return {
        "cases": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "confusion": confusion,
        "mistakes": mistakes,
        "cost_units": {
            "adaptive": adaptive_cost,
            "always_hybrid_rerank": baseline_cost,
            "saving_rate": round(1 - adaptive_cost / baseline_cost, 4)
            if baseline_cost else 0.0,
        },
    }


def evaluate_semantic_cache(groups: list[list[str]],
                            cross_intent: list[str]) -> dict:
    from app.rag import retriever

    settings.semantic_cache_enabled = True
    settings.semantic_cache_threshold = 0.76
    # 评测不依赖 Redis：强制走进程内缓存
    semantic_cache.get_client = lambda: None
    semantic_cache.clear_local()

    at = datetime.now()
    tenant_id = 9999
    vectors = []
    for index, group in enumerate(groups):
        group_vectors = [retriever._query_vector(query) for query in group]
        vectors.append(group_vectors)
        semantic_cache.store(
            group[0], group_vectors[0], [{"doc_id": index + 1}],
            tenant_id, at, "vector",
        )

    hit = 0
    cases = 0
    for index, group in enumerate(groups):
        for query, vector in zip(group[1:], vectors[index][1:]):
            cases += 1
            result = semantic_cache.lookup(
                query, vector, tenant_id, at, "vector"
            )
            hit += int(result is not None)

    false_hits = 0
    for query in cross_intent:
        vector = retriever._query_vector(query)
        result = semantic_cache.lookup(
            query, vector, tenant_id, at, "vector"
        )
        false_hits += int(result is not None)

    return {
        "paraphrase_cases": cases,
        "hit_rate": round(hit / cases, 4) if cases else 0.0,
        "cross_intent_cases": len(cross_intent),
        "false_hit_rate": round(false_hits / len(cross_intent), 4)
        if cross_intent else 0.0,
        "threshold": settings.semantic_cache_threshold,
    }


def evaluate() -> dict:
    data = _load()
    return {
        "routing": evaluate_routing(data["routing_cases"]),
        "semantic_cache": evaluate_semantic_cache(
            data["cache_groups"],
            data.get("cache_cross_intent", []),
        ),
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
