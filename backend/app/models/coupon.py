"""优惠券模型：用户领取后归属本人，下单满足门槛时抵扣

每档券（满 X 减 Y）每用户限领一张；下单核销后与订单绑定，
订单取消时自动退回为未使用。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base

# 券状态
COUPON_UNUSED = "unused"
COUPON_USED = "used"


class Coupon(Base):
    """用户优惠券"""

    __tablename__ = "coupons"
    __table_args__ = (Index("ix_coupons_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 归属用户
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 券名（如 双11狂欢满减券）
    title: Mapped[str] = mapped_column(String(50), default="优惠券")
    # 使用门槛（满 X 元可用）
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    # 抵扣金额（减 Y 元）
    discount: Mapped[float] = mapped_column(Float, nullable=False)
    # 状态：unused 未使用 / used 已核销
    status: Mapped[str] = mapped_column(String(20), default=COUPON_UNUSED)
    # 核销于哪笔订单（取消订单时据此退回）
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
