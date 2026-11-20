"""商品仓储"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory, ProductVariant
from app.repositories.base import BaseRepository, apply_tenant, scoped


class ProductRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, product_id: int) -> Product | None:
        return self.db.query(Product).filter(Product.id == product_id).first()

    def get_by_name(self, name: str) -> Product | None:
        return self.db.query(Product).filter(Product.name == name).first()

    def _public_query(self, keyword: str | None = None,
                      category_id: int | None = None):
        """前台可见范围：仅上架商品 + 可选关键词/分类过滤"""
        query = self.db.query(Product).filter(Product.status == "on_sale")
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                Product.name.like(like) | Product.subtitle.like(like)
            )
        if category_id:
            query = query.filter(Product.category_id == category_id)
        return query

    def list_public(self, keyword: str | None = None,
                    category_id: int | None = None,
                    offset: int = 0,
                    limit: int | None = None) -> list[Product]:
        """前台商品列表：全平台在售商品，按销量倒序（不按商家过滤）

        limit 为空表示不分页（内部工具/兼容调用）；列表接口传 limit 做分页。
        """
        query = self._public_query(keyword, category_id).order_by(
            Product.sales.desc(), Product.id.desc()
        )
        if limit is not None:
            query = query.offset(offset).limit(limit)
        return query.all()

    def count_public(self, keyword: str | None = None,
                     category_id: int | None = None) -> int:
        """前台商品总数（分页时返回给前端）"""
        return self._public_query(keyword, category_id).count()

    def list_all(self, keyword: str | None = None,
                 status: str | None = None) -> list[Product]:
        """平台监管：全平台商品（含下架），不按商家过滤"""
        query = self.db.query(Product)
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                Product.name.like(like) | Product.subtitle.like(like)
            )
        if status:
            query = query.filter(Product.status == status)
        return query.order_by(Product.created_at.desc(), Product.id.desc()).all()

    def list_merchant(self, keyword: str | None = None,
                      tenant_id: int | None = None) -> list[Product]:
        """商家后台商品列表：强制限定本商家（含下架商品）"""
        query = scoped(self.db.query(Product), Product, tenant_id)
        if keyword:
            query = query.filter(Product.name.like(f"%{keyword}%"))
        return query.order_by(Product.created_at.desc()).all()

    def search_on_sale(self, keyword: str, limit: int = 5) -> list[Product]:
        """给 AI 导购工具用的轻量搜索：名称/副标题模糊匹配在售商品"""
        like = f"%{keyword}%"
        return (
            self.db.query(Product)
            .filter(Product.status == "on_sale")
            .filter(Product.name.like(like) | Product.subtitle.like(like))
            .order_by(Product.sales.desc())
            .limit(limit)
            .all()
        )

    def create(self, **fields) -> Product:
        product = Product(**fields)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def save(self, product: Product) -> Product:
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        self.db.delete(product)
        self.db.commit()


class ProductVariantRepository(BaseRepository):
    """商品规格数据访问"""

    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, variant_id: int) -> ProductVariant | None:
        return (
            self.db.query(ProductVariant)
            .filter(ProductVariant.id == variant_id)
            .first()
        )

    def list_by_product(self, product_id: int) -> list[ProductVariant]:
        return (
            self.db.query(ProductVariant)
            .filter(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.price, ProductVariant.id)
            .all()
        )

    def create(self, **fields) -> ProductVariant:
        variant = ProductVariant(**fields)
        self.db.add(variant)
        self.db.commit()
        self.db.refresh(variant)
        return variant

    def save(self, variant: ProductVariant) -> ProductVariant:
        self.db.commit()
        self.db.refresh(variant)
        return variant

    def delete(self, variant: ProductVariant) -> None:
        self.db.delete(variant)
        self.db.commit()

    def delete_by_product(self, product_id: int) -> None:
        self.db.query(ProductVariant).filter(
            ProductVariant.product_id == product_id
        ).delete(synchronize_session=False)
        self.db.commit()


class ProductCategoryRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def list(self) -> list[ProductCategory]:
        return self.db.query(ProductCategory).order_by(ProductCategory.sort).all()

    def get(self, category_id: int) -> ProductCategory | None:
        return self.db.query(ProductCategory).filter(
            ProductCategory.id == category_id
        ).first()

    def get_by_name(self, name: str) -> ProductCategory | None:
        return self.db.query(ProductCategory).filter(
            ProductCategory.name == name
        ).first()

    def create(self, name: str, icon: str = "🛒", sort: int = 0) -> ProductCategory:
        category = ProductCategory(name=name, icon=icon, sort=sort)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def save(self, category: ProductCategory) -> ProductCategory:
        self.db.commit()
        self.db.refresh(category)
        return category

    def delete(self, category: ProductCategory) -> None:
        self.db.delete(category)
        self.db.commit()
