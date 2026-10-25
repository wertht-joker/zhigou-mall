"""收货地址模型"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Address(Base):
    """收货地址（归属顾客 user_id）"""

    __tablename__ = "addresses"
    __table_args__ = (Index("ix_addresses_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    receiver: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    # 所在地区（省市区）
    region: Mapped[str] = mapped_column(String(100), default="")
    # 详细地址
    detail: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
