"""订单服务：下单 → 支付 → 发货 → 收货 全状态机（电商域核心）

订单归属顾客（user_id）；商家通过订单明细的 merchant_id 圈定
「包含我商品的订单」并完成发货，实现平台/商家两套视角。

【状态机】每个流转都是独立方法，方法内先校验当前状态，非法流转抛 400：
    待付款 ──pay──▶ 待发货 ──ship(商家)──▶ 已发货 ──confirm──▶ 已完成
       │
       └──cancel──▶ 已取消（终态，回补库存 + 退回优惠券）
  不允许跳状态（如待发货不能直接确认收货）。为什么集中成状态机而不是路由里 if/else：
  业务规则只有一处、新增状态（如"已退款"）只改这里、每个方法天然是事务边界与测试点。

【快照 vs 外键引用】（面试高频）
  订单明细冗余 product_name / price / image 的成交时刻值 —— 商品后续改价/改名/下架
  不影响历史订单；同时保留 product_id（售后定位）与 merchant_id（商家圈单）。
  收货地址同理：下单瞬间把地址写死进订单，地址簿之后的修改/删除不影响已有订单。

【并发与库存】（已实现条件更新）
  扣库存不再"先查后减"，而是单条条件更新：
    UPDATE products SET stock = stock - n WHERE id = ? AND stock >= n
  影响行数 = 1 才算成功，并发下只有一个请求能扣到最后一支库存，杜绝超卖。
  取消订单的回补仍走 ORM 增量更新（逆向操作，不需要抢占语义）。
  进一步的生产方案：Redis 预扣（DECR / Lua）+ 异步落库；本项目的 DB 条件更新已够用。
"""
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.order import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_DONE,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_SHIPPED,
    Order,
    OrderItem,
    OrderLogisticsEvent,
)
from app.models.payment import (
    PAYMENT_METHOD_LABELS,
    PAYMENT_STATUS_CLOSED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_SUCCESS,
    Payment,
)
from app.models.product import Product
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.product_repository import ProductRepository
from app.services import address_service, cart_service, coupon_service, product_service

# 物流状态只能按顺序向前推进，避免商家把轨迹改回历史节点
LOGISTICS_FLOW = ["已发货", "已揽收", "运输中", "派送中", "已签收"]


def _gen_order_no() -> str:
    """生成平台订单号：ZG + 时间戳 + 4 位随机数"""
    return f"ZG{datetime.now():%Y%m%d%H%M%S}{random.randint(0, 9999):04d}"


def _gen_payment_no() -> str:
    """生成支付单号：PAY + 时间戳 + 4 位随机数"""
    return f"PAY{datetime.now():%Y%m%d%H%M%S}{random.randint(0, 9999):04d}"


def _split_legacy_logistics(order: Order) -> tuple[str, str]:
    """兼容旧数据：从「顺丰速运 SF123」拆出公司与运单号"""
    company = (order.logistics_company or "").strip()
    tracking = (order.tracking_no or "").strip()
    if company and tracking:
        return company, tracking
    parts = (order.logistics or "").strip().split(maxsplit=1)
    if len(parts) == 2:
        return company or parts[0], tracking or parts[1]
    if parts and parts[0]:
        return company or "快递", tracking or parts[0]
    return company, tracking


def _ensure_logistics_events(db: Session,
                             order: Order) -> list[OrderLogisticsEvent]:
    """为已发货订单补齐物流轨迹；老订单按发货时间惰性生成"""
    events = (
        db.query(OrderLogisticsEvent)
        .filter(OrderLogisticsEvent.order_id == order.id)
        .order_by(OrderLogisticsEvent.occurred_at.asc())
        .all()
    )
    if events:
        return events
    if order.status not in (ORDER_STATUS_SHIPPED, ORDER_STATUS_DONE):
        return []

    company, tracking = _split_legacy_logistics(order)
    if not tracking and not order.logistics:
        return []

    shipped_at = order.shipped_at or order.created_at or datetime.now()
    order.shipped_at = shipped_at
    if not order.estimated_delivery_at:
        order.estimated_delivery_at = shipped_at + timedelta(days=3)
    order.logistics_company = company
    order.tracking_no = tracking
    order.logistics = f"{company} {tracking}".strip()

    steps = [
        (0, "已发货", "商家已发货，等待快递揽收", "商家仓库"),
        (2, "已揽收", f"{company or '快递'}已揽收包裹", "发货城市"),
        (12, "运输中", "包裹已到达中转中心，正在发往收货城市", "区域分拨中心"),
        (36, "派送中", "快递员正在派送，请保持电话畅通", "收货城市"),
        (48, "已签收", "包裹已签收，感谢使用", "收货地址"),
    ]
    created = []
    for hours, status, description, location in steps:
        event = OrderLogisticsEvent(
            order_id=order.id,
            status=status,
            description=description,
            location=location,
            occurred_at=shipped_at + timedelta(hours=hours),
        )
        db.add(event)
        created.append(event)
    db.commit()
    for event in created:
        db.refresh(event)
    return created


def _logistics_payload(db: Session | None, order: Order) -> dict:
    """对外的物流视图：只展示已经发生的轨迹节点"""
    if db is None:
        return {}
    events = _ensure_logistics_events(db, order)
    now = datetime.now()
    occurred = [e for e in events if e.occurred_at <= now]
    occurred.sort(key=lambda e: e.occurred_at, reverse=True)
    company, tracking = _split_legacy_logistics(order)
    return {
        "logistics_company": company,
        "tracking_no": tracking,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "estimated_delivery_at": (
            order.estimated_delivery_at.isoformat()
            if order.estimated_delivery_at else None
        ),
        "logistics_status": occurred[0].status if occurred else (
            order.status if order.status == ORDER_STATUS_SHIPPED else ""
        ),
        "logistics_events": [
            {
                "status": e.status,
                "description": e.description,
                "location": e.location,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in occurred
        ],
    }


def _serialize_payment(payment: Payment) -> dict:
    return {
        "id": payment.id,
        "payment_no": payment.payment_no,
        "order_id": payment.order_id,
        "amount": payment.amount,
        "method": payment.method,
        "method_label": PAYMENT_METHOD_LABELS.get(payment.method, payment.method),
        "status": payment.status,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
    }


def _serialize(order: Order, items: list[OrderItem] | None = None,
               db: Session | None = None) -> dict:
    # 明细快照只存 emoji；实物图从商品表现查（商品删图后自动回退 emoji）
    image_urls: dict[int, str | None] = {}
    if db and items:
        product_ids = {i.product_id for i in items if i.product_id}
        if product_ids:
            rows = db.query(Product.id, Product.image_url).filter(
                Product.id.in_(product_ids)
            ).all()
            image_urls = dict(rows)
    items = items or []
    logistics_info = _logistics_payload(db, order)
    return {
        "id": order.id,
        "order_no": order.order_no,
        "total_amount": order.total_amount,
        "discount_amount": order.discount_amount or 0.0,
        "coupon_id": order.coupon_id,
        "status": order.status,
        "receiver_name": order.receiver_name,
        "receiver_phone": order.receiver_phone,
        "receiver_address": order.receiver_address,
        "logistics": order.logistics,
        "logistics_company": logistics_info.get("logistics_company", ""),
        "tracking_no": logistics_info.get("tracking_no", ""),
        "shipped_at": logistics_info.get("shipped_at"),
        "estimated_delivery_at": logistics_info.get("estimated_delivery_at"),
        "logistics_status": logistics_info.get("logistics_status", ""),
        "logistics_events": logistics_info.get("logistics_events", []),
        "payment_method": order.payment_method or "",
        "payment_method_label": PAYMENT_METHOD_LABELS.get(order.payment_method, ""),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "expire_at": order.expire_at.isoformat() if order.expire_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "variant_id": i.variant_id,
                "variant_spec": i.variant_spec or "",
                "product_name": i.product_name,
                "image": i.image,
                "image_url": image_urls.get(i.product_id),
                "price": i.price,
                "quantity": i.quantity,
            }
            for i in items
        ],
    }


def _buy_now_item(db: Session, product_id: int, variant_id: int | None,
                  quantity: int) -> dict:
    """立即购买：构造一条"虚拟购物车条目"，复用后续库存/优惠券/明细逻辑

    id 为 None 表示不属于购物车，下单成功后不会回写/删除购物车数据。
    """
    if quantity <= 0:
        raise BadRequestError("购买数量必须大于 0")
    product = product_service.get_product(db, product_id)
    variant = product_service.resolve_variant(db, product, variant_id)
    return {
        "id": None,
        "product_id": product.id,
        "variant_id": variant.id if variant else None,
        "quantity": quantity,
        "variant": product_service.serialize_variant(variant) if variant else None,
        "product": product,
        "unit_price": variant.price if variant else product.price,
        "stock": variant.stock if variant else product.stock,
    }


def create_order(db: Session, user_id: int, address_id: int,
                 cart_item_ids: list[int] | None = None,
                 coupon_id: int | None = None,
                 buy_now: dict | None = None) -> dict:
    """下单：锁定地址快照、扣库存、核销优惠券、生成订单与明细

    两种入口共用同一套下单逻辑：
    - 购物车结算：按 cart_item_ids 勾选条目，下单后清理已购条目；
    - 立即购买：buy_now 构造单条虚拟条目，不读写购物车。
    """
    address = address_service.list_addresses(db, user_id)
    target = next((a for a in address if a.id == address_id), None)
    if not target:
        raise NotFoundError("收货地址不存在")

    if buy_now:
        cart_items = [_buy_now_item(
            db, buy_now["product_id"], buy_now.get("variant_id"),
            buy_now.get("quantity", 1),
        )]
    else:
        # 勾选要下单的购物车条目（不传默认全部）
        cart_items = cart_service.get_cart(db, user_id)
        if cart_item_ids:
            cart_items = [c for c in cart_items if c["id"] in cart_item_ids]
        cart_items = [c for c in cart_items if c["product"]]
        if not cart_items:
            raise BadRequestError("购物车为空或商品已失效，无法下单")

    # 库存预检只负责给出友好提示；真正的防超卖由下面的条件更新保证
    total = 0.0
    for c in cart_items:
        product: Product = c["product"]
        variant = c["variant"]
        if product.status != "on_sale":
            raise BadRequestError(f"「{product.name}」已下架，请移除后再下单")
        # 商品已配置规格但购物车条目没选规格（如规格是后加的）→ 要求重新选择
        if not variant and product_service.list_variants(db, product.id):
            raise BadRequestError(f"「{product.name}」请重新选择商品规格")
        stock = variant["stock"] if variant else product.stock
        if stock < c["quantity"]:
            raise BadRequestError(f"「{product.name}」库存不足，仅剩 {stock} 件")
        total += (variant["price"] if variant else product.price) * c["quantity"]

    # 优惠券抵扣（核销：校验归属/状态/门槛）
    discount = 0.0
    coupon = None
    if coupon_id:
        discount, coupon = coupon_service.redeem(db, user_id, coupon_id, total)

    # 扣库存：条件更新，影响行数 0 表示并发下已被其他请求抢先扣完
    # 有规格时同时扣「商品汇总库存」与「规格库存」，两者都成功才算下单成功
    for c in cart_items:
        product = c["product"]
        if not product_service.deduct_stock(db, product.id, c["quantity"]):
            raise BadRequestError(f"「{product.name}」库存不足，请刷新后重试")
        if c["variant_id"] and not product_service.deduct_variant_stock(
            db, c["variant_id"], c["quantity"]
        ):
            raise BadRequestError(f"「{product.name}」所选规格库存不足，请刷新后重试")

    order = OrderRepository(db).create(
        user_id=user_id,
        order_no=_gen_order_no(),
        total_amount=round(total - discount, 2),
        discount_amount=discount,
        coupon_id=coupon.id if coupon else None,
        status=ORDER_STATUS_PENDING,
        expire_at=datetime.now() + timedelta(
            minutes=settings.order_pending_timeout_minutes
        ),
        receiver_name=target.receiver,
        receiver_phone=target.phone,
        receiver_address=f"{target.region} {target.detail}".strip(),
    )
    if coupon:
        coupon_service.bind_order(db, coupon, order.id)
    OrderRepository(db).add_items([
        OrderItem(
            order_id=order.id,
            product_id=product.id,
            variant_id=c["variant_id"],
            variant_spec=c["variant"]["spec"] if c["variant"] else "",
            merchant_id=product.tenant_id,
            product_name=product.name,
            image=product.image,
            price=c["variant"]["price"] if c["variant"] else product.price,
            quantity=c["quantity"],
        )
        for c in cart_items
        for product in [c["product"]]
    ])

    # 清掉已下单的购物车条目（立即购买不涉及购物车）
    if not buy_now:
        CartRepository(db).remove_by_ids(user_id, [c["id"] for c in cart_items])
    return _serialize(order, OrderRepository(db).items_of(order.id), db=db)


def pay_order(db: Session, user_id: int, order_id: int,
              method: str = "alipay") -> dict:
    """兼容旧接口的一步支付：创建支付单 + 立即确认（模拟网关同步回调）

    新前端走「创建支付单 → 确认支付」两步，能看到待支付/成功等真实状态；
    这里保留一步接口给旧客户端与测试使用。
    """
    payment = create_payment(db, user_id, order_id, method)
    return confirm_payment(db, user_id, payment["payment_no"])["order"]


# ===== 支付流水（支付方式 / 幂等 / 状态流转） =====

def create_payment(db: Session, user_id: int, order_id: int, method: str,
                   idempotency_key: str | None = None) -> dict:
    """发起支付：校验订单归属与状态，生成待支付流水

    幂等策略：
    1. 相同 Idempotency-Key 直接返回原支付单（客户端超时重试不会产生多笔）；
    2. 同订单已有 pending 流水且支付方式相同则复用；
    3. 换了支付方式则关闭旧流水再新建。
    """
    if method not in PAYMENT_METHOD_LABELS:
        raise BadRequestError("不支持的支付方式")
    order = _get_user_order(db, order_id, user_id)
    repo = PaymentRepository(db)

    key = (idempotency_key or "").strip()[:64] or None
    if key:
        existing = repo.get_by_idempotency_key(key)
        if existing:
            if existing.user_id != user_id or existing.order_id != order.id:
                raise BadRequestError("幂等键已被其他支付请求使用")
            return _serialize_payment(existing)

    if order.status != ORDER_STATUS_PENDING:
        raise BadRequestError("订单当前状态不可支付")

    pending = repo.get_pending_by_order(order.id)
    if pending:
        if pending.method == method:
            return _serialize_payment(pending)
        pending.status = PAYMENT_STATUS_CLOSED
        repo.save(pending)

    payment = repo.create(
        payment_no=_gen_payment_no(),
        order_id=order.id,
        user_id=user_id,
        amount=order.total_amount,
        method=method,
        status=PAYMENT_STATUS_PENDING,
        idempotency_key=key,
    )
    return _serialize_payment(payment)


def confirm_payment(db: Session, user_id: int, payment_no: str) -> dict:
    """确认支付（模拟网关回调）：流水成功 + 订单转待发货

    幂等：已成功的支付单重复确认直接返回当前结果，不会重复流转订单。
    """
    repo = PaymentRepository(db)
    payment = repo.get_by_no(payment_no)
    if not payment or payment.user_id != user_id:
        # 不泄露他人支付单是否存在
        raise NotFoundError("支付单不存在")
    order = _get_user_order(db, payment.order_id, user_id)

    if payment.status == PAYMENT_STATUS_SUCCESS:
        return {
            "payment": _serialize_payment(payment),
            "order": _serialize(order, OrderRepository(db).items_of(order.id), db=db),
        }
    if payment.status != PAYMENT_STATUS_PENDING:
        raise BadRequestError("支付单已关闭，请重新发起支付")
    if order.status != ORDER_STATUS_PENDING:
        payment.status = PAYMENT_STATUS_CLOSED
        repo.save(payment)
        raise BadRequestError("订单当前状态不可支付")

    now = datetime.now()
    payment.status = PAYMENT_STATUS_SUCCESS
    payment.paid_at = now
    order.status = ORDER_STATUS_PAID
    order.payment_method = payment.method
    order.paid_at = now
    repo.save(payment)  # 同一事务提交流水与订单状态
    order = OrderRepository(db).save(order)
    return {
        "payment": _serialize_payment(payment),
        "order": _serialize(order, OrderRepository(db).items_of(order.id), db=db),
    }


def list_order_payments(db: Session, user_id: int, order_id: int) -> list[dict]:
    """订单支付流水（仅本人可见）"""
    order = _get_user_order(db, order_id, user_id)
    return [
        _serialize_payment(p)
        for p in PaymentRepository(db).list_by_order(order.id)
    ]


def _cancel_pending(db: Session, order: Order) -> dict:
    """取消待付款订单的公共补偿流程：关支付单 + 回补库存 + 退券 + 落状态"""
    # 关闭未完成的支付流水，避免取消后还能确认支付
    PaymentRepository(db).close_pending(order.id)
    _restore_stock(db, order)
    coupon_service.release_if_any(db, order.id)
    order.status = ORDER_STATUS_CANCELLED
    order = OrderRepository(db).save(order)
    return _serialize(order, db=db)


def cancel_order(db: Session, user_id: int, order_id: int) -> dict:
    """取消订单（仅待付款）：回补库存 + 退回优惠券

    两个"逆向补偿"动作都做在本方法里：库存按明细快照回补、
    券按 order_id 找回重置（见 coupon_service.release_if_any）。
    幂等性由状态机保证：已取消的订单再取消会被状态校验拒绝。
    """
    order = _get_user_order(db, order_id, user_id)
    if order.status != ORDER_STATUS_PENDING:
        raise BadRequestError("仅待付款订单可以取消")
    return _cancel_pending(db, order)


def cancel_expired_orders(db: Session, now: datetime | None = None,
                          limit: int = 200) -> int:
    """批量取消超时未支付订单（后台定时任务调用）

    只处理 expire_at 非空且已过期的待付款订单，老数据没有截止时间不会被误伤。
    逐单提交：单笔失败不影响其他订单，返回本次成功取消的数量。
    """
    now = now or datetime.now()
    orders = (
        db.query(Order)
        .filter(
            Order.status == ORDER_STATUS_PENDING,
            Order.expire_at.isnot(None),
            Order.expire_at <= now,
        )
        .order_by(Order.expire_at.asc())
        .limit(limit)
        .all()
    )
    cancelled = 0
    for order in orders:
        try:
            _cancel_pending(db, order)
            cancelled += 1
        except Exception:  # noqa: BLE001 - 单笔失败不阻断批量清理
            db.rollback()
    return cancelled


def confirm_receive(db: Session, user_id: int, order_id: int) -> dict:
    """顾客确认收货：已发货 → 已完成"""
    order = _get_user_order(db, order_id, user_id)
    if order.status != ORDER_STATUS_SHIPPED:
        raise BadRequestError("订单尚未发货或已完成")
    order.status = ORDER_STATUS_DONE
    order = OrderRepository(db).save(order)
    return _serialize(order, db=db)


def ship_order(db: Session, order_id: int, logistics_company: str,
               tracking_no: str, merchant_id: int | None,
               logistics: str | None = None) -> dict:
    """商家发货：待发货 → 已发货（仅能发包含自己商品的订单）

    越权防线在业务校验而非路由：先看订单明细里有没有本店商品（merchant_id），
    没有直接 403 —— 商家 A 连"存在感"都探测不到商家 B 的订单。
    """
    repo = OrderRepository(db)
    order = repo.get(order_id)
    if not order:
        raise NotFoundError("订单不存在")
    item_merchant_ids = {i.merchant_id for i in repo.items_of(order.id)}
    if merchant_id not in item_merchant_ids:
        raise ForbiddenError("该订单不包含本店商品")
    if order.status != ORDER_STATUS_PAID:
        raise BadRequestError("订单当前状态不可发货")

    company = (logistics_company or "").strip()
    tracking = (tracking_no or "").strip()
    # 兼容旧客户端：只传「顺丰速运 SF123」时自动拆分
    if (not company or not tracking) and logistics:
        parts = logistics.strip().split(maxsplit=1)
        if len(parts) == 2:
            company = company or parts[0]
            tracking = tracking or parts[1]
        else:
            tracking = tracking or (parts[0] if parts else "")
    if not tracking:
        raise BadRequestError("请填写物流单号")
    company = company or "快递"

    now = datetime.now()
    order.status = ORDER_STATUS_SHIPPED
    order.logistics_company = company
    order.tracking_no = tracking
    order.logistics = f"{company} {tracking}"
    order.shipped_at = now
    order.estimated_delivery_at = now + timedelta(days=3)
    order = repo.save(order)

    # 预生成轨迹节点，查询时只返回已发生的事件，形成自动推进的物流时间线
    steps = [
        (0, "已发货", "商家已发货，等待快递揽收", "商家仓库"),
        (2, "已揽收", f"{company}已揽收包裹", "发货城市"),
        (12, "运输中", "包裹已到达中转中心，正在发往收货城市", "区域分拨中心"),
        (36, "派送中", "快递员正在派送，请保持电话畅通", "收货城市"),
        (48, "已签收", "包裹已签收，感谢使用", "收货地址"),
    ]
    for hours, status, description, location in steps:
        db.add(OrderLogisticsEvent(
            order_id=order.id,
            status=status,
            description=description,
            location=location,
            occurred_at=now + timedelta(hours=hours),
        ))
    db.commit()
    return _serialize(order, db=db)


def add_logistics_event(db: Session, order_id: int, merchant_id: int | None,
                        status: str, description: str = "",
                        location: str = "") -> dict:
    """商家手动推进物流状态（真实场景：揽收/运输/派送/签收）"""
    repo = OrderRepository(db)
    order = repo.get(order_id)
    if not order:
        raise NotFoundError("订单不存在")
    my_items = [i for i in repo.items_of(order.id) if i.merchant_id == merchant_id]
    if not my_items:
        raise ForbiddenError("该订单不包含本店商品")
    if order.status != ORDER_STATUS_SHIPPED:
        raise BadRequestError("仅已发货订单可以更新物流状态")

    status = (status or "").strip()
    if status not in LOGISTICS_FLOW:
        raise BadRequestError("无效的物流状态")

    _ensure_logistics_events(db, order)
    now = datetime.now()
    occurred = (
        db.query(OrderLogisticsEvent)
        .filter(
            OrderLogisticsEvent.order_id == order.id,
            OrderLogisticsEvent.occurred_at <= now,
        )
        .order_by(OrderLogisticsEvent.occurred_at.desc())
        .all()
    )
    current = occurred[0].status if occurred else "已发货"
    if status not in LOGISTICS_FLOW or current not in LOGISTICS_FLOW:
        raise BadRequestError("当前物流状态异常，无法更新")
    if LOGISTICS_FLOW.index(status) <= LOGISTICS_FLOW.index(current):
        raise BadRequestError(f"当前物流状态为「{current}」，只能向前更新")

    # 商家接管后，删除尚未发生的模拟轨迹，后续由商家按真实节点推进
    db.query(OrderLogisticsEvent).filter(
        OrderLogisticsEvent.order_id == order.id,
        OrderLogisticsEvent.occurred_at > now,
    ).delete(synchronize_session=False)

    defaults = {
        "已揽收": (f"{order.logistics_company or '快递'}已揽收包裹", "发货城市"),
        "运输中": ("包裹已到达中转中心，正在发往收货城市", "区域分拨中心"),
        "派送中": ("快递员正在派送，请保持电话畅通", "收货城市"),
        "已签收": ("包裹已签收，感谢使用", "收货地址"),
    }
    default_desc, default_loc = defaults.get(status, ("物流状态已更新", ""))
    db.add(OrderLogisticsEvent(
        order_id=order.id,
        status=status,
        description=(description or "").strip() or default_desc,
        location=(location or "").strip() or default_loc,
        occurred_at=now,
    ))
    db.commit()

    data = _serialize(order, my_items, db=db)
    data["total_amount"] = sum(i.price * i.quantity for i in my_items)
    return data


def list_my_orders(db: Session, user_id: int, status: str | None = None,
                   page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
    """顾客订单列表（带明细，分页）→ (订单列表, 总数)"""
    repo = OrderRepository(db)
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 100)
    orders = repo.list_by_user(
        user_id, status, offset=(page - 1) * page_size, limit=page_size
    )
    items = repo.items_of_orders([o.id for o in orders])
    by_order: dict[int, list[OrderItem]] = {}
    for i in items:
        by_order.setdefault(i.order_id, []).append(i)
    result = [_serialize(o, by_order.get(o.id, []), db=db) for o in orders]
    return result, repo.count_by_user(user_id, status)


def get_my_order(db: Session, user_id: int, order_id: int) -> dict:
    order = _get_user_order(db, order_id, user_id)
    return _serialize(order, OrderRepository(db).items_of(order.id), db=db)


def list_merchant_orders(db: Session, merchant_id: int | None,
                         status: str | None = None) -> list[dict]:
    """商家订单列表：只含本店商品的订单，明细也只展示本店部分"""
    repo = OrderRepository(db)
    order_ids = repo.list_order_ids_by_merchant(merchant_id, status)
    if not order_ids:
        return []
    orders = (
        db.query(Order)
        .filter(Order.id.in_(order_ids))
        .order_by(Order.created_at.desc())
        .all()
    )
    result = []
    for order in orders:
        my_items = [
            i for i in repo.items_of(order.id) if i.merchant_id == merchant_id
        ]
        if not my_items:
            continue
        data = _serialize(order, my_items, db=db)
        data["total_amount"] = sum(i.price * i.quantity for i in my_items)
        result.append(data)
    return result


def list_platform_orders(db: Session, status: str | None = None,
                         limit: int = 100) -> list[dict]:
    """平台监管：全平台订单（只读，附下单顾客用户名）"""
    from app.models.user import User

    repo = OrderRepository(db)
    orders = repo.list_all(status, limit)
    if not orders:
        return []
    items = repo.items_of_orders([o.id for o in orders])
    by_order: dict[int, list[OrderItem]] = {}
    for item in items:
        by_order.setdefault(item.order_id, []).append(item)
    user_ids = {o.user_id for o in orders}
    usernames = dict(
        db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
    )
    result = []
    for order in orders:
        data = _serialize(order, by_order.get(order.id, []), db=db)
        data["username"] = usernames.get(order.user_id, "-")
        result.append(data)
    return result


def _get_user_order(db: Session, order_id: int, user_id: int) -> Order:
    """取本人订单；越权（别人的订单）与不存在统一按 404 处理

    统一 404 是刻意的：如果"别人的订单"返回 403，攻击者能据此确认
    该订单 ID 存在——不泄露资源存在性是横向越权防护的通用做法。
    """
    order = OrderRepository(db).get(order_id)
    if not order:
        raise NotFoundError("订单不存在")
    if order.user_id != user_id:
        # 越权防护：不泄露订单存在性
        raise NotFoundError("订单不存在")
    return order


def _restore_stock(db: Session, order: Order) -> None:
    """取消订单时按明细回补库存（商品汇总 + 规格）"""
    repo = OrderRepository(db)
    for item in repo.items_of(order.id):
        product_service.restore_item_stock(
            db, item.product_id, item.variant_id, item.quantity
        )
