"""购物车仓储"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.repositories.base import BaseRepository


class CartRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def list(self, user_id: int) -> list[CartItem]:
        return (
            self.db.query(CartItem)
            .filter(CartItem.user_id == user_id)
            .order_by(CartItem.created_at.desc())
            .all()
        )

    def get(self, item_id: int, user_id: int) -> CartItem | None:
        return (
            self.db.query(CartItem)
            .filter(CartItem.id == item_id, CartItem.user_id == user_id)
            .first()
        )

    def get_by_variant(self, user_id: int, product_id: int,
                       variant_id: int | None) -> CartItem | None:
        """按「商品 + 规格」定位购物车条目（无规格商品 variant_id 为 None）"""
        query = self.db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
        )
        if variant_id is None:
            query = query.filter(CartItem.variant_id.is_(None))
        else:
            query = query.filter(CartItem.variant_id == variant_id)
        return query.first()

    def add(self, user_id: int, product_id: int, quantity: int,
            variant_id: int | None = None) -> CartItem:
        item = CartItem(
            user_id=user_id, product_id=product_id,
            variant_id=variant_id, quantity=quantity,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def save(self, item: CartItem) -> CartItem:
        self.db.commit()
        self.db.refresh(item)
        return item

    def remove(self, item: CartItem) -> None:
        self.db.delete(item)
        self.db.commit()

    def remove_by_ids(self, user_id: int, item_ids: list[int]) -> int:
        """删除顾客自己的若干购物车条目，返回删除数量"""
        if not item_ids:
            return 0
        deleted = (
            self.db.query(CartItem)
            .filter(CartItem.user_id == user_id, CartItem.id.in_(item_ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
