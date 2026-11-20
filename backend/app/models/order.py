"""订单模型（电商主流程）：订单头 + 订单明细

订单归属顾客（user_id）；明细冗余商品名/单价快照，并记录 merchant_id，
商家可按明细定位「含我商品的订单」进行发货。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base

# 订单状态机：待付款 → 待发货 → 已发货 → 已完成；待付款可取消
ORDER_STATUS_PENDING = "待付款"
ORDER_STATUS_PAID = "待发货"
ORDER_STATUS_SHIPPED = "已发货"
ORDER_STATUS_DONE = "已完成"
ORDER_STATUS_CANCELLED = "已取消"
ORDER_STATUSES = [
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PAID,
    ORDER_STATUS_SHIPPED,
    ORDER_STATUS_DONE,
    ORDER_STATUS_CANCELLED,
]


class Order(Base):
    """订单头"""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_expire", "status", "expire_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 下单顾客
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 平台订单号，对外唯一标识（顾客报单号给客服查询）
    order_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    # 订单总额（元，已扣优惠券抵扣）
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    # 优惠券抵扣金额（元）
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0)
    # 本单核销的优惠券 ID
    coupon_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 状态：待付款 / 待发货 / 已发货 / 已完成 / 已取消
    status: Mapped[str] = mapped_column(String(20), default=ORDER_STATUS_PENDING)
    # 收货信息快照（下单时锁定，不随地址簿变化）
    receiver_name: Mapped[str] = mapped_column(String(50), default="")
    receiver_phone: Mapped[str] = mapped_column(String(20), default="")
    receiver_address: Mapped[str] = mapped_column(String(255), default="")
    # 物流信息，发货时填写
    logistics: Mapped[str] = mapped_column(String(100), default="")
    # 物流公司 / 运单号 / 发货时间 / 预计送达
    logistics_company: Mapped[str] = mapped_column(String(50), default="")
    tracking_no: Mapped[str] = mapped_column(String(50), default="")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # 支付方式（alipay / wechat / unionpay），支付成功后写入
    payment_method: Mapped[str] = mapped_column(String(20), default="")
    # 支付完成时间
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 待付款订单的支付截止时间：超时由后台任务自动取消并回补库存
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OrderItem(Base):
    """订单明细（商品快照）"""

    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order", "order_id"),
        Index("ix_order_items_merchant", "merchant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 所选规格（可空）及其名称快照
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variant_spec: Mapped[str] = mapped_column(String(100), default="")
    # 商品所属商家（商家据此圈定自己的订单）
    merchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 下单时的商品快照（商品后续改名/改价不影响历史订单）
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    image: Mapped[str] = mapped_column(String(20), default="📦")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class OrderLogisticsEvent(Base):
    """物流轨迹节点（发货时预生成，按时间逐步对外可见）"""

    __tablename__ = "order_logistics_events"
    __table_args__ = (
        Index("ix_logistics_order_time", "order_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(100), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
