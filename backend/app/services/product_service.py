"""商品服务：前台浏览（全平台）+ 商家管理（租户隔离）"""
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.cart import CartItem
from app.models.product import Product, ProductVariant
from app.repositories.product_repository import (
    ProductCategoryRepository,
    ProductRepository,
    ProductVariantRepository,
)
from app.repositories.review_repository import ReviewRepository
from app.repositories.tenant_repository import TenantRepository

# 默认租户即平台自营，前台展示用
PLATFORM_STORE_LABEL = "智购自营"

# 商家上传的商品主图：落在 static 下（与种子实物图同源，/static 已挂载）
PRODUCT_IMAGE_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads" / "products"
PRODUCT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def serialize_variant(variant: ProductVariant) -> dict:
    """规格序列化（价格/库存/规格名）"""
    return {
        "id": variant.id,
        "product_id": variant.product_id,
        "spec": variant.spec,
        "price": variant.price,
        "original_price": variant.original_price,
        "stock": variant.stock,
    }


def list_variants(db: Session, product_id: int) -> list[ProductVariant]:
    return ProductVariantRepository(db).list_by_product(product_id)


def serialize_public(product: Product, db: Session, stats: dict | None = None,
                     with_variants: bool = False) -> dict:
    """前台商品序列化：附店铺名称 + 评价统计（评分/评价数）

    with_variants=True 时（详情页）返回规格列表；列表页不查规格，避免 N+1。
    """
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
    variants = list_variants(db, product.id) if with_variants else []
    data["has_variants"] = bool(variants)
    data["variants"] = [serialize_variant(v) for v in variants]
    return data


def serialize_merchant(product: Product, db: Session) -> dict:
    """商家后台商品序列化：附带全部规格（用于编辑回填）"""
    data = {k: v for k, v in product.__dict__.items() if not k.startswith("_")}
    variants = list_variants(db, product.id)
    data["has_variants"] = bool(variants)
    data["variants"] = [serialize_variant(v) for v in variants]
    return data


def list_categories(db: Session) -> list:
    return ProductCategoryRepository(db).list()


def list_products(db: Session, keyword: str | None = None,
                  category_id: int | None = None,
                  page: int = 1, page_size: int = 12) -> tuple[list[Product], int]:
    """前台商品列表：全平台在售商品，按销量排序，分页返回 (商品, 总数)"""
    repo = ProductRepository(db)
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 60)
    products = repo.list_public(
        keyword, category_id, offset=(page - 1) * page_size, limit=page_size
    )
    return products, repo.count_public(keyword, category_id)


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
    """商家上新（归属本商家）；可同时创建多规格"""
    fields = dict(fields)
    variants = fields.pop("variants", None)
    repo = ProductRepository(db)
    _validate_category(db, fields.get("category_id"))
    product = repo.create(**fields, tenant_id=tenant_id)
    if variants:
        sync_variants(db, product, variants)
        product = repo.get(product.id)
    return product


def update_product(db: Session, product_id: int, fields: dict,
                   tenant_id: int | None) -> Product:
    """商家改价/改库存/上下架等（只能改自己的商品）

    variants 为 None 表示不改规格；[] 表示清空规格；有值则同步规格。
    """
    fields = dict(fields)
    variants = fields.pop("variants", None)
    repo = ProductRepository(db)
    product = _get_owned(repo, product_id, tenant_id)
    if fields.get("category_id") is not None:
        _validate_category(db, fields["category_id"])
    for key, value in fields.items():
        setattr(product, key, value)
    product = repo.save(product)
    if variants is not None:
        sync_variants(db, product, variants)
        product = repo.get(product.id)
    return product


def delete_product(db: Session, product_id: int, tenant_id: int | None) -> None:
    """商家删除商品（演示实现为物理删除），连带规格"""
    repo = ProductRepository(db)
    product = _get_owned(repo, product_id, tenant_id)
    ProductVariantRepository(db).delete_by_product(product.id)
    repo.delete(product)


def save_product_image(db: Session, product_id: int, upload,
                       tenant_id: int | None) -> dict:
    """商家上传商品主图：校验类型/大小后落盘到 static/uploads/products

    只改 image_url（实物图），emoji 字段保留作为无图时的兜底展示。
    """
    repo = ProductRepository(db)
    product = _get_owned(repo, product_id, tenant_id)

    content_type = (upload.content_type or "").lower()
    ext = _IMAGE_EXT_BY_TYPE.get(content_type)
    if not ext:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            raise BadRequestError("仅支持 JPG / PNG / WEBP / GIF 图片")
        ext = ".jpg" if suffix == ".jpeg" else suffix

    data = upload.file.read(PRODUCT_IMAGE_MAX_BYTES + 1)
    if not data:
        raise BadRequestError("图片内容为空")
    if len(data) > PRODUCT_IMAGE_MAX_BYTES:
        raise BadRequestError("图片大小不能超过 5MB")

    PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{product.id}-{uuid.uuid4().hex}{ext}"
    (PRODUCT_IMAGE_DIR / name).write_bytes(data)
    product.image_url = f"/static/uploads/products/{name}"
    repo.save(product)
    return serialize_merchant(product, db)


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


def deduct_stock(db: Session, product_id: int, quantity: int) -> bool:
    """原子扣减库存（防超卖的关键）

    UPDATE products SET stock = stock - n
     WHERE id = ? AND status = 'on_sale' AND stock >= n

    以影响行数判定成败：两个并发下单同时看到"库存 1"时，
    只有第一个能把 stock 减到 0，第二个影响行数为 0 → 下单失败。
    相比"先查库存再改"的两步窗口，条件更新把判断与扣减压在同一条 SQL 里。
    """
    if quantity <= 0:
        raise BadRequestError("扣减数量必须大于 0")
    rows = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.status == "on_sale",
            Product.stock >= quantity,
        )
        .update(
            {Product.stock: Product.stock - quantity},
            synchronize_session=False,
        )
    )
    return rows == 1


def adjust_stock(db: Session, product: Product, delta: int) -> None:
    """库存增减（取消回补 / 补偿重放使用，不做并发抢占）"""
    if product.stock + delta < 0:
        raise BadRequestError(f"「{product.name}」库存不足")
    product.stock += delta


# ===== 多规格（SKU） =====

def sync_variants(db: Session, product: Product, variants: list[dict]) -> None:
    """同步商品规格：带 id 更新、不带 id 新建、列表缺席的删除

    有规格时自动回写商品汇总：price = 最低规格价，stock = 各规格库存之和，
    保证前台列表展示的价格与库存和规格一致。
    """
    specs = [str(v["spec"]).strip() for v in variants]
    if len(specs) != len(set(specs)):
        raise BadRequestError("规格名称不能重复")

    repo = ProductVariantRepository(db)
    existing = {v.id: v for v in repo.list_by_product(product.id)}
    kept: set[int] = set()
    for raw in variants:
        variant_id = raw.get("id")
        if variant_id is not None:
            variant = existing.get(variant_id)
            if not variant:
                raise BadRequestError("规格不存在或不属于该商品")
            variant.spec = str(raw["spec"]).strip()
            variant.price = float(raw["price"])
            variant.original_price = raw.get("original_price")
            variant.stock = int(raw.get("stock", 0))
            kept.add(variant.id)
        else:
            created = repo.create(
                product_id=product.id,
                spec=str(raw["spec"]).strip(),
                price=float(raw["price"]),
                original_price=raw.get("original_price"),
                stock=int(raw.get("stock", 0)),
            )
            kept.add(created.id)

    # 删除缺席规格，并清理引用这些规格的购物车条目
    removed_ids = [vid for vid in existing if vid not in kept]
    if removed_ids:
        db.query(CartItem).filter(CartItem.variant_id.in_(removed_ids)).delete(
            synchronize_session=False
        )
        for vid in removed_ids:
            db.delete(existing[vid])
    db.commit()

    remaining = repo.list_by_product(product.id)
    if remaining:
        product.price = min(v.price for v in remaining)
        product.stock = sum(v.stock for v in remaining)
        ProductRepository(db).save(product)


def resolve_variant(db: Session, product: Product,
                    variant_id: int | None) -> ProductVariant | None:
    """解析并校验所选规格：有规格的商品必须选，且规格必须属于该商品"""
    variants = list_variants(db, product.id)
    if not variants:
        if variant_id is not None:
            raise BadRequestError("该商品无需选择规格")
        return None
    if variant_id is None:
        raise BadRequestError("请选择商品规格")
    variant = next((v for v in variants if v.id == variant_id), None)
    if not variant:
        raise BadRequestError("所选规格不存在，请重新选择")
    return variant


def deduct_variant_stock(db: Session, variant_id: int, quantity: int) -> bool:
    """规格库存原子扣减（与商品汇总库存同时扣，防超卖）"""
    if quantity <= 0:
        raise BadRequestError("扣减数量必须大于 0")
    rows = (
        db.query(ProductVariant)
        .filter(
            ProductVariant.id == variant_id,
            ProductVariant.stock >= quantity,
        )
        .update(
            {ProductVariant.stock: ProductVariant.stock - quantity},
            synchronize_session=False,
        )
    )
    return rows == 1


def adjust_variant_stock(db: Session, variant: ProductVariant, delta: int) -> None:
    """规格库存增减（取消/售后回补）"""
    if variant.stock + delta < 0:
        raise BadRequestError(f"规格「{variant.spec}」库存不足")
    variant.stock += delta


def restore_item_stock(db: Session, product_id: int | None,
                       variant_id: int | None, quantity: int) -> None:
    """按订单明细快照回补库存（商品汇总 + 规格）"""
    if not product_id:
        return
    product = ProductRepository(db).get(product_id)
    if not product:
        return
    adjust_stock(db, product, quantity)
    if variant_id:
        variant = ProductVariantRepository(db).get(variant_id)
        if variant:
            adjust_variant_stock(db, variant, quantity)
