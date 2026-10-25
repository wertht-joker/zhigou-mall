"""订单接口：顾客下单/支付/取消/确认收货 + 商家发货"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.order import MerchantShipRequest, OrderCreateRequest
from app.services import order_service

router = APIRouter(tags=["订单"])


@router.post("/orders")
def create_order(
    req: OrderCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从购物车下单（锁定地址快照、扣库存、核销优惠券、清理已购条目）"""
    order = order_service.create_order(db, user.id, req.address_id, req.cart_item_ids, req.coupon_id)
    return success(order, message="下单成功")


@router.get("/orders")
def list_my_orders(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的订单列表（带商品明细）"""
    return success(order_service.list_my_orders(db, user.id, status))


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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """模拟支付：待付款 → 待发货"""
    return success(order_service.pay_order(db, user.id, order_id), message="支付成功")


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
    order = order_service.ship_order(db, order_id, req.logistics, tenant.id)
    return success(order, message="发货成功")
