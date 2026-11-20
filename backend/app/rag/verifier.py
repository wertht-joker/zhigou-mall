"""可信回答守卫：claim 分解、证据支撑校验与低置信判定（方向 B）

【解决什么问题】
现有引用溯源只是把召回 chunk 附在答案后面，并没有回答：
1. 这条 chunk 真的支持答案里的这句话吗？
2. 答案里有没有 chunk 根本没提到的内容（幻觉）？
3. 证据不足时，系统是硬答还是提示转人工？

本模块把答案拆成句子级 claim，逐句在引用证据中查找支撑，产出：
- 每个 claim 的 verdict（supported / partial / unsupported）与置信度；
- 每条引用的 verdict（它是否真的支撑了某句答案）；
- 聚合指标：faithfulness（句子忠实度）、hallucination_rate。

【实现取舍】
MVP 不引入额外 NLI 模型依赖（答辩环境可能无 GPU / 无外网），
用「中文分词词覆盖 + 字符 bigram 覆盖」作为轻量语义代理：
业务实体（签收、退货、原路退回、7天）同时出现在 claim 与证据中才计分。
接口是纯函数，后续可把 verify_claim 内部替换为 bge-reranker / NLI / LLM judge，
调用方无需改动。MVP 只做校验与提示，不改写答案。
"""
import re

import jieba

# 虚词 / 口语词不参与覆盖率计算，避免「可以」「怎么」这类词虚抬分数
_STOPWORDS = {
    "一个", "一些", "一下", "我们", "你们", "他们", "以及", "但是", "因为",
    "所以", "如果", "已经", "这个", "那个", "这些", "那些", "什么", "怎么",
    "如何", "多少", "是否", "可以", "可能", "需要", "进行", "还是", "或者",
    "而且", "并且", "然后", "这样", "那样", "的话", "目前", "相关", "内容",
    "情况", "问题", "请问", "您好", "好的", "谢谢", "感谢", "麻烦", "一下",
}

# 答案句级切分：中文句号/问号/叹号/分号/换行都视为 claim 边界
_CLAIM_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
# 超过该长度的句子再按逗号切分，避免一个 claim 塞进多个事实
_LONG_SENTENCE = 80
_MIN_CLAIM_LEN = 4

# 客套 / 拒答话术不是事实性 claim，避免把「未找到相关答案」误判为幻觉。
# 前缀类覆盖整句客套（如「如果您方便，也可以告诉我订单号」），
# 句中类只放强拒答短语，避免误伤「退货后请联系客服」这类有事实内容的句子。
_NON_FACTUAL_PREFIXES = (
    "未找到", "没有找到", "抱歉", "对不起", "您好", "请问", "感谢",
    "建议您", "建议联系", "请联系", "如果您", "您可以", "请稍后", "我先帮",
    "需要我", "要不要", "是否需要", "如需", "如您需要",
)
_NON_FACTUAL_ANYWHERE = (
    "知识库暂时查询不到", "知识库中未", "未检索到", "无法确认", "无法回答",
    "无法提供", "暂未收录", "联系客服",
)

_CHAR_RUN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
_ALNUM_RE = re.compile(r"[a-z0-9]+(?:[.%-][a-z0-9]+)*")
_HAS_CONTENT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def _normalize(text: str) -> str:
    """统一小写并去掉 markdown 修饰符，保证词面比较稳定"""
    return (text or "").lower().replace("**", "").replace("`", "")


def content_tokens(text: str) -> list[str]:
    """提取参与覆盖率计算的内容词（去虚词、去纯标点、去重复）"""
    normalized = _normalize(text)
    tokens: list[str] = []
    for word in jieba.cut(normalized):
        word = word.strip()
        if len(word) < 2 or word in _STOPWORDS:
            continue
        if not _HAS_CONTENT_RE.search(word):
            continue
        if word.isdigit():
            # 纯数字信息量低（"7"），交给字符 bigram 捕获「7天」「48小时」
            continue
        tokens.append(word)
    # 订单号、型号等字母数字串常被分词切开，单独补一遍
    tokens.extend(m for m in _ALNUM_RE.findall(normalized) if len(m) >= 2)
    return list(dict.fromkeys(tokens))


def char_bigrams(text: str) -> set[str]:
    """字符二元组：对中文分词误差不敏感，能兜住「7天」「原路退回」等短语"""
    result: set[str] = set()
    for run in _CHAR_RUN_RE.findall(_normalize(text)):
        for left, right in zip(run, run[1:]):
            result.add(left + right)
    return result


def coverage(claim: str, evidence: str) -> float:
    """claim 被 evidence 覆盖的程度（0-1）

    词覆盖占 0.6（业务实体是否出现），字符 bigram 占 0.4（短语级顺序信息，
    缓解「几天」vs「7天」这类分词边界差异）。
    """
    claim_words = content_tokens(claim)
    evidence_text = _normalize(evidence)
    word_cov = (
        sum(1 for word in claim_words if word in evidence_text) / len(claim_words)
        if claim_words else 0.0
    )

    claim_bigrams = char_bigrams(claim)
    evidence_bigrams = char_bigrams(evidence)
    bigram_cov = (
        len(claim_bigrams & evidence_bigrams) / len(claim_bigrams)
        if claim_bigrams else 0.0
    )

    if not claim_words and not claim_bigrams:
        return 0.0
    return round(0.6 * word_cov + 0.4 * bigram_cov, 4)


def _clean_claim(text: str) -> str:
    """去掉列表符号 / 序号，保留句子正文"""
    text = re.sub(r"^\s*(?:[-*•·]|\d+[.、)])\s*", "", text)
    return text.strip(" \t`*_")


def _is_non_factual(claim: str) -> bool:
    """客套 / 拒答句不计入事实性 claim"""
    if any(claim.startswith(prefix) for prefix in _NON_FACTUAL_PREFIXES):
        return True
    return any(marker in claim for marker in _NON_FACTUAL_ANYWHERE)


def decompose_claims(answer: str, max_claims: int | None = None) -> list[str]:
    """把答案拆成原子 claim（句子级；超长句再按逗号切分）"""
    claims: list[str] = []
    for sentence in _CLAIM_SPLIT_RE.split(_normalize(answer)):
        sentence = _clean_claim(sentence)
        if not sentence:
            continue
        pieces = [sentence]
        if len(sentence) > _LONG_SENTENCE:
            pieces = [_clean_claim(piece) for piece in re.split(r"[，,]", sentence)]
        for piece in pieces:
            # 以冒号结尾的是小标题（如「支付渠道到账：」），不是事实性陈述
            if piece.endswith(("：", ":")):
                continue
            if len(piece) < _MIN_CLAIM_LEN or _is_non_factual(piece):
                continue
            claims.append(piece)
            if max_claims and len(claims) >= max_claims:
                return claims
    return claims


def verify_claim(claim: str, sources: list[dict],
                 supported_threshold: float = 0.6,
                 partial_threshold: float = 0.35) -> dict:
    """为单条 claim 找最匹配的证据，并给出支撑等级

    verdict 三档：
    - supported：核心词与短语基本都能在证据中找到；
    - partial：只覆盖一部分，需要提示用户核对；
    - unsupported：证据中没有支撑（按幻觉风险处理）。
    """
    if not sources:
        return {
            "text": claim,
            "verdict": "unsupported",
            "confidence": 0.0,
            "source": None,
        }

    best_source = None
    best_score = -1.0
    for source in sources:
        score = coverage(claim, source.get("text") or "")
        if score > best_score:
            best_source, best_score = source, score

    if best_score >= supported_threshold:
        verdict = "supported"
    elif best_score >= partial_threshold:
        verdict = "partial"
    else:
        verdict = "unsupported"

    return {
        "text": claim,
        "verdict": verdict,
        "confidence": round(best_score, 4),
        "source": {
            "doc_id": best_source.get("doc_id"),
            "chunk_index": best_source.get("chunk_index"),
            "doc_name": best_source.get("doc_name"),
        },
    }


_VERDICT_PRIORITY = {"supported": 0, "partial": 1, "unsupported": 2}


def _merge_verdicts(verdicts: list[str]) -> str:
    """同一引用支撑多句时，取最强的一档（支撑过一句就算 supported）"""
    return min(verdicts, key=lambda v: _VERDICT_PRIORITY.get(v, 3))


def verify_answer(answer: str, sources: list[dict],
                  max_claims: int | None = None,
                  threshold: float = 0.8) -> dict:
    """校验整条答案，返回逐句 verdict、引用 verdict 与聚合指标"""
    claims = decompose_claims(answer, max_claims)
    verdicts = [verify_claim(claim, sources) for claim in claims]

    total = len(verdicts)
    supported = sum(1 for item in verdicts if item["verdict"] == "supported")
    partial = sum(1 for item in verdicts if item["verdict"] == "partial")
    unsupported = sum(1 for item in verdicts if item["verdict"] == "unsupported")
    # total=0（纯客套/拒答）不视为低置信，避免对「未找到相关答案」再做处罚
    faithfulness = round(supported / total, 4) if total else 1.0
    hallucination_rate = round(unsupported / total, 4) if total else 0.0

    # 汇总每条引用被哪些 claim 命中
    stats: dict[tuple, dict] = {}
    for item in verdicts:
        source = item.get("source")
        if not source:
            continue
        key = (source["doc_id"], source["chunk_index"])
        stat = stats.setdefault(key, {"verdicts": [], "confidence": 0.0, "claims": 0})
        stat["verdicts"].append(item["verdict"])
        stat["confidence"] = max(stat["confidence"], item["confidence"])
        stat["claims"] += 1

    source_reports = []
    for source in sources:
        key = (source.get("doc_id"), source.get("chunk_index"))
        stat = stats.get(key)
        if stat:
            verdict = _merge_verdicts(stat["verdicts"])
            confidence = stat["confidence"]
            claims_count = stat["claims"]
        else:
            verdict = "unused"
            confidence = 0.0
            claims_count = 0
        source_reports.append({
            "doc_id": source.get("doc_id"),
            "chunk_index": source.get("chunk_index"),
            "doc_name": source.get("doc_name"),
            "verdict": verdict,
            "confidence": round(confidence, 4),
            "claims": claims_count,
        })

    return {
        "claims": verdicts,
        "sources": source_reports,
        "total": total,
        "supported": supported,
        "partial": partial,
        "unsupported": unsupported,
        "faithfulness": faithfulness,
        "hallucination_rate": hallucination_rate,
        # 低于阈值才提示；partial 不单独触发，避免过度打扰
        "low_confidence": total > 0 and faithfulness < threshold,
    }


def should_refuse(sources: list[dict], sufficiency: dict | None = None) -> bool:
    """是否应给出「证据不足 / 转人工」提示

    证据为空，或生成前门控判定为 insufficient 时，上层应提示拒答/转人工。
    MVP 不自动改写答案，只把结论透传给前端展示。
    """
    return (not sources) or (sufficiency or {}).get("level") == "insufficient"
