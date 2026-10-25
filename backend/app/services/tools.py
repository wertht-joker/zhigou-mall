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
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.rag import retriever
from app.repositories.document_repository import DocumentRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.tenant_repository import TenantRepository


class ToolResult(NamedTuple):
    """工具执行结果：text 给模型推理，payload 给前端渲染卡片"""

    text: str
    sources: list[dict]
    payload: dict | None = None


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
                    }
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
    return f"🛠 调用工具：{name}"


def _search_knowledge_base(args: dict, db: Session,
                           tenant_id: int | None = None,
                           user_id: int | None = None) -> ToolResult:
    """检索知识库：返回给模型看的文本 + 给前端的引用来源（限定当前租户）"""
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult("未提供检索关键词。", [])

    hits = retriever.search(query, tenant_id=tenant_id)
    if not hits:
        return ToolResult("知识库中未检索到相关内容。", [])

    lines = []
    sources = []
    for i, h in enumerate(hits):
        lines.append(f"[片段{i + 1}] {h['text']}")
        doc = DocumentRepository(db).get(h["doc_id"], tenant_id)
        sources.append({
            "doc_id": h["doc_id"],
            "doc_name": doc.name if doc else "未知文档",
            "chunk_index": h["chunk_index"],
            "text": h["text"],
            "score": h["score"],
        })
    return ToolResult("\n\n".join(lines), sources)


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
    """查询当前顾客自己的订单（越权防护：只能查 user_id 自己的）"""
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
            f"{i.product_name}×{i.quantity}（¥{i.price}）" for i in items
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
    """商品导购：关键词匹配在售商品（全平台），可按预算过滤"""
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


def execute_tool(name: str, args: dict, db: Session,
                 tenant_id: int | None = None,
                 user_id: int | None = None) -> ToolResult:
    """执行工具，返回 ToolResult（模型文本 + 引用来源 + 前端卡片 payload）

    tenant_id 限定知识库范围；user_id 限定订单归属。
    """
    if name == "search_knowledge_base":
        return _search_knowledge_base(args, db, tenant_id, user_id)
    if name == "query_my_orders":
        return _query_my_orders(args, db, tenant_id, user_id)
    if name == "recommend_products":
        return _recommend_products(args, db, tenant_id, user_id)
    return ToolResult(f"未知工具：{name}", [])


def parse_arguments(raw: str | None) -> dict:
    """解析模型给出的工具参数（JSON 字符串），解析失败返回空字典"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
