"""可信回答评测：充分性门控 + claim 级忠实度指标（方向 B / 阶段 1）

数据集是「问题 + 证据 + 代表性回答」的离线用例，不依赖 LLM / Milvus / BGE，
因此在 CI 与答辩现场都能复现。它评的是**守卫本身**：
- 门控：证据是否被判定为 sufficient / partial / insufficient；
- 校验：答案里的 claim 有多少能被证据支撑；
- 指标：Faithfulness、Hallucination Rate、Citation Precision/Recall、
  Refusal Accuracy、对抗样本检出率、P95 校验延迟。

用法（backend 目录）：
    python -m evals.faithfulness_eval
    python -m evals.faithfulness_eval --details
"""
import argparse
import json
import math
import statistics
import time
from pathlib import Path

from app.core.config import settings
from app.rag import sufficiency, verifier

DATASET_PATH = Path(__file__).with_name("faithfulness_dataset.json")

# 回答中出现这些话术，视为「明确拒答/要求转人工」
_REFUSAL_MARKERS = (
    "未找到", "没有找到", "无法确认", "无法回答", "暂未收录",
    "知识库暂", "联系人工", "转人工", "抱歉",
)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 3)


def _is_refusal(answer: str) -> bool:
    return any(marker in answer for marker in _REFUSAL_MARKERS)


def evaluate(include_details: bool = False) -> dict:
    """跑完整评测集，返回汇总指标（可选逐条明细）"""
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    corpus = {
        (item["doc_id"], item["chunk_index"]): item
        for item in data["corpus"]
    }
    cases = data["cases"]

    claim_total = 0
    supported_total = 0
    unsupported_total = 0
    used_citations = 0
    supported_citations = 0
    latencies: list[float] = []

    answerable_count = 0
    unanswerable_count = 0
    adversarial_count = 0
    gate_refusal_hits = 0
    gate_caution_hits = 0
    answer_refusal_hits = 0
    adversarial_hits = 0
    details = []

    for case in cases:
        keys = [(item[0], item[1]) for item in case.get("evidence_keys", [])]
        hits = [corpus[key] for key in keys if key in corpus]
        started = time.perf_counter()
        gate = sufficiency.judge_sufficiency(case["question"], hits)
        report = verifier.verify_answer(
            case["answer"],
            hits,
            max_claims=settings.verifier_max_claims,
            threshold=settings.faithfulness_threshold,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        answerable = bool(case.get("answerable"))
        adversarial = bool(case.get("adversarial"))
        if answerable:
            answerable_count += 1
            claim_total += report["total"]
            supported_total += report["supported"]
            unsupported_total += report["unsupported"]
            for source in report["sources"]:
                if source["verdict"] == "unused":
                    continue
                used_citations += 1
                if source["verdict"] == "supported":
                    supported_citations += 1
            if adversarial:
                adversarial_count += 1
                if report["low_confidence"]:
                    adversarial_hits += 1
        else:
            unanswerable_count += 1
            if gate["level"] == "insufficient":
                gate_refusal_hits += 1
            if gate["level"] in {"insufficient", "partial"}:
                gate_caution_hits += 1
            if _is_refusal(case["answer"]):
                answer_refusal_hits += 1

        if include_details:
            details.append({
                "id": case["id"],
                "question": case["question"],
                "answerable": answerable,
                "adversarial": adversarial,
                "gate": gate,
                "faithfulness": report["faithfulness"],
                "low_confidence": report["low_confidence"],
                "refusal_in_answer": _is_refusal(case["answer"]),
                "claims": report["claims"],
                "sources": report["sources"],
            })

    result = {
        "cases": len(cases),
        "answerable": answerable_count,
        "unanswerable": unanswerable_count,
        "adversarial": adversarial_count,
        "claims": claim_total,
        "supported_claims": supported_total,
        "unsupported_claims": unsupported_total,
        "faithfulness": _ratio(supported_total, claim_total),
        "hallucination_rate": _ratio(unsupported_total, claim_total),
        "citation_precision": _ratio(supported_citations, used_citations),
        "citation_recall": _ratio(supported_total, claim_total),
        "gate_refusal_accuracy": _ratio(gate_refusal_hits, unanswerable_count),
        "gate_caution_accuracy": _ratio(gate_caution_hits, unanswerable_count),
        "answer_refusal_accuracy": _ratio(answer_refusal_hits, unanswerable_count),
        "adversarial_detection_rate": _ratio(adversarial_hits, adversarial_count),
        "mean_latency_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": _p95(latencies),
    }
    if include_details:
        result["details"] = details
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="可信回答守卫离线评测")
    parser.add_argument("--details", action="store_true", help="输出逐条用例明细")
    args = parser.parse_args()
    print(json.dumps(evaluate(include_details=args.details), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
