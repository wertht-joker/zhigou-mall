"""购物车服务（按商品规格区分条目）"""
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.repositories.cart_repository import CartRepository
from app.repositories.product_repository import (
    ProductRepository,
    ProductVariantRepository,
)

MAX_QUANTITY_PER_ITEM = 99


def _serialize_variant(variant) -> dict | None:
    if not variant:
        return None
    return {
        "id": variant.id,
        "product_id": variant.product_id,
        "spec": variant.spec,
        "price": variant.price,
        "original_price": variant.original_price,
        "stock": variant.stock,
    }


def get_cart(db: Session, user_id: int) -> list[dict]:
    """购物车列表：条目带商品、所选规格、成交单价与可购库存"""
    repo, product_repo = CartRepository(db), ProductRepository(db)
    variant_repo = ProductVariantRepository(db)
    result = []
    for item in repo.list(user_id):
        product = product_repo.get(item.product_id)
        variant = variant_repo.get(item.variant_id) if item.variant_id else None
        # 规格已删除或不属于该商品：整条按失效处理，避免按错误价格下单
        if variant and (not product or variant.product_id != product.id):
            variant = None
        if item.variant_id and not variant:
            product = None
        result.append({
            "id": item.id,
            "product_id": item.product_id,
            "variant_id": item.variant_id,
            "quantity": item.quantity,
            "variant": _serialize_variant(variant),
            "unit_price": variant.price if variant else (product.price if product else 0.0),
            "stock": variant.stock if variant else (product.stock if product else 0),
            "product": product,
        })
    return result


def add_to_cart(db: Session, user_id: int, product_id: int, quantity: int,
                variant_id: int | None = None) -> list[dict]:
    """加入购物车：同商品同规格合并数量；校验在售与库存"""
    product = ProductRepository(db).get(product_id)
    if not product or product.status != "on_sale":
        raise NotFoundError("商品不存在或已下架")

    variant_repo = ProductVariantRepository(db)
    variants = variant_repo.list_by_product(product.id)
    if variants:
        if variant_id is None:
            raise BadRequestError("请选择商品规格")
        variant = next((v for v in variants if v.id == variant_id), None)
        if not variant:
            raise BadRequestError("所选规格不存在，请重新选择")
    else:
        variant = None
    stock = variant.stock if variant else product.stock
    label = f"{product.name} {variant.spec}" if variant else product.name

    repo = CartRepository(db)
    item = repo.get_by_variant(user_id, product_id, variant_id)
    new_quantity = (item.quantity if item else 0) + quantity
    if new_quantity > MAX_QUANTITY_PER_ITEM:
        raise BadRequestError("单个商品最多购买 99 件")
    if new_quantity > stock:
        raise BadRequestError(f"「{label}」库存不足，仅剩 {stock} 件")

    if item:
        item.quantity = new_quantity
        repo.save(item)
    else:
        repo.add(user_id, product_id, quantity, variant_id)
    return get_cart(db, user_id)


def update_quantity(db: Session, user_id: int, item_id: int, quantity: int) -> list[dict]:
    """修改数量（按所选规格的库存校验）"""
    repo = CartRepository(db)
    item = repo.get(item_id, user_id)
    if not item:
        raise NotFoundError("购物车条目不存在")
    product = ProductRepository(db).get(item.product_id)
    variant = (
        ProductVariantRepository(db).get(item.variant_id)
        if item.variant_id else None
    )
    stock = variant.stock if variant else (product.stock if product else 0)
    label = f"「{product.name} {variant.spec}」" if variant else (
        f"「{product.name}」" if product else "商品"
    )
    if quantity > stock:
        raise BadRequestError(f"{label}库存不足，仅剩 {stock} 件")
    if quantity > MAX_QUANTITY_PER_ITEM:
        raise BadRequestError("单个商品最多购买 99 件")
    item.quantity = quantity
    repo.save(item)
    return get_cart(db, user_id)


def remove_items(db: Session, user_id: int, item_ids: list[int]) -> list[dict]:
    """移除条目（只删自己的）"""
    CartRepository(db).remove_by_ids(user_id, item_ids)
    return get_cart(db, user_id)


def clear_cart(db: Session, user_id: int) -> None:
    """清空购物车"""
    items = CartRepository(db).list(user_id)
    for item in items:
        CartRepository(db).remove(item)
