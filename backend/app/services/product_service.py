"""商品服务：前台浏览（全平台）+ 商家管理（租户隔离）"""
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.product import Product
from app.repositories.product_repository import ProductCategoryRepository, ProductRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.tenant_repository import TenantRepository

# 默认租户即平台自营，前台展示用
PLATFORM_STORE_LABEL = "智购自营"


def serialize_public(product: Product, db: Session, stats: dict | None = None) -> dict:
    """前台商品序列化：附店铺名称 + 评价统计（评分/评价数）"""
    data = {k: v for k, v in product.__dict__.items() if not k.startswith("_")}
    if product.tenant_id is None:
        data["store_name"] = PLATFORM_STORE_LABEL
    else:
        tenant = TenantRepository(db).get(product.tenant_id)
        data["store_name"] = (
            PLATFORM_STORE_LABEL
            if tenant is None or tenant.code == "default"
            else tenant.name
        )
    if stats is None:
        stats = ReviewRepository(db).stats_by_product(product.id)
    data["review_count"] = stats["total"]
    data["avg_rating"] = stats["avg_rating"]
    return data


def list_categories(db: Session) -> list:
    return ProductCategoryRepository(db).list()


def list_products(db: Session, keyword: str | None = None,
                  category_id: int | None = None) -> list[Product]:
    """前台商品列表：全平台在售商品（不区分商家），按销量排序"""
    return ProductRepository(db).list_public(keyword, category_id)


def get_product(db: Session, product_id: int) -> Product:
    """商品详情（前台可见，含下架商品以便历史订单回溯展示）"""
    product = ProductRepository(db).get(product_id)
    if not product:
        raise NotFoundError("商品不存在")
    return product


def list_merchant_products(db: Session, keyword: str | None,
                           tenant_id: int | None) -> list[Product]:
    """商家后台：本店商品（强制租户过滤）"""
    return ProductRepository(db).list_merchant(keyword, tenant_id)


def create_product(db: Session, fields: dict, tenant_id: int | None) -> Product:
    """商家上新（归属本商家）"""
    repo = ProductRepository(db)
    _validate_category(db, fields.get("category_id"))
    return repo.create(**fields, tenant_id=tenant_id)


def update_product(db: Session, product_id: int, fields: dict,
                   tenant_id: int | None) -> Product:
    """商家改价/改库存/上下架等（只能改自己的商品）"""
    repo = ProductRepository(db)
    product = _get_owned(repo, product_id, tenant_id)
    if fields.get("category_id") is not None:
        _validate_category(db, fields["category_id"])
    for key, value in fields.items():
        setattr(product, key, value)
    return repo.save(product)


def delete_product(db: Session, product_id: int, tenant_id: int | None) -> None:
    """商家删除商品（演示实现为物理删除）"""
    repo = ProductRepository(db)
    product = _get_owned(repo, product_id, tenant_id)
    repo.delete(product)


def _get_owned(repo: ProductRepository, product_id: int,
               tenant_id: int | None) -> Product:
    product = repo.get(product_id)
    if not product:
        raise NotFoundError("商品不存在")
    # 越权防护：跨商家操作一律 404，不泄露资源存在性
    if tenant_id is not None and product.tenant_id != tenant_id:
        raise NotFoundError("商品不存在")
    if tenant_id is None and product.tenant_id is not None:
        raise ForbiddenError("无权操作该商品")
    return product


def _validate_category(db: Session, category_id: int | None) -> None:
    if category_id is not None and not ProductCategoryRepository(db).get(category_id):
        raise BadRequestError("商品分类不存在")


def adjust_stock(db: Session, product: Product, delta: int) -> None:
    """下单扣减 / 取消回补库存，调用方保证在订单事务里使用"""
    if product.stock + delta < 0:
        raise BadRequestError(f"「{product.name}」库存不足")
    product.stock += delta
