"""购物车模型"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class CartItem(Base):
    """购物车条目（归属顾客 user_id，同商品合并数量）"""

    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "product_id", "variant_id",
            name="uq_cart_user_product_variant",
        ),
        Index("ix_cart_items_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 所选规格；无规格商品为 None
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
