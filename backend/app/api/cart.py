"""购物车接口（登录顾客本人操作）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import success
from app.models.database import get_db
from app.models.user import User
from app.schemas.cart import CartAddRequest, CartUpdateRequest
from app.services import cart_service

router = APIRouter(tags=["购物车"])


def _serialize(items: list[dict]) -> list[dict]:
    """商品 ORM 对象转 dict，规格与成交单价直接透出"""
    result = []
    for item in items:
        product = item["product"]
        result.append({
            "id": item["id"],
            "product_id": item["product_id"],
            "variant_id": item["variant_id"],
            "quantity": item["quantity"],
            "variant": item["variant"],
            "unit_price": item["unit_price"],
            "stock": item["stock"],
            "product": (
                {k: v for k, v in product.__dict__.items() if not k.startswith("_")}
                if product
                else None
            ),
        })
    return result


@router.get("/cart")
def get_cart(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我的购物车"""
    return success(_serialize(cart_service.get_cart(db, user.id)))


@router.post("/cart/items")
def add_to_cart(
    req: CartAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """加入购物车（同商品同规格自动合并数量）"""
    items = cart_service.add_to_cart(
        db, user.id, req.product_id, req.quantity, req.variant_id
    )
    return success(_serialize(items), message="已加入购物车")


@router.put("/cart/items/{item_id}")
def update_cart_item(
    item_id: int,
    req: CartUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改数量"""
    items = cart_service.update_quantity(db, user.id, item_id, req.quantity)
    return success(_serialize(items))


@router.delete("/cart/items")
def remove_cart_items(
    item_ids: list[int] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """移除条目（不传 ids 则清空）"""
    if item_ids:
        items = cart_service.remove_items(db, user.id, item_ids)
    else:
        cart_service.clear_cart(db, user.id)
        items = []
    return success(_serialize(items))
