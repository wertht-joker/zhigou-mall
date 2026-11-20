"""商品与商品分类模型"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class ProductCategory(Base):
    """商品分类（平台级，全商家共用）"""

    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # 分类图标（emoji，演示用）
    icon: Mapped[str] = mapped_column(String(20), default="🛒")
    # 排序权重，小的在前
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Product(Base):
    """商品（归属商家 tenant_id，前台对全平台可见）"""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_tenant_created", "tenant_id", "created_at"),
        Index("ix_products_category", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属商家（多租户隔离边界：商家只能管理自己的商品）
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 卖点副标题（商品卡片第二行）
    subtitle: Mapped[str] = mapped_column(String(200), default="")
    # 图文详情
    description: Mapped[str] = mapped_column(Text, default="")
    # 售价（元）
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 划线原价（可空）
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 库存
    stock: Mapped[int] = mapped_column(Integer, default=0)
    # 累计销量（演示排序用）
    sales: Mapped[int] = mapped_column(Integer, default=0)
    # 商品主图（emoji，演示用；生产环境为图片 URL）
    image: Mapped[str] = mapped_column(String(20), default="📦")
    # 实物宣传图 URL（可为后端静态资源 /static/... 或外链；为空时前端回退 emoji）
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 状态：on_sale 在售 / off_sale 下架
    status: Mapped[str] = mapped_column(String(20), default="on_sale")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProductVariant(Base):
    """商品规格/SKU（如手机 128G / 256G，各自独立价格与库存）

    有规格的商品：Product.price 取最低规格价用于列表展示，
    Product.stock 为各规格库存之和；下单时按具体规格计价并扣减规格库存。
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "spec", name="uq_product_variants_spec"),
        Index("ix_product_variants_product", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 规格名（如 "16GB+512GB 曜石黑"）
    spec: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
