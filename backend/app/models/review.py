"""商品评价模型（京东式：确认收货后凭订单明细评价，一单一评，商家可回复）"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Review(Base):
    """商品评价（归属顾客 user_id，锚定订单明细 order_item_id）"""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_review_order_item"),
        Index("ix_reviews_product_created", "product_id", "created_at"),
        Index("ix_reviews_merchant", "merchant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 评价人（顾客）
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 被评价的商品与其商家（商家据此圈定自己店铺的评价）
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    merchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 评价来源订单与明细（一单明细只能评价一次）
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 星级 1~5
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    # 评价内容
    content: Mapped[str] = mapped_column(Text, default="")
    # 商家回复
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
