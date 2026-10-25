"""优惠券服务：领取 / 我的券 / 下单抵扣 / 取消退回

档位与双11活动横幅一致：满 199 减 30、满 399 减 80、满 699 减 150，
每档每用户限领一张。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.models.coupon import COUPON_UNUSED, COUPON_USED, Coupon
from app.repositories.coupon_repository import CouponRepository

# (门槛, 抵扣) 档位配置
COUPON_TIERS: list[tuple[float, float]] = [(199, 30), (399, 80), (699, 150)]
COUPON_TITLE = "双11狂欢满减券"


def _serialize(coupon: Coupon) -> dict:
    return {
        "id": coupon.id,
        "title": coupon.title,
        "threshold": coupon.threshold,
        "discount": coupon.discount,
        "status": coupon.status,
        "order_id": coupon.order_id,
        "claimed_at": coupon.claimed_at.isoformat() if coupon.claimed_at else None,
        "used_at": coupon.used_at.isoformat() if coupon.used_at else None,
    }


def list_tiers() -> list[dict]:
    """活动券档位（横幅/领券页展示用）"""
    return [{"threshold": t, "discount": d} for t, d in COUPON_TIERS]


def list_my(db: Session, user_id: int) -> list[dict]:
    return [_serialize(c) for c in CouponRepository(db).list_by_user(user_id)]


def claim(db: Session, user_id: int, threshold: float) -> dict:
    """领取指定档位券（每档限领一张）"""
    tier = next((t for t in COUPON_TIERS if t[0] == threshold), None)
    if not tier:
        raise NotFoundError("优惠券档位不存在")
    if CouponRepository(db).find_by_tier(user_id, threshold):
        raise BadRequestError("该档位优惠券已领取过啦")
    coupon = CouponRepository(db).create(
        user_id=user_id,
        title=COUPON_TITLE,
        threshold=tier[0],
        discount=tier[1],
        status=COUPON_UNUSED,
    )
    return _serialize(coupon)


def usable_for(db: Session, user_id: int, subtotal: float) -> list[dict]:
    """结算页可选的券：未使用且门槛 <= 当前金额"""
    return [
        _serialize(c) for c in CouponRepository(db).list_usable(user_id, subtotal)
    ]


def redeem(db: Session, user_id: int, coupon_id: int, subtotal: float) -> tuple[float, Coupon]:
    """下单核销：校验归属/状态/门槛，返回抵扣金额并绑定订单由调用方回填

    抵扣不超过订单金额（最低支付 0 元）。
    """
    coupon = CouponRepository(db).get(coupon_id)
    if not coupon or coupon.user_id != user_id:
        raise NotFoundError("优惠券不存在")
    if coupon.status != COUPON_UNUSED:
        raise BadRequestError("优惠券已被使用")
    if subtotal < coupon.threshold:
        raise BadRequestError(f"该券满 {coupon.threshold:g} 元可用，还差 {coupon.threshold - subtotal:g} 元")
    discount = min(coupon.discount, subtotal)
    coupon.status = COUPON_USED
    coupon.used_at = datetime.now()
    CouponRepository(db).save(coupon)
    return round(discount, 2), coupon


def release_if_any(db: Session, order_id: int) -> None:
    """取消订单时退回本单核销的优惠券（重新变为未使用）"""
    coupon = CouponRepository(db).find_by_order(order_id)
    if coupon and coupon.status == COUPON_USED:
        coupon.status = COUPON_UNUSED
        coupon.order_id = None
        coupon.used_at = None
        CouponRepository(db).save(coupon)


def bind_order(db: Session, coupon: Coupon, order_id: int) -> None:
    """核销后绑定订单号（取消时据此退回）"""
    coupon.order_id = order_id
    CouponRepository(db).save(coupon)
