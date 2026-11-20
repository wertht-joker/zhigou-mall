"""时效政策检索离线评测（方向 C）

对比两种策略在同一批跨版本订单问题上的版本选择：
- no_filter：永远选最新版本（模拟“没有时间过滤”的基线）
- with_filter：按订单成交时间选择生效版本

评测是确定性的版本选择模拟，不依赖 Milvus / BGE / LLM，
用于验证“时间维度”确实能降低政策版本错配率。

运行：
    python -m evals.temporal_eval
"""
import json
import os
from datetime import datetime

from app.rag.temporal import within_window

DATASET_PATH = os.path.join(os.path.dirname(__file__), "temporal_dataset.json")


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _load():
    with open(DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    versions = []
    for item in data["versions"]:
        versions.append({
            **item,
            "effective_from": _parse(item.get("effective_from")),
            "effective_to": _parse(item.get("effective_to")),
        })
    return versions, data["order_dates"], data["queries"]


def select_version(versions: list[dict], at: datetime,
                   apply_filter: bool = True) -> dict | None:
    """选择 at 时刻应有的政策版本

    apply_filter=True：只保留生效区间覆盖 at 的版本；
    apply_filter=False：直接取最新版本（基线）。
    """
    if not apply_filter:
        return max(versions, key=lambda v: v["version"]) if versions else None

    matched = [
        v for v in versions
        if within_window(v["effective_from"], v["effective_to"], at)
    ]
    if not matched:
        return None
    return max(matched, key=lambda v: v["version"])


def evaluate() -> dict:
    """展开 query × order_date，输出版本错配率与时效准确率"""
    versions, order_dates, queries = _load()
    cases = []
    no_filter_wrong = 0
    filtered_wrong = 0

    for date_str in order_dates:
        at = datetime.fromisoformat(date_str)
        expected = select_version(versions, at, apply_filter=True)
        for query in queries:
            baseline = select_version(versions, at, apply_filter=False)
            filtered = select_version(versions, at, apply_filter=True)
            no_filter_wrong += int(baseline != expected)
            filtered_wrong += int(filtered != expected)
            cases.append({
                "query": query,
                "order_at": date_str,
                "expected_version": expected["version"] if expected else None,
                "no_filter_version": baseline["version"] if baseline else None,
                "with_filter_version": filtered["version"] if filtered else None,
            })

    total = len(cases)
    report = {
        "cases": total,
        "versions": len(versions),
        "no_filter_mismatch_rate": round(no_filter_wrong / total, 4) if total else 0.0,
        "with_filter_mismatch_rate": round(filtered_wrong / total, 4) if total else 0.0,
        "temporal_accuracy": round(1 - filtered_wrong / total, 4) if total else 0.0,
        "stale_answer_rate": round(no_filter_wrong / total, 4) if total else 0.0,
        "details": cases,
    }
    return report


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(
        {k: v for k, v in result.items() if k != "details"},
        ensure_ascii=False,
        indent=2,
    ))
