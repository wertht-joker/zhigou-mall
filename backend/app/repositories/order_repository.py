"""订单仓储：订单头按顾客查询，明细按订单/商家查询"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    # ===== 订单头 =====

    def get(self, order_id: int) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_by_order_no(self, order_no: str) -> Order | None:
        return self.db.query(Order).filter(Order.order_no == order_no).first()

    def list_by_user(self, user_id: int, status: str | None = None) -> list[Order]:
        query = self.db.query(Order).filter(Order.user_id == user_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).all()

    def create(self, **fields) -> Order:
        order = Order(**fields)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def save(self, order: Order) -> Order:
        self.db.commit()
        self.db.refresh(order)
        return order

    # ===== 订单明细 =====

    def add_items(self, items: list[OrderItem]) -> None:
        self.db.add_all(items)
        self.db.commit()

    def items_of(self, order_id: int) -> list[OrderItem]:
        return (
            self.db.query(OrderItem)
            .filter(OrderItem.order_id == order_id)
            .all()
        )

    def items_of_orders(self, order_ids: list[int]) -> list[OrderItem]:
        """批量取多个订单的明细（避免列表页 N+1 查询）"""
        if not order_ids:
            return []
        return (
            self.db.query(OrderItem)
            .filter(OrderItem.order_id.in_(order_ids))
            .all()
        )

    def list_order_ids_by_merchant(self, merchant_id: int,
                                   status: str | None = None) -> list[int]:
        """商家视角：包含该商家商品的订单 ID 集合"""
        query = (
            self.db.query(OrderItem.order_id.distinct())
            .filter(OrderItem.merchant_id == merchant_id)
        )
        if status:
            query = query.join(Order, Order.id == OrderItem.order_id).filter(
                Order.status == status
            )
        return [row[0] for row in query.all()]
