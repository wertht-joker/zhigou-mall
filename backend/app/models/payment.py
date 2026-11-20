"""支付流水模型：一次支付尝试对应一条流水

订单与支付解耦：
- 订单负责交易状态机（待付款 → 待发货 → ...）
- 支付流水负责「这笔钱有没有收到」：支付方式、支付单状态、幂等键、支付时间

真实接入支付网关时，创建支付单 = 向网关预下单；确认支付 = 网关异步回调验签后
把流水置为 success，并驱动订单状态流转。本项目用模拟确认接口复现该链路。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base

# 支付单状态
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_SUCCESS = "success"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_STATUS_CLOSED = "closed"

# 支付方式：存英文码，展示用中文标签
PAYMENT_METHOD_LABELS = {
    "alipay": "支付宝",
    "wechat": "微信支付",
    "unionpay": "银联",
}


class Payment(Base):
    """支付流水（归属顾客 user_id，关联订单 order_id）"""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_order", "order_id"),
        Index("ix_payments_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 支付单号（对外唯一标识，模拟支付时展示）
    payment_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    # alipay / wechat / unionpay
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    # pending / success / failed / closed
    status: Mapped[str] = mapped_column(String(20), default=PAYMENT_STATUS_PENDING)
    # 幂等键（客户端重复提交时复用同一支付单）
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
