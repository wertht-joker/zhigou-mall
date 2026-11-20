"""检索充分性门控：生成前判断 top-k 证据是否足以回答问题

规则通道（MVP）：问题关键词在证据中的覆盖率
→ sufficient / partial / insufficient。

【为什么不用向量分数做阈值】
RRF 融合分（约 0.03）与 rerank 分（0-1）语义不同，同一个阈值不可通用
（方案技术债 #12）。词面覆盖虽粗，但可解释、可复现、无额外模型依赖；
门控结论会作为提示写回工具结果，让模型在生成前就知道「证据只够答一部分」。
后续可增加 LLM few-shot 复核通道，接口保持不变。
"""
from app.core.config import settings
from app.rag.verifier import coverage


def judge_sufficiency(question: str, hits: list[dict],
                      threshold: float | None = None) -> dict:
    """判断检索结果是否足以回答 question

    - sufficient：问题核心信息基本都能在证据中找到；
    - partial：只覆盖一部分，可回答但需提示核对；
    - insufficient：相关性过低或没有命中，应拒答/转人工。
    """
    threshold = settings.sufficiency_threshold if threshold is None else threshold
    hit_count = len(hits or [])
    if hit_count == 0:
        return {
            "level": "insufficient",
            "score": 0.0,
            "hit_count": 0,
            "threshold": threshold,
            "reason": "知识库未检索到相关内容",
        }

    evidence = "\n".join((hit.get("text") or "") for hit in hits)
    score = coverage(question, evidence)
    if score >= threshold:
        level, reason = "sufficient", "检索结果覆盖了问题的核心信息"
    elif score >= threshold * 0.5:
        level, reason = "partial", "检索结果只覆盖了问题的一部分信息"
    else:
        level, reason = "insufficient", "检索结果与问题相关性过低"

    return {
        "level": level,
        "score": round(score, 4),
        "hit_count": hit_count,
        "threshold": threshold,
        "reason": reason,
    }
