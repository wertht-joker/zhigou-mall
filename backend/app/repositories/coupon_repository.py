"""优惠券仓储：按用户查询 / 按档位判重 / 核销与退回"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.coupon import COUPON_UNUSED, Coupon
from app.repositories.base import BaseRepository


class CouponRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, coupon_id: int) -> Coupon | None:
        return self.db.query(Coupon).filter(Coupon.id == coupon_id).first()

    def list_by_user(self, user_id: int, status: str | None = None) -> list[Coupon]:
        query = self.db.query(Coupon).filter(Coupon.user_id == user_id)
        if status:
            query = query.filter(Coupon.status == status)
        return query.order_by(Coupon.claimed_at.desc()).all()

    def find_by_tier(self, user_id: int, threshold: float) -> Coupon | None:
        """每档券每用户限领一张：按门槛金额定位档位"""
        return (
            self.db.query(Coupon)
            .filter(Coupon.user_id == user_id, Coupon.threshold == threshold)
            .first()
        )

    def find_by_order(self, order_id: int) -> Coupon | None:
        """取消订单时按订单找回被核销的券"""
        return self.db.query(Coupon).filter(Coupon.order_id == order_id).first()

    def list_usable(self, user_id: int, subtotal: float) -> list[Coupon]:
        """下单可选：未使用且门槛不超过当前金额"""
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.user_id == user_id,
                Coupon.status == COUPON_UNUSED,
                Coupon.threshold <= subtotal,
            )
            .order_by(Coupon.discount.desc())
            .all()
        )

    def create(self, **fields) -> Coupon:
        coupon = Coupon(**fields)
        self.db.add(coupon)
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def save(self, coupon: Coupon) -> Coupon:
        self.db.commit()
        self.db.refresh(coupon)
        return coupon
