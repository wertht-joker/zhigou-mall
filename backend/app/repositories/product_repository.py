"""商品仓储"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.repositories.base import BaseRepository, apply_tenant, scoped


class ProductRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, product_id: int) -> Product | None:
        return self.db.query(Product).filter(Product.id == product_id).first()

    def get_by_name(self, name: str) -> Product | None:
        return self.db.query(Product).filter(Product.name == name).first()

    def list_public(self, keyword: str | None = None,
                    category_id: int | None = None) -> list[Product]:
        """前台商品列表：全平台在售商品，按销量倒序（不按商家过滤）"""
        query = self.db.query(Product).filter(Product.status == "on_sale")
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                Product.name.like(like) | Product.subtitle.like(like)
            )
        if category_id:
            query = query.filter(Product.category_id == category_id)
        return query.order_by(Product.sales.desc(), Product.id.desc()).all()

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


class ProductCategoryRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def list(self) -> list[ProductCategory]:
        return self.db.query(ProductCategory).order_by(ProductCategory.sort).all()

    def get(self, category_id: int) -> ProductCategory | None:
        return self.db.query(ProductCategory).filter(
            ProductCategory.id == category_id
        ).first()

    def create(self, name: str, icon: str = "🛒", sort: int = 0) -> ProductCategory:
        category = ProductCategory(name=name, icon=icon, sort=sort)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
