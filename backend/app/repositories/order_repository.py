"""订单仓储（供本地演示 / 订单查询工具使用）"""
from sqlalchemy.orm import Session

from app.models.order import Order
from app.repositories.base import BaseRepository, apply_tenant, scoped


class OrderRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get_by_order_no(self, order_no: str, tenant_id: int | None = None) -> Order | None:
        query = scoped(
            self.db.query(Order).filter(Order.order_no == order_no), Order, tenant_id
        )
        return query.first()

    def exists(self, tenant_id: int | None = None) -> bool:
        return scoped(self.db.query(Order), Order, tenant_id).first() is not None

    def add_all(self, orders: list[Order]) -> None:
        self.db.add_all(orders)
        self.db.commit()
