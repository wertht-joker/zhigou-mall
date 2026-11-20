"""订单接口：顾客下单/支付/取消/确认收货 + 商家发货"""
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.order import (
    LogisticsEventCreateRequest,
    MerchantShipRequest,
    OrderCreateRequest,
)
from app.schemas.payment import PaymentCreateRequest
from app.services import order_service

router = APIRouter(tags=["订单"])


@router.post("/orders")
def create_order(
    req: OrderCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下单：购物车结算或立即购买（锁定地址快照、扣库存、核销优惠券）"""
    order = order_service.create_order(
        db, user.id, req.address_id, req.cart_item_ids, req.coupon_id,
        buy_now=req.buy_now.model_dump() if req.buy_now else None,
    )
    return success(order, message="下单成功")


@router.get("/orders")
def list_my_orders(
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的订单列表（分页，带商品明细）"""
    items, total = order_service.list_my_orders(
        db, user.id, status, page, page_size
    )
    return success({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/orders/{order_id}")
def get_my_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """订单详情（仅本人可见，越权 404）"""
    return success(order_service.get_my_order(db, user.id, order_id))


@router.post("/orders/{order_id}/pay")
def pay_order(
    order_id: int,
    req: PaymentCreateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """一步支付（兼容旧客户端）：默认支付宝，创建支付单并立即确认"""
    method = req.method if req else "alipay"
    return success(
        order_service.pay_order(db, user.id, order_id, method),
        message="支付成功",
    )


# ===== 支付流水 =====

@router.post("/orders/{order_id}/payments")
def create_payment(
    order_id: int,
    req: PaymentCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发起支付：选择支付方式，生成待支付流水（支持 Idempotency-Key 幂等）"""
    payment = order_service.create_payment(
        db, user.id, order_id, req.method, idempotency_key
    )
    return success(payment, message="支付单已创建")


@router.get("/orders/{order_id}/payments")
def list_order_payments(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """订单支付流水（仅本人可见）"""
    return success(order_service.list_order_payments(db, user.id, order_id))


@router.post("/payments/{payment_no}/confirm")
def confirm_payment(
    payment_no: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认支付（模拟支付网关回调）：流水成功 + 订单转待发货，重复确认幂等"""
    result = order_service.confirm_payment(db, user.id, payment_no)
    return success(result, message="支付成功")


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """取消订单（仅待付款）：回补库存"""
    return success(order_service.cancel_order(db, user.id, order_id), message="订单已取消")


@router.post("/orders/{order_id}/confirm")
def confirm_receive(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认收货：已发货 → 已完成"""
    return success(order_service.confirm_receive(db, user.id, order_id), message="已确认收货")


# ===== 商家发货 =====

@router.get("/merchant/orders")
def list_merchant_orders(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家订单列表：包含本店商品的订单（明细只展示本店部分）"""
    return success(order_service.list_merchant_orders(db, tenant.id, status))


@router.post("/merchant/orders/{order_id}/ship")
def ship_order(
    order_id: int,
    req: MerchantShipRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家发货：待发货 → 已发货"""
    order = order_service.ship_order(
        db, order_id,
        logistics_company=req.logistics_company,
        tracking_no=req.tracking_no,
        merchant_id=tenant.id,
        logistics=req.logistics,
    )
    return success(order, message="发货成功")


@router.post("/merchant/orders/{order_id}/logistics-events")
def add_logistics_event(
    order_id: int,
    req: LogisticsEventCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家更新物流状态：已揽收 / 运输中 / 派送中 / 已签收"""
    order = order_service.add_logistics_event(
        db, order_id, tenant.id,
        status=req.status,
        description=req.description,
        location=req.location,
    )
    return success(order, message="物流状态已更新")
