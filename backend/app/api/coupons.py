"""优惠券接口：领券 + 我的优惠券"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import success
from app.models.database import get_db
from app.models.user import User
from app.schemas.coupon import CouponClaimRequest
from app.services import coupon_service

router = APIRouter(tags=["优惠券"])


@router.get("/coupons/tiers")
def list_tiers():
    """活动券档位配置（无需登录，横幅展示用）"""
    return success(coupon_service.list_tiers())


@router.get("/coupons")
def list_my_coupons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的优惠券（含已使用）"""
    return success(coupon_service.list_my(db, user.id))


@router.post("/coupons/claim")
def claim_coupon(
    req: CouponClaimRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """领取指定档位的满减券（每档限领一张）"""
    coupon = coupon_service.claim(db, user.id, req.threshold)
    return success(coupon, message="领取成功")
