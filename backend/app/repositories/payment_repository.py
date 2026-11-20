"""支付流水仓储"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.payment import PAYMENT_STATUS_CLOSED, PAYMENT_STATUS_PENDING, Payment
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, payment_id: int) -> Payment | None:
        return self.db.query(Payment).filter(Payment.id == payment_id).first()

    def get_by_no(self, payment_no: str) -> Payment | None:
        return (
            self.db.query(Payment)
            .filter(Payment.payment_no == payment_no)
            .first()
        )

    def get_by_idempotency_key(self, key: str) -> Payment | None:
        return (
            self.db.query(Payment)
            .filter(Payment.idempotency_key == key)
            .first()
        )

    def get_pending_by_order(self, order_id: int) -> Payment | None:
        return (
            self.db.query(Payment)
            .filter(
                Payment.order_id == order_id,
                Payment.status == PAYMENT_STATUS_PENDING,
            )
            .order_by(Payment.created_at.desc())
            .first()
        )

    def list_by_order(self, order_id: int) -> list[Payment]:
        return (
            self.db.query(Payment)
            .filter(Payment.order_id == order_id)
            .order_by(Payment.created_at.desc())
            .all()
        )

    def create(self, **fields) -> Payment:
        payment = Payment(**fields)
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def save(self, payment: Payment) -> Payment:
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def close_pending(self, order_id: int) -> int:
        """关闭订单下所有待支付流水（取消订单时调用）"""
        closed = (
            self.db.query(Payment)
            .filter(
                Payment.order_id == order_id,
                Payment.status == PAYMENT_STATUS_PENDING,
            )
            .update(
                {Payment.status: PAYMENT_STATUS_CLOSED},
                synchronize_session=False,
            )
        )
        self.db.commit()
        return closed
