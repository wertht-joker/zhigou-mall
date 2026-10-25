"""订单服务：下单 → 支付 → 发货 → 收货 全状态机

订单归属顾客（user_id）；商家通过订单明细的 merchant_id 圈定
「包含我商品的订单」并完成发货，实现平台/商家两套视角。
"""
import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.order import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_DONE,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_SHIPPED,
    Order,
    OrderItem,
)
from app.models.product import Product
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.services import address_service, cart_service, coupon_service, product_service


def _gen_order_no() -> str:
    """生成平台订单号：ZG + 时间戳 + 4 位随机数"""
    return f"ZG{datetime.now():%Y%m%d%H%M%S}{random.randint(0, 9999):04d}"


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
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "image": i.image,
                "image_url": image_urls.get(i.product_id),
                "price": i.price,
                "quantity": i.quantity,
            }
            for i in items
        ],
    }


def create_order(db: Session, user_id: int, address_id: int,
                 cart_item_ids: list[int] | None = None,
                 coupon_id: int | None = None) -> dict:
    """从购物车下单：锁定地址快照、扣库存、核销优惠券、生成订单与明细、清理已购条目"""
    address = address_service.list_addresses(db, user_id)
    target = next((a for a in address if a.id == address_id), None)
    if not target:
        raise NotFoundError("收货地址不存在")

    # 勾选要下单的购物车条目（不传默认全部）
    cart_items = cart_service.get_cart(db, user_id)
    if cart_item_ids:
        cart_items = [c for c in cart_items if c["id"] in cart_item_ids]
    cart_items = [c for c in cart_items if c["product"]]
    if not cart_items:
        raise BadRequestError("购物车为空或商品已失效，无法下单")

    # 校验库存并计算总额
    total = 0.0
    for c in cart_items:
        product: Product = c["product"]
        if product.status != "on_sale":
            raise BadRequestError(f"「{product.name}」已下架，请移除后再下单")
        if product.stock < c["quantity"]:
            raise BadRequestError(f"「{product.name}」库存不足，仅剩 {product.stock} 件")
        total += product.price * c["quantity"]

    # 优惠券抵扣（核销：校验归属/状态/门槛）
    discount = 0.0
    coupon = None
    if coupon_id:
        discount, coupon = coupon_service.redeem(db, user_id, coupon_id, total)

    # 扣库存（校验已通过，直接扣减）
    for c in cart_items:
        product_service.adjust_stock(db, c["product"], -c["quantity"])

    order = OrderRepository(db).create(
        user_id=user_id,
        order_no=_gen_order_no(),
        total_amount=round(total - discount, 2),
        discount_amount=discount,
        coupon_id=coupon.id if coupon else None,
        status=ORDER_STATUS_PENDING,
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
            merchant_id=product.tenant_id,
            product_name=product.name,
            image=product.image,
            price=product.price,
            quantity=c["quantity"],
        )
        for c in cart_items
        for product in [c["product"]]
    ])

    # 清掉已下单的购物车条目
    CartRepository(db).remove_by_ids(user_id, [c["id"] for c in cart_items])
    return _serialize(order, OrderRepository(db).items_of(order.id), db=db)


def pay_order(db: Session, user_id: int, order_id: int) -> dict:
    """模拟支付：待付款 → 待发货"""
    order = _get_user_order(db, order_id, user_id)
    if order.status != ORDER_STATUS_PENDING:
        raise BadRequestError("订单当前状态不可支付")
    order.status = ORDER_STATUS_PAID
    order = OrderRepository(db).save(order)
    return _serialize(order, db=db)


def cancel_order(db: Session, user_id: int, order_id: int) -> dict:
    """取消订单（仅待付款）：回补库存 + 退回优惠券"""
    order = _get_user_order(db, order_id, user_id)
    if order.status != ORDER_STATUS_PENDING:
        raise BadRequestError("仅待付款订单可以取消")
    _restore_stock(db, order)
    coupon_service.release_if_any(db, order.id)
    order.status = ORDER_STATUS_CANCELLED
    order = OrderRepository(db).save(order)
    return _serialize(order, db=db)


def confirm_receive(db: Session, user_id: int, order_id: int) -> dict:
    """顾客确认收货：已发货 → 已完成"""
    order = _get_user_order(db, order_id, user_id)
    if order.status != ORDER_STATUS_SHIPPED:
        raise BadRequestError("订单尚未发货或已完成")
    order.status = ORDER_STATUS_DONE
    order = OrderRepository(db).save(order)
    return _serialize(order, db=db)


def ship_order(db: Session, order_id: int, logistics: str,
               merchant_id: int | None) -> dict:
    """商家发货：待发货 → 已发货（仅能发包含自己商品的订单）"""
    repo = OrderRepository(db)
    order = repo.get(order_id)
    if not order:
        raise NotFoundError("订单不存在")
    item_merchant_ids = {i.merchant_id for i in repo.items_of(order.id)}
    if merchant_id not in item_merchant_ids:
        raise ForbiddenError("该订单不包含本店商品")
    if order.status != ORDER_STATUS_PAID:
        raise BadRequestError("订单当前状态不可发货")
    order.status = ORDER_STATUS_SHIPPED
    order.logistics = logistics
    order = repo.save(order)
    return _serialize(order, db=db)


def list_my_orders(db: Session, user_id: int, status: str | None = None) -> list[dict]:
    """顾客订单列表（带明细）"""
    repo = OrderRepository(db)
    orders = repo.list_by_user(user_id, status)
    items = repo.items_of_orders([o.id for o in orders])
    by_order: dict[int, list[OrderItem]] = {}
    for i in items:
        by_order.setdefault(i.order_id, []).append(i)
    return [_serialize(o, by_order.get(o.id, []), db=db) for o in orders]


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


def _get_user_order(db: Session, order_id: int, user_id: int) -> Order:
    order = OrderRepository(db).get(order_id)
    if not order:
        raise NotFoundError("订单不存在")
    if order.user_id != user_id:
        # 越权防护：不泄露订单存在性
        raise NotFoundError("订单不存在")
    return order


def _restore_stock(db: Session, order: Order) -> None:
    """取消订单时按明细回补库存"""
    repo, product_repo = OrderRepository(db), ProductRepository(db)
    for item in repo.items_of(order.id):
        if item.product_id:
            product = product_repo.get(item.product_id)
            if product:
                product_service.adjust_stock(db, product, item.quantity)
