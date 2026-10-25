"""购物车服务"""
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.repositories.cart_repository import CartRepository
from app.repositories.product_repository import ProductRepository

MAX_QUANTITY_PER_ITEM = 99


def get_cart(db: Session, user_id: int) -> list[dict]:
    """购物车列表，条目带上商品信息与可购状态"""
    repo, product_repo = CartRepository(db), ProductRepository(db)
    result = []
    for item in repo.list(user_id):
        product = product_repo.get(item.product_id)
        result.append({
            "id": item.id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "product": product,
        })
    return result


def add_to_cart(db: Session, user_id: int, product_id: int, quantity: int) -> list[dict]:
    """加入购物车：同商品合并数量；校验在售与库存"""
    product = ProductRepository(db).get(product_id)
    if not product or product.status != "on_sale":
        raise NotFoundError("商品不存在或已下架")

    repo = CartRepository(db)
    item = repo.get_by_product(user_id, product_id)
    new_quantity = (item.quantity if item else 0) + quantity
    if new_quantity > MAX_QUANTITY_PER_ITEM:
        raise BadRequestError("单个商品最多购买 99 件")
    if new_quantity > product.stock:
        raise BadRequestError(f"「{product.name}」库存不足，仅剩 {product.stock} 件")

    if item:
        item.quantity = new_quantity
        repo.save(item)
    else:
        repo.add(user_id, product_id, quantity)
    return get_cart(db, user_id)


def update_quantity(db: Session, user_id: int, item_id: int, quantity: int) -> list[dict]:
    """修改数量"""
    repo = CartRepository(db)
    item = repo.get(item_id, user_id)
    if not item:
        raise NotFoundError("购物车条目不存在")
    product = ProductRepository(db).get(item.product_id)
    if product and quantity > product.stock:
        raise BadRequestError(f"「{product.name}」库存不足，仅剩 {product.stock} 件")
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
