"""方向 D：查询复杂度路由（Adaptive RAG 的规则版）

不是所有问题都值得「混合检索 + 精排 + 多轮工具」：
- none          闲聊 / 问候 / 身份问题，不检索；
- vector        单跳事实问题，只走向量召回（省一次 BM25 + 一次精排）；
- hybrid_rerank 多条件 / 政策 / 订单 / 对比问题，走完整混合检索 + 精排。

为什么先用规则而不是 LLM 分类：
1. 规则零成本、零延迟、可解释，适合作为高频链路的默认策略；
2. 不确定时一律回退 hybrid_rerank（保守策略），宁可多花算力也不漏召回；
3. 保留开关 RETRIEVAL_FORCE_STRATEGY，线上可一键回退固定链路。

后续若引入 LLM few-shot 路由，只需替换 classify_query 的实现，
上层 retriever / tools 无需改动。
"""
import re
from dataclasses import asdict, dataclass, field

from app.core.config import settings

# 订单号：ZG2026111100031
ORDER_RE = re.compile(r"[A-Za-z]{2}\d{8,}")

# 寒暄 / 身份类问题：短句且不含业务词时直接判定为闲聊
GREETING_RE = re.compile(
    r"^(你好|您好|hi|hello|嗨|在吗|在不在|谢谢|感谢|多谢|再见|拜拜|"
    r"你是谁|你叫什么|你能做什么|你会什么|介绍一下你自己|早上好|晚上好)"
    r"[\s！!。,.，?？~～]*$",
    re.IGNORECASE,
)

# 平台业务词：出现这些词才值得查知识库
DOMAIN_KEYWORDS = (
    "退货", "退款", "换货", "售后", "价保", "保价", "发货", "物流", "快递",
    "配送", "运费", "包邮", "发票", "会员", "积分", "优惠券", "支付", "付款",
    "订单", "商品", "保修", "维修", "取消", "地址", "尺码", "颜色", "库存",
    "预售", "客服", "规则", "政策", "账号", "密码", "登录", "注册", "评价",
    "七天", "15天", "无理由",
)

# 复杂问题信号：多条件、对比、流程、规则解释
# 注意：「政策」「规则」单独出现不代表复杂（如「退货政策是几天」是单跳事实），
# 只有和「对比/分别/条件/流程/有哪些」等组合时才升级链路。
COMPLEX_KEYWORDS = (
    "对比", "分别", "区别", "不同", "同时", "以及", "并且", "还有", "如果",
    "但是", "流程", "条件", "需要什么", "怎么办", "如何",
    "能不能", "可不可以", "是否", "有哪些", "为什么",
)

# 各策略的相对成本（用于评测与路由解释，不代表真实耗时）
STRATEGY_COST = {
    "none": 0,
    "vector": 1,
    "hybrid": 2,
    "hybrid_rerank": 3,
}


@dataclass(frozen=True)
class RouteDecision:
    """一次路由决策：策略 + 可解释原因 + 特征 + 成本估计"""

    strategy: str
    reason: str
    features: dict = field(default_factory=dict)

    @property
    def cost(self) -> int:
        return STRATEGY_COST.get(self.strategy, 3)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cost"] = self.cost
        return data


def _features(query: str, has_order: bool) -> dict:
    return {
        "length": len(query),
        "has_order": has_order,
        "is_greeting": bool(GREETING_RE.match(query)),
        "has_domain_keyword": any(k in query for k in DOMAIN_KEYWORDS),
        "has_complex_keyword": any(k in query for k in COMPLEX_KEYWORDS),
        "question_marks": query.count("?") + query.count("？"),
        "clauses": query.count("，") + query.count(",") + query.count("；"),
    }


# 语义缓存的意图词做同义词归一：
# 「物流/快递/配送/发货」视为同一意图，「退款/到账/退回」视为同一意图；
# 「退货」与「换货」政策不同，不能合并。
_INTENT_GROUPS = {
    "物流": ("物流", "快递", "配送", "发货", "送达"),
    "退款": ("退款", "到账", "退回", "退钱"),
    "退货": ("退货", "无理由退货"),
    "会员": ("会员",),
    "积分": ("积分",),
}


def intent_keywords(query: str) -> list[str]:
    """抽取问题里的业务意图（同义词归一，供语义缓存做一致性校验）"""
    text = query or ""
    return sorted({
        canonical
        for canonical, words in _INTENT_GROUPS.items()
        if any(word in text for word in words)
    })


def classify_query(query: str, has_order: bool = False) -> RouteDecision:
    """按问题复杂度选择检索策略（保守：不确定就走完整链路）"""
    text = (query or "").strip()
    features = _features(text, has_order)

    forced = (settings.retrieval_force_strategy or "").strip().lower()
    if forced in STRATEGY_COST:
        return RouteDecision(forced, f"配置强制策略：{forced}", features)

    if not settings.adaptive_retrieval_enabled:
        return RouteDecision("auto", "自适应路由已关闭，沿用固定链路", features)

    # 1. 带订单号：需要「订单时效 + 政策版本 + 精确条款」，必须完整链路
    if has_order or ORDER_RE.search(text):
        return RouteDecision(
            "hybrid_rerank", "包含订单号，需要按成交时间检索政策版本", features
        )

    # 2. 短寒暄 / 身份问题，且没有业务词：不检索
    if features["is_greeting"] and not features["has_domain_keyword"]:
        return RouteDecision("none", "寒暄或身份类问题，无需检索", features)

    # 3. 没有任何业务词，也不是复杂问题：按闲聊处理
    if (
        not features["has_domain_keyword"]
        and not features["has_complex_keyword"]
        and features["length"] <= 20
    ):
        return RouteDecision("none", "未包含平台业务词，按闲聊处理", features)

    # 4. 单跳事实：短、单一问句、无复杂信号 -> 只走向量
    if (
        features["length"] <= 24
        and features["clauses"] == 0
        and features["question_marks"] <= 1
        and not features["has_complex_keyword"]
    ):
        return RouteDecision(
            "vector", "单一事实问题，向量召回足够", features
        )

    # 5. 其余（多条件/对比/流程/政策解释）走完整链路，保证召回
    return RouteDecision(
        "hybrid_rerank", "多条件或政策解释问题，使用混合检索 + 精排", features
    )
