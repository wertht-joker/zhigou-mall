"""AI 客服 Agent 工具定义与执行器

Agent 能自主决定调用哪些工具、以什么参数调用：
- search_knowledge_base：检索平台知识库（售后政策 / 物流说明 / FAQ 等）
- query_my_orders：查询当前顾客的订单（可按订单号精确查，缺省查最近订单）
- recommend_products：商品导购，按需求描述搜索在售商品

数据边界：知识库按租户（商家）隔离；订单只查当前登录用户自己的。

除给模型的文本结果外，工具还返回可选的结构化 payload（商品卡片 / 订单卡片），
随 SSE 推给前端渲染成富卡片，答案文本只负责总结说明。
"""
import json
import logging
import time
from datetime import datetime
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.rag import retriever, router, sufficiency
from app.rag.temporal import from_epoch
from app.repositories.address_repository import AddressRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.tenant_repository import TenantRepository
from app.services import aftersale_service

logger = logging.getLogger("app.tools")


class ToolResult(NamedTuple):
    """工具执行结果：text 给模型推理，payload 给前端渲染卡片

    meta 是只在内置链路流转的结构化信息（如知识库检索的充分性结论），
    不会直接推给前端；chat_service 用它生成 verify 事件。
    """

    text: str
    sources: list[dict]
    payload: dict | None = None
    meta: dict | None = None


# ===== 工具声明（OpenAI / DeepSeek function-calling 格式）=====

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "在平台知识库中检索资料。当用户询问售后政策、退换货流程、"
                "物流配送、支付方式、会员积分、账号问题等平台规则类问题时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "检索用的查询语句。必须是完整、独立、不含代词指代的问题，"
                            "例如用户问「那多久到账」，应改写为「退货退款多久到账」再检索。"
                        ),
                    },
                    "order_no": {
                        "type": "string",
                        "description": (
                            "可选。用户问「我这单能不能退/这笔订单适用什么政策」时，"
                            "传入从 query_my_orders 得到的订单号，系统会按订单成交时"
                            "生效的政策版本检索，而不是直接使用最新政策。"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_my_orders",
            "description": (
                "查询当前顾客自己的订单（状态、物流、明细）。"
                "当用户问「我买的到哪了」「我的订单什么状态」「帮我查订单」时调用；"
                "用户提供了订单号就按订单号精确查询，没提供就查最近的订单。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_no": {
                        "type": "string",
                        "description": "订单号（可选），例如 ZG2026101900031",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_products",
            "description": (
                "商品导购：根据用户描述的需求（品类、预算、用途、功能偏好）"
                "在在售商品中搜索并推荐。当用户表达购买意向或询问商品信息时调用，"
                "例如「有没有便宜点的降噪耳机」「两千预算买什么平板」。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "商品搜索关键词，从用户需求中提炼，例如「降噪耳机」「平板」「空气净化器」",
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "用户给出的预算上限（元，可选）",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_addresses",
            "description": (
                "查询当前顾客保存的收货地址簿（含地址 ID）。"
                "当用户要修改订单收货地址时，先调用本工具拿到地址 ID，再发起改址提案。"
                "地址 ID 只能取自本工具的返回结果，不要猜测。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_after_sales_action",
            "description": (
                "发起售后操作提案（不会立即执行，需要用户在确认卡片上点击确认才生效）。"
                "支持：cancel_order 取消待付款订单；create_refund_ticket 为已支付订单申请退款；"
                "change_address 修改未发货订单的收货地址。"
                "只有在用户明确要求对应操作时才调用；订单号必须来自 query_my_orders 的真实结果，"
                "地址 ID 必须来自 list_my_addresses 的真实结果。"
                "调用后必须提示用户点击确认卡片，绝不能声称操作已经完成。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "cancel_order",
                            "create_refund_ticket",
                            "change_address",
                        ],
                        "description": "要发起的售后操作类型",
                    },
                    "order_no": {
                        "type": "string",
                        "description": "订单号，例如 ZG2026101900031（必须来自订单查询结果）",
                    },
                    "reason": {
                        "type": "string",
                        "description": "退款原因（仅 create_refund_ticket 必填），例如「尺码不合适」",
                    },
                    "address_id": {
                        "type": "integer",
                        "description": "新收货地址 ID（仅 change_address 必填，来自 list_my_addresses）",
                    },
                },
                "required": ["action_type", "order_no"],
            },
        },
    },
]


def tool_label(name: str, args: dict) -> str:
    """生成给前端展示的工具调用步骤文案"""
    if name == "search_knowledge_base":
        return f"🛠 检索知识库：{args.get('query', '')}"
    if name == "query_my_orders":
        label = "查询我的订单"
        if args.get("order_no"):
            label += f"：{args['order_no']}"
        return f"🛠 {label}"
    if name == "recommend_products":
        return f"🛠 商品导购：{args.get('query', '')}"
    if name == "list_my_addresses":
        return "🛠 查询我的收货地址"
    if name == "propose_after_sales_action":
        labels = {
            "cancel_order": "取消订单",
            "create_refund_ticket": "申请退款",
            "change_address": "修改收货地址",
        }
        return f"🛠 发起售后提案：{labels.get(args.get('action_type'), '售后操作')}"
    return f"🛠 调用工具：{name}"


# 充分性门控结论 → 写回工具结果的生成约束（生成前门控）
_SUFFICIENCY_HINTS = {
    "partial": (
        "【证据充分性提示】检索结果只覆盖了问题的一部分。"
        "请只回答资料明确支持的内容，资料没有提到的细节必须说明「暂时无法确认」，"
        "并建议用户联系人工客服核实。"
    ),
    "insufficient": (
        "【证据充分性提示】检索结果与问题相关性很低。"
        "禁止凭常识编造平台政策；请明确告知用户知识库暂未收录该信息，"
        "并建议联系人工客服核实。"
    ),
}


def _hit_datetime(value) -> datetime | None:
    """Milvus 返回的是秒级时间戳；兼容测试里直接塞 datetime 的情况"""
    if isinstance(value, (int, float)) and value:
        return from_epoch(int(value))
    return value or None


def _search_knowledge_base(args: dict, db: Session,
                           tenant_id: int | None = None,
                           user_id: int | None = None) -> ToolResult:
    """检索知识库：返回给模型看的文本 + 给前端的引用来源（限定当前租户）

    检索后立即做充分性门控：结论既作为提示写回给模型（生成前约束），
    也放进 meta 供 chat_service 生成 verify 事件（生成后校验）。

    方向 C：order_no 非空时，用订单成交时间作为 effective_at，
    只检索那笔订单成交时生效的政策版本；普通问题用当前时间。
    """
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult("未提供检索关键词。", [])

    order_no = (args.get("order_no") or "").strip()
    effective_at = datetime.now()
    order_note = ""
    if order_no:
        order = OrderRepository(db).get_by_order_no(order_no)
        # 订单归属必须由服务端校验，绝不能用模型传入的订单号查别人的政策
        if not order or user_id is None or order.user_id != user_id:
            order_note = f"未找到属于您的订单 {order_no}，以下按当前生效政策检索。\n\n"
        elif order.created_at:
            effective_at = order.created_at
            order_note = (
                f"以下资料按订单 {order_no} 成交时间 "
                f"{order.created_at:%Y-%m-%d} 生效的政策版本检索。\n\n"
            )

    # 方向 D：先按问题复杂度选链路，再检索；订单问题禁用语义缓存，
    # 避免把「某笔订单适用什么政策」缓存成通用答案。
    decision = router.classify_query(query, has_order=bool(order_no))
    hits, retrieval_meta = retriever.search_with_meta(
        query,
        tenant_id=tenant_id,
        effective_at=effective_at,
        strategy=decision.strategy,
        allow_semantic_cache=not bool(order_no),
    )
    meta = {
        "kb_used": decision.strategy != "none",
        "query": query,
        "order_no": order_no or None,
        "effective_at": effective_at.isoformat(),
        "route": decision.to_dict(),
        "retrieval": retrieval_meta,
    }

    # 闲聊/问候：不检索，直接让模型作答（不注入“资料不足”的约束）
    if decision.strategy == "none":
        return ToolResult(
            "该问题属于闲聊或通用问题，无需检索知识库，请直接回答用户。",
            [], None, meta,
        )

    judgement = sufficiency.judge_sufficiency(query, hits)
    meta["sufficiency"] = judgement
    hint = _SUFFICIENCY_HINTS.get(judgement["level"])

    if not hits:
        text = order_note + "知识库中未检索到相关内容。"
        if order_no and "未找到属于您的订单" not in order_note:
            text += "\n未检索到该订单成交时生效的政策版本，建议转人工核实。"
        if hint:
            text += "\n\n" + hint
        return ToolResult(text, [], None, meta)

    lines = []
    sources = []
    for i, h in enumerate(hits):
        doc = DocumentRepository(db).get(h["doc_id"], tenant_id)
        version = h.get("doc_version") or (doc.version if doc else 1)
        policy_key = h.get("policy_key") or (doc.policy_key if doc else None)
        label = f"[片段{i + 1}"
        if policy_key:
            label += f" · {policy_key} v{version}"
        label += "]"
        lines.append(f"{label} {h['text']}")
        effective_from = _hit_datetime(h.get("effective_from")) or (
            doc.effective_from if doc else None
        )
        sources.append({
            "doc_id": h["doc_id"],
            "doc_name": doc.name if doc else "未知文档",
            "chunk_index": h["chunk_index"],
            "text": h["text"],
            "score": h["score"],
            "version": version,
            "policy_key": policy_key,
            # SSE meta 直接 json.dumps，这里先转 ISO 字符串；
            # Pydantic Source 会自动把它解析回 datetime。
            "effective_from": effective_from.isoformat() if effective_from else None,
        })
    text = order_note + "\n\n".join(lines)
    if hint:
        text += "\n\n" + hint
    return ToolResult(text, sources, None, meta)


def _order_card(order, items: list) -> dict:
    """订单卡片（给前端渲染，脱敏无关字段）"""
    return {
        "order_no": order.order_no,
        "status": order.status,
        "total_amount": order.total_amount,
        "logistics": order.logistics or "",
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "name": i.product_name,
                "variant_spec": i.variant_spec or "",
                "quantity": i.quantity,
                "price": i.price,
                "image": i.image,
                "image_url": None,  # 明细快照不含图路径，由前端回退 emoji
            }
            for i in items
        ],
    }


def _query_my_orders(args: dict, db: Session,
                     tenant_id: int | None = None,
                     user_id: int | None = None) -> ToolResult:
    """查询当前顾客自己的订单（越权防护：只能查 user_id 自己的）

    【面试考点：模型不可信原则】user_id 来自服务端 JWT 解析，绝不来自模型参数——
    模型只能传可选的 order_no；即使被诱导"帮我查张三的订单"，归属过滤也在
    工具内部完成（order.user_id != user_id 一律拒绝）。
    查无此单时统一回答"没有找到属于您的订单"，与"订单不存在"话术一致，
    不向攻击者泄露他人订单的存在性。
    """
    if user_id is None:
        return ToolResult("当前用户未登录，无法查询订单。", [])

    order_no = (args.get("order_no") or "").strip()
    repo = OrderRepository(db)
    payload_orders = []
    if order_no:
        order = repo.get_by_order_no(order_no)
        if not order or order.user_id != user_id:
            return ToolResult(f"没有找到属于您的订单 {order_no}，请核对订单号是否正确。", [])
        orders = [order]
    else:
        orders = repo.list_by_user(user_id)[:5]
        if not orders:
            return ToolResult("您目前还没有订单。", [])

    blocks = []
    for order in orders:
        items = repo.items_of(order.id)
        payload_orders.append(_order_card(order, items))
        item_text = "；".join(
            f"{i.product_name}{('（' + i.variant_spec + '）') if i.variant_spec else ''}"
            f"×{i.quantity}（¥{i.price}）"
            for i in items
        ) or "（无商品明细）"
        block = (
            f"订单号：{order.order_no}\n"
            f"商品：{item_text}\n"
            f"总额：¥{order.total_amount}\n"
            f"状态：{order.status}\n"
            f"物流：{order.logistics or '暂无物流信息'}"
        )
        blocks.append(block)
    payload = {"type": "orders", "items": payload_orders}
    return ToolResult("\n\n".join(blocks), [], payload)


def _product_card(product, db: Session) -> dict:
    """商品卡片：复用前台序列化（店铺名 + 评价统计）"""
    from app.services.product_service import serialize_public

    data = serialize_public(product, db)
    return {
        "id": data["id"],
        "name": data["name"],
        "subtitle": data.get("subtitle") or "",
        "price": data["price"],
        "original_price": data.get("original_price"),
        "image": data.get("image") or "📦",
        "image_url": data.get("image_url"),
        "store_name": data.get("store_name") or "智购自营",
        "sales": data.get("sales") or 0,
        "avg_rating": data.get("avg_rating") or 0,
        "review_count": data.get("review_count") or 0,
    }


def _recommend_products(args: dict, db: Session,
                        tenant_id: int | None = None,
                        user_id: int | None = None) -> ToolResult:
    """商品导购：关键词匹配在售商品（全平台），可按预算过滤

    【防幻觉设计】模型只负责从用户话术里提炼 query / budget_max 两个参数，
    商品名与价格全部来自本函数的 DB 查询结果（在售 + 按销量），
    system prompt 明确要求"按返回结果推荐并附价格"；查不到就如实说没有——
    模型永远不自己生成商品信息（幻觉 = 客诉 + 赔付）。
    """
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult("未提供商品需求描述。", [])

    budget = args.get("budget_max")
    try:
        budget = float(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget = None

    product_repo = ProductRepository(db)
    tenant_repo = TenantRepository(db)

    # 先按整句模糊匹配，命中不足再按分词逐个匹配
    candidates = product_repo.search_on_sale(query, limit=8)
    if len(candidates) < 3:
        import jieba
        seen_ids = {p.id for p in candidates}
        for token in jieba.cut(query):
            token = token.strip()
            if len(token) < 2:
                continue
            for p in product_repo.search_on_sale(token, limit=5):
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    candidates.append(p)

    if budget is not None:
        candidates = [p for p in candidates if p.price <= budget]
    if not candidates:
        if budget is not None:
            return ToolResult(f"没有找到 {query} 相关且预算 {budget} 元以内的在售商品，可以看看其他品类。", [])
        return ToolResult(f"暂时没有找到与「{query}」相关的在售商品。", [])

    top = candidates[:5]
    cards = [_product_card(p, db) for p in top]
    lines = ["以下是为您挑选的在售商品："]
    for rank, p in enumerate(top, start=1):
        store = (
            tenant_repo.get(p.tenant_id).name
            if p.tenant_id and tenant_repo.get(p.tenant_id)
            else "平台自营"
        )
        line = f"{rank}. {p.name} —— ¥{p.price}（{store}，已售 {p.sales}）"
        if p.subtitle:
            line += f"\n   {p.subtitle}"
        lines.append(line)
    payload = {"type": "products", "items": cards}
    return ToolResult("\n".join(lines), [], payload)


def _list_my_addresses(args: dict, db: Session,
                       tenant_id: int | None = None,
                       user_id: int | None = None) -> ToolResult:
    """查当前顾客的地址簿（改址提案需要真实的 address_id）"""
    if user_id is None:
        return ToolResult("当前用户未登录，无法查询收货地址。", [])
    addresses = AddressRepository(db).list(user_id)
    if not addresses:
        return ToolResult("您还没有保存收货地址，请先在「我的地址」中添加。", [])
    blocks = []
    for a in addresses:
        default = "（默认地址）" if a.is_default else ""
        blocks.append(
            f"地址ID：{a.id}{default}\n"
            f"收货人：{a.receiver} {a.phone}\n"
            f"地址：{a.region} {a.detail}"
        )
    return ToolResult("\n\n".join(blocks), [])


def _propose_after_sales_action(args: dict, db: Session,
                                tenant_id: int | None = None,
                                user_id: int | None = None,
                                session_id: int | None = None) -> ToolResult:
    """生成待确认的售后提案（不写业务数据）

    【模型不可信的落点】模型能做的只是"建议"；真正的写操作在用户点击确认后，
    由 /aftersale/actions/{token}/confirm 完成。这里把所有参数重新交给服务层
    校验（订单归属、状态、地址归属），模型给什么参数都不能绕过。
    """
    if user_id is None:
        return ToolResult("当前用户未登录，无法发起售后操作。", [])
    if session_id is None:
        return ToolResult("当前会话无效，无法发起售后操作。", [])
    action_type = str(args.get("action_type") or "").strip()
    try:
        proposal = aftersale_service.propose(
            db,
            user_id,
            session_id,
            action_type,
            {
                "order_no": args.get("order_no"),
                "reason": args.get("reason"),
                "address_id": args.get("address_id"),
            },
        )
    except AppError as exc:
        # 业务校验失败转成可供模型转述的话术，而不是让整条问答流报错
        return ToolResult(f"无法发起该售后操作：{exc.message}", [])

    text = (
        f"已生成「{proposal['title']}」待确认提案：{proposal['summary']}。\n"
        "确认卡片已推送给用户，必须由用户点击「确认执行」后才会真正生效。"
        "在用户确认前，不要声称操作已完成，也不要重复发起同一提案。"
    )
    payload = {"type": "action", "action": proposal}
    return ToolResult(text, [], payload)


def _search_handler(args: dict, db: Session, tenant_id: int | None,
                    user_id: int | None, session_id: int | None) -> ToolResult:
    return _search_knowledge_base(args, db, tenant_id, user_id)


def _orders_handler(args: dict, db: Session, tenant_id: int | None,
                    user_id: int | None, session_id: int | None) -> ToolResult:
    return _query_my_orders(args, db, tenant_id, user_id)


def _recommend_handler(args: dict, db: Session, tenant_id: int | None,
                       user_id: int | None, session_id: int | None) -> ToolResult:
    return _recommend_products(args, db, tenant_id, user_id)


def _address_handler(args: dict, db: Session, tenant_id: int | None,
                     user_id: int | None, session_id: int | None) -> ToolResult:
    return _list_my_addresses(args, db, tenant_id, user_id)


def _propose_handler(args: dict, db: Session, tenant_id: int | None,
                     user_id: int | None, session_id: int | None) -> ToolResult:
    return _propose_after_sales_action(args, db, tenant_id, user_id, session_id)


_HANDLERS = {
    "search_knowledge_base": _search_handler,
    "query_my_orders": _orders_handler,
    "recommend_products": _recommend_handler,
    "list_my_addresses": _address_handler,
    "propose_after_sales_action": _propose_handler,
}


def execute_tool(name: str, args: dict, db: Session,
                 tenant_id: int | None = None,
                 user_id: int | None = None,
                 session_id: int | None = None) -> ToolResult:
    """执行工具，返回 ToolResult（模型文本 + 引用来源 + 前端卡片 payload）

    【身份注入点】tenant_id / user_id / session_id 由 chat_service 从 JWT 解析后传入——
    工具永远不信任模型提供的任何身份信息。这是 Agent 工具设计的通用安全范式：
    模型输出只当"意图"，权限边界全部在代码里。

    【异常隔离】工具内部任何异常都在这里兜住并转成可读话术：
    单个工具失败不应该让整轮问答 500，模型拿到错误说明后仍可继续回答或换工具。
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return ToolResult(f"未知工具：{name}", [])

    started = time.perf_counter()
    try:
        return handler(args, db, tenant_id, user_id, session_id)
    except AppError as exc:
        # 业务校验失败（订单不存在、状态不允许等）→ 让模型转述给用户
        logger.warning("工具业务校验失败 name=%s args=%s err=%s", name, args, exc.message)
        return ToolResult(f"工具调用失败：{exc.message}", [])
    except Exception:
        logger.exception("工具执行异常 name=%s args=%s", name, args)
        return ToolResult("工具暂时不可用，请换一种方式提问或稍后重试。", [])
    finally:
        elapsed = time.perf_counter() - started
        if elapsed > settings.tool_timeout_seconds:
            logger.warning(
                "工具耗时超出预算 name=%s elapsed=%.2fs budget=%.2fs",
                name, elapsed, settings.tool_timeout_seconds,
            )


def parse_arguments(raw: str | None) -> dict:
    """解析模型给出的工具参数（JSON 字符串），解析失败返回空字典"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
