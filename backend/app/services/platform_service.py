"""平台管理服务：平台管理员专属的数据视图

与商家后台的边界：
- 商家后台只看到自己 tenant_id 下的商品/订单；
- 平台后台看全平台汇总、商家列表与平台级商品分类，不参与商家经营操作。
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.models.aftersale import (
    TICKET_OPEN_STATUSES,
    ActionAuditLog,
    AfterSalesTicket,
)
from app.models.feedback import Feedback
from app.models.order import (
    ORDER_STATUS_DONE,
    ORDER_STATUS_PAID,
    ORDER_STATUS_SHIPPED,
    ORDER_STATUSES,
    Order,
    OrderItem,
)
from app.models.product import Product, ProductVariant
from app.models.session import Message
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.product_repository import (
    ProductCategoryRepository,
    ProductRepository,
)
from app.repositories.tenant_repository import TenantRepository
from app.services import order_service
from app.services.product_service import PLATFORM_STORE_LABEL

# 计入成交额的订单状态（已付款及之后，排除待付款/已取消）
GMV_STATUSES = (ORDER_STATUS_PAID, ORDER_STATUS_SHIPPED, ORDER_STATUS_DONE)


def overview(db: Session) -> dict:
    """平台概览：商家/商品/订单/成交额与今日数据"""
    tenant_total = db.query(func.count(Tenant.id)).scalar() or 0
    tenant_active = db.query(func.count(Tenant.id)).filter(
        Tenant.status == "active"
    ).scalar() or 0
    customer_total = db.query(func.count(User.id)).filter(
        User.role == "customer"
    ).scalar() or 0

    product_total = db.query(func.count(Product.id)).scalar() or 0
    product_on_sale = db.query(func.count(Product.id)).filter(
        Product.status == "on_sale"
    ).scalar() or 0

    order_total = db.query(func.count(Order.id)).scalar() or 0
    gmv = db.query(func.coalesce(func.sum(Order.total_amount), 0.0)).filter(
        Order.status.in_(GMV_STATUSES)
    ).scalar() or 0.0

    today_start = datetime.combine(date.today(), time.min)
    today_end = today_start + timedelta(days=1)
    today_orders = db.query(func.count(Order.id)).filter(
        Order.created_at >= today_start,
        Order.created_at < today_end,
    ).scalar() or 0
    today_gmv = db.query(
        func.coalesce(func.sum(Order.total_amount), 0.0)
    ).filter(
        Order.created_at >= today_start,
        Order.created_at < today_end,
        Order.status.in_(GMV_STATUSES),
    ).scalar() or 0.0

    by_status = {
        status: db.query(func.count(Order.id)).filter(
            Order.status == status
        ).scalar() or 0
        for status in ORDER_STATUSES
    }

    # 最近 7 天订单/成交额趋势
    trend = []
    for offset in range(6, -1, -1):
        day = date.today() - timedelta(days=offset)
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        day_orders = db.query(func.count(Order.id)).filter(
            Order.created_at >= start,
            Order.created_at < end,
        ).scalar() or 0
        day_gmv = db.query(
            func.coalesce(func.sum(Order.total_amount), 0.0)
        ).filter(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(GMV_STATUSES),
        ).scalar() or 0.0
        trend.append({
            "date": day.strftime("%m-%d"),
            "orders": day_orders,
            "gmv": round(float(day_gmv), 2),
        })

    return {
        "tenants": {"total": tenant_total, "active": tenant_active},
        "customers": customer_total,
        "products": {"total": product_total, "on_sale": product_on_sale},
        "orders": {
            "total": order_total,
            "today": today_orders,
            "by_status": by_status,
        },
        "gmv": round(float(gmv), 2),
        "today_gmv": round(float(today_gmv), 2),
        "trend": trend,
        "recent_orders": order_service.list_platform_orders(db, limit=5),
    }


def list_tenants(db: Session, keyword: str | None = None) -> list[dict]:
    """商家列表：附带商品数、在售数、订单数"""
    tenants = TenantRepository(db).list()
    if keyword:
        keyword = keyword.strip()
        tenants = [
            t for t in tenants
            if keyword in t.name or keyword in t.code
        ]

    product_counts = dict(
        db.query(Product.tenant_id, func.count(Product.id))
        .group_by(Product.tenant_id)
        .all()
    )
    on_sale_counts = dict(
        db.query(Product.tenant_id, func.count(Product.id))
        .filter(Product.status == "on_sale")
        .group_by(Product.tenant_id)
        .all()
    )
    order_counts = dict(
        db.query(OrderItem.merchant_id, func.count(func.distinct(OrderItem.order_id)))
        .group_by(OrderItem.merchant_id)
        .all()
    )
    return [
        {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "product_count": product_counts.get(t.id, 0),
            "on_sale_count": on_sale_counts.get(t.id, 0),
            "order_count": order_counts.get(t.id, 0),
            "is_platform_store": t.code == "default",
        }
        for t in tenants
    ]


def update_tenant_status(db: Session, tenant_id: int, status: str) -> dict:
    """启用/停用商家（平台自营店不允许停用）"""
    if status not in ("active", "disabled"):
        raise BadRequestError("状态只能是 active 或 disabled")
    tenant = TenantRepository(db).get(tenant_id)
    if not tenant:
        raise NotFoundError("商家不存在")
    if tenant.code == "default" and status != "active":
        raise BadRequestError("平台自营店不允许停用")
    tenant.status = status
    db.commit()
    db.refresh(tenant)
    return {"id": tenant.id, "code": tenant.code, "name": tenant.name,
            "status": tenant.status}


def list_categories(db: Session) -> list[dict]:
    """平台商品分类（附分类下商品数）"""
    counts = dict(
        db.query(Product.category_id, func.count(Product.id))
        .group_by(Product.category_id)
        .all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "icon": c.icon,
            "sort": c.sort,
            "product_count": counts.get(c.id, 0),
        }
        for c in ProductCategoryRepository(db).list()
    ]


def create_category(db: Session, name: str, icon: str, sort: int) -> dict:
    name = name.strip()
    if not name:
        raise BadRequestError("分类名称不能为空")
    repo = ProductCategoryRepository(db)
    if repo.get_by_name(name):
        raise ConflictError("分类名称已存在")
    category = repo.create(name, icon or "🛒", sort)
    return {"id": category.id, "name": category.name,
            "icon": category.icon, "sort": category.sort, "product_count": 0}


def update_category(db: Session, category_id: int, name: str,
                    icon: str, sort: int) -> dict:
    repo = ProductCategoryRepository(db)
    category = repo.get(category_id)
    if not category:
        raise NotFoundError("分类不存在")
    name = name.strip()
    if not name:
        raise BadRequestError("分类名称不能为空")
    exists = repo.get_by_name(name)
    if exists and exists.id != category_id:
        raise ConflictError("分类名称已存在")
    category.name = name
    category.icon = icon or "🛒"
    category.sort = sort
    category = repo.save(category)
    count = db.query(func.count(Product.id)).filter(
        Product.category_id == category.id
    ).scalar() or 0
    return {"id": category.id, "name": category.name,
            "icon": category.icon, "sort": category.sort,
            "product_count": count}


def delete_category(db: Session, category_id: int) -> None:
    repo = ProductCategoryRepository(db)
    category = repo.get(category_id)
    if not category:
        raise NotFoundError("分类不存在")
    count = db.query(func.count(Product.id)).filter(
        Product.category_id == category_id
    ).scalar() or 0
    if count:
        raise BadRequestError("该分类下还有商品，无法删除")
    repo.delete(category)


def list_products(db: Session, keyword: str | None = None,
                  status: str | None = None) -> list[dict]:
    """全平台商品监管（只读）：含下架商品与所属店铺"""
    products = ProductRepository(db).list_all(keyword, status)
    tenants = {t.id: t for t in TenantRepository(db).list()}
    categories = {c.id: c.name for c in ProductCategoryRepository(db).list()}
    # 规格数量单独聚合，避免逐商品查询
    variant_counts = dict(
        db.query(ProductVariant.product_id, func.count(ProductVariant.id))
        .group_by(ProductVariant.product_id)
        .all()
    )

    result = []
    for p in products:
        data = {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
        tenant = tenants.get(p.tenant_id) if p.tenant_id else None
        data["store_name"] = (
            PLATFORM_STORE_LABEL
            if tenant is None or tenant.code == "default"
            else tenant.name
        )
        data["category_name"] = categories.get(p.category_id, "")
        data["variant_count"] = variant_counts.get(p.id, 0)
        result.append(data)
    return result


def list_orders(db: Session, status: str | None = None,
                limit: int = 100) -> list[dict]:
    """全平台订单监管（只读）"""
    return order_service.list_platform_orders(db, status, limit)


def list_customers(db: Session, keyword: str | None = None) -> list[dict]:
    """顾客管理：账号 + 下单次数 / 累计消费 / 最近下单时间"""
    query = db.query(User).filter(User.role == "customer")
    if keyword:
        query = query.filter(User.username.like(f"%{keyword.strip()}%"))
    customers = query.order_by(User.created_at.desc()).all()

    stats = {
        row[0]: {
            "order_count": row[1],
            "total_spent": float(row[2] or 0),
            "last_order_at": row[3],
        }
        for row in db.query(
            Order.user_id,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0.0),
            func.max(Order.created_at),
        ).filter(Order.status.in_(GMV_STATUSES)).group_by(Order.user_id).all()
    }
    # 下单次数包含未支付/已取消订单，消费金额只统计已付款订单
    all_counts = dict(
        db.query(Order.user_id, func.count(Order.id))
        .group_by(Order.user_id)
        .all()
    )
    result = []
    for user in customers:
        stat = stats.get(user.id, {})
        result.append({
            "id": user.id,
            "username": user.username,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "order_count": all_counts.get(user.id, 0),
            "paid_order_count": stat.get("order_count", 0),
            "total_spent": round(stat.get("total_spent", 0.0), 2),
            "last_order_at": (
                stat["last_order_at"].isoformat()
                if stat.get("last_order_at") else None
            ),
        })
    return result


def feedback_overview(db: Session, limit: int = 50) -> dict:
    """AI 客服反馈分析：满意度 + 最近反馈内容"""
    up = db.query(func.count(Feedback.id)).filter(Feedback.type == "up").scalar() or 0
    down = db.query(func.count(Feedback.id)).filter(Feedback.type == "down").scalar() or 0
    total = up + down

    rows = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .all()
    )
    contents = {}
    if rows:
        message_ids = {r.message_id for r in rows}
        contents = dict(
            db.query(Message.id, Message.content)
            .filter(Message.id.in_(message_ids))
            .all()
        )
    return {
        "up": up,
        "down": down,
        "total": total,
        "satisfaction": round(up / total * 100, 1) if total else None,
        "recent": [
            {
                "id": r.id,
                "type": r.type,
                "message_id": r.message_id,
                "content": (contents.get(r.message_id) or "")[:200],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def list_audit_logs(db: Session, limit: int = 100,
                    result: str | None = None) -> list[dict]:
    """平台操作审计日志（售后 Agent 写操作留痕）"""
    query = db.query(ActionAuditLog)
    if result:
        query = query.filter(ActionAuditLog.result == result)
    logs = query.order_by(ActionAuditLog.created_at.desc()).limit(limit).all()
    user_ids = {log.user_id for log in logs}
    usernames = dict(
        db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
    )
    return [
        {
            "id": log.id,
            "trace_id": log.trace_id,
            "user_id": log.user_id,
            "username": usernames.get(log.user_id, "-"),
            "action_type": log.action_type,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "result": log.result,
            "error": log.error,
            "before_json": log.before_json,
            "after_json": log.after_json,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


def insights(db: Session) -> dict:
    """智能运营洞察：经营脉搏 + 风险预警 + 商家健康度 + 知识缺口"""
    today_start = datetime.combine(date.today(), time.min)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    month_ago = today_start - timedelta(days=30)

    def gmv_between(start: datetime, end: datetime) -> float:
        return float(
            db.query(func.coalesce(func.sum(Order.total_amount), 0.0)).filter(
                Order.created_at >= start,
                Order.created_at < end,
                Order.status.in_(GMV_STATUSES),
            ).scalar() or 0.0
        )

    def orders_between(start: datetime, end: datetime) -> int:
        return int(
            db.query(func.count(Order.id)).filter(
                Order.created_at >= start,
                Order.created_at < end,
            ).scalar() or 0
        )

    def growth(today: float, yesterday: float) -> float | None:
        if yesterday <= 0:
            return None
        return round((today - yesterday) / yesterday * 100, 1)

    today_gmv = gmv_between(today_start, tomorrow_start)
    yesterday_gmv = gmv_between(yesterday_start, today_start)
    today_orders = orders_between(today_start, tomorrow_start)
    yesterday_orders = orders_between(yesterday_start, today_start)

    pending_ship = db.query(func.count(Order.id)).filter(
        Order.status == ORDER_STATUS_PAID
    ).scalar() or 0
    open_tickets = db.query(func.count(AfterSalesTicket.id)).filter(
        AfterSalesTicket.status.in_(TICKET_OPEN_STATUSES)
    ).scalar() or 0

    tenants = TenantRepository(db).list()
    tenant_map = {t.id: t for t in tenants}

    def store_name(tenant_id: int | None) -> str:
        tenant = tenant_map.get(tenant_id) if tenant_id else None
        if tenant is None or tenant.code == "default":
            return PLATFORM_STORE_LABEL
        return tenant.name

    low_stock_query = db.query(Product).filter(
        Product.status == "on_sale",
        Product.stock <= 10,
    )
    low_stock_total = low_stock_query.count()
    low_stock = low_stock_query.order_by(Product.stock.asc()).limit(8).all()

    sold_ids = (
        db.query(OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.created_at >= month_ago,
            Order.status.in_(GMV_STATUSES),
            OrderItem.product_id.isnot(None),
        )
        .subquery()
    )
    slow_query = db.query(Product).filter(
        Product.status == "on_sale",
        ~Product.id.in_(select(sold_ids.c.product_id)),
    )
    slow_total = slow_query.count()
    slow_products = slow_query.order_by(Product.created_at.asc()).limit(8).all()

    # 商家健康度：近 30 天商品/订单/成交 + 待处理售后
    product_counts = dict(
        db.query(Product.tenant_id, func.count(Product.id))
        .group_by(Product.tenant_id).all()
    )
    on_sale_counts = dict(
        db.query(Product.tenant_id, func.count(Product.id))
        .filter(Product.status == "on_sale")
        .group_by(Product.tenant_id).all()
    )
    sales_rows = db.query(
        OrderItem.merchant_id,
        func.count(func.distinct(Order.id)),
        func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0.0),
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Order.created_at >= month_ago,
        Order.status.in_(GMV_STATUSES),
    ).group_by(OrderItem.merchant_id).all()
    sales_map = {row[0]: (row[1], float(row[2] or 0)) for row in sales_rows}

    ticket_rows = db.query(
        OrderItem.merchant_id,
        func.count(func.distinct(AfterSalesTicket.id)),
    ).join(Order, Order.id == OrderItem.order_id).join(
        AfterSalesTicket, AfterSalesTicket.order_id == Order.id
    ).filter(
        AfterSalesTicket.status.in_(TICKET_OPEN_STATUSES)
    ).group_by(OrderItem.merchant_id).all()
    ticket_map = {row[0]: row[1] for row in ticket_rows}

    merchant_health = []
    for tenant in tenants:
        total_products = product_counts.get(tenant.id, 0)
        on_sale = on_sale_counts.get(tenant.id, 0)
        orders_30d, gmv_30d = sales_map.get(tenant.id, (0, 0.0))
        tickets = ticket_map.get(tenant.id, 0)

        score = 100
        if total_products == 0:
            score -= 30
        elif on_sale / total_products < 0.6:
            score -= 15
        if orders_30d == 0:
            score -= 35
        score -= min(30, tickets * 10)
        if gmv_30d >= 10000:
            score += 5
        score = max(0, min(100, score))
        grade = "A" if score >= 85 else "B" if score >= 70 else "C"

        risks = []
        if tickets:
            risks.append(f"{tickets} 个售后待处理")
        if total_products and on_sale == 0:
            risks.append("无在售商品")
        if orders_30d == 0:
            risks.append("近 30 天无成交")
        if total_products and 0 < on_sale / total_products < 0.6:
            risks.append("在售率偏低")

        merchant_health.append({
            "id": tenant.id,
            "name": tenant.name,
            "code": tenant.code,
            "status": tenant.status,
            "is_platform_store": tenant.code == "default",
            "product_count": total_products,
            "on_sale_count": on_sale,
            "orders_30d": orders_30d,
            "gmv_30d": round(gmv_30d, 2),
            "open_tickets": tickets,
            "score": score,
            "grade": grade,
            "risks": risks,
        })
    merchant_health.sort(key=lambda x: x["score"])

    # 知识缺口：最近点踩的 AI 回答
    down_feedback = (
        db.query(Feedback)
        .filter(Feedback.type == "down")
        .order_by(Feedback.created_at.desc())
        .limit(8).all()
    )
    contents = {}
    if down_feedback:
        contents = dict(
            db.query(Message.id, Message.content)
            .filter(Message.id.in_({f.message_id for f in down_feedback}))
            .all()
        )
    knowledge_gaps = [
        {
            "feedback_id": f.id,
            "content": (contents.get(f.message_id) or "")[:160],
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in down_feedback
    ]

    gmv_growth = growth(today_gmv, yesterday_gmv)
    order_growth = growth(today_orders, yesterday_orders)

    def pct(value: float | None) -> str:
        return "—" if value is None else f"{value:+.1f}%"

    brief = (
        f"今日成交 ¥{today_gmv:.2f}（环比 {pct(gmv_growth)}），"
        f"订单 {today_orders} 单（环比 {pct(order_growth)}）。"
        f"当前 {pending_ship} 单待发货、{open_tickets} 个售后待处理；"
        f"{low_stock_total} 个商品库存紧张，{slow_total} 个商品近 30 天无成交。"
    )
    if knowledge_gaps:
        brief += f" 另有 {len(knowledge_gaps)} 条 AI 回答被点踩，建议补充知识库。"

    return {
        "brief": brief,
        "pulse": {
            "today_gmv": round(today_gmv, 2),
            "today_orders": today_orders,
            "gmv_growth": gmv_growth,
            "order_growth": order_growth,
            "pending_ship": pending_ship,
            "open_after_sales": open_tickets,
        },
        "alerts": {
            "low_stock_total": low_stock_total,
            "low_stock": [
                {
                    "id": p.id,
                    "name": p.name,
                    "image": p.image,
                    "stock": p.stock,
                    "sales": p.sales,
                    "store_name": store_name(p.tenant_id),
                }
                for p in low_stock
            ],
            "slow_moving_total": slow_total,
            "slow_moving": [
                {
                    "id": p.id,
                    "name": p.name,
                    "image": p.image,
                    "sales": p.sales,
                    "stock": p.stock,
                    "store_name": store_name(p.tenant_id),
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in slow_products
            ],
        },
        "merchant_health": merchant_health,
        "knowledge_gaps": knowledge_gaps,
    }
