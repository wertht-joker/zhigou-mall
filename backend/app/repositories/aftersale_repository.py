"""售后 Agent 仓储：提案 / 工单 / 审计 / 补偿任务

所有读写都围绕"一次提案只执行一次"这个核心约束：
claim() 用条件更新（WHERE used_at IS NULL）抢占执行权，返回影响行数，
并发下只有一个请求能拿到 1，其余请求只能回放已存结果。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.aftersale import (
    ACTION_STATUS_EXECUTING,
    ActionAuditLog,
    AfterSalesTicket,
    CompensationTask,
    PendingAction,
)
from app.models.order import OrderItem
from app.repositories.base import BaseRepository


class AfterSaleRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    # ===== 提案 =====

    def create_action(self, **fields) -> PendingAction:
        action = PendingAction(**fields)
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def get_by_token(self, token: str) -> PendingAction | None:
        return (
            self.db.query(PendingAction)
            .filter(PendingAction.token == token)
            .first()
        )

    def get_by_idempotency_key(self, key: str) -> PendingAction | None:
        return (
            self.db.query(PendingAction)
            .filter(PendingAction.idempotency_key == key)
            .first()
        )

    def claim(self, action_id: int, idempotency_key: str | None) -> int:
        """抢占执行权：只有 used_at 为空的那一次更新能成功

        返回受影响行数：1 = 抢到执行权，0 = 已被其他请求执行/正在执行。
        这是"同一个确认令牌只能触发一次写操作"的数据库级闸门。
        """
        rows = (
            self.db.query(PendingAction)
            .filter(
                PendingAction.id == action_id,
                PendingAction.used_at.is_(None),
            )
            .update(
                {
                    PendingAction.used_at: datetime.now(),
                    PendingAction.status: ACTION_STATUS_EXECUTING,
                    PendingAction.idempotency_key: idempotency_key,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return rows

    def finish(self, action_id: int, status: str, result_json: str) -> None:
        self.db.query(PendingAction).filter(PendingAction.id == action_id).update(
            {"status": status, "result_json": result_json},
            synchronize_session=False,
        )
        self.db.commit()

    def save(self, action: PendingAction) -> PendingAction:
        self.db.commit()
        self.db.refresh(action)
        return action

    # ===== 售后工单 =====

    def create_ticket(self, **fields) -> AfterSalesTicket:
        ticket = AfterSalesTicket(**fields)
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def has_open_ticket(self, order_id: int) -> bool:
        from app.models.aftersale import TICKET_OPEN_STATUSES

        return (
            self.db.query(AfterSalesTicket)
            .filter(
                AfterSalesTicket.order_id == order_id,
                AfterSalesTicket.status.in_(TICKET_OPEN_STATUSES),
            )
            .first()
            is not None
        )

    def list_tickets(self, user_id: int) -> list[AfterSalesTicket]:
        return (
            self.db.query(AfterSalesTicket)
            .filter(AfterSalesTicket.user_id == user_id)
            .order_by(AfterSalesTicket.created_at.desc())
            .all()
        )

    def get_ticket(self, ticket_id: int) -> AfterSalesTicket | None:
        return (
            self.db.query(AfterSalesTicket)
            .filter(AfterSalesTicket.id == ticket_id)
            .first()
        )

    def ticket_belongs_to_merchant(self, ticket: AfterSalesTicket,
                                   merchant_id: int) -> bool:
        """工单是否包含本店商品：订单明细里的 merchant_id 即商家租户 ID"""
        return (
            self.db.query(OrderItem.id)
            .filter(
                OrderItem.order_id == ticket.order_id,
                OrderItem.merchant_id == merchant_id,
            )
            .first()
            is not None
        )

    def list_merchant_tickets(self, merchant_id: int,
                              status: str | None = None) -> list[AfterSalesTicket]:
        """商家视角的售后工单：先按明细圈定含本店商品的订单，再取工单"""
        order_ids = (
            self.db.query(OrderItem.order_id)
            .filter(OrderItem.merchant_id == merchant_id)
            .distinct()
        )
        query = self.db.query(AfterSalesTicket).filter(
            AfterSalesTicket.order_id.in_(order_ids)
        )
        if status:
            query = query.filter(AfterSalesTicket.status == status)
        return query.order_by(AfterSalesTicket.created_at.desc()).all()

    def transition_ticket(self, ticket_id: int, from_status: str,
                          to_status: str) -> int:
        """条件更新工单状态：只有仍处于 from_status 时才能流转

        返回影响行数：1 = 审核成功，0 = 已被其他请求处理过。
        与提案的 claim() 同一思路，防止两个商家账号同时点"通过/驳回"。
        """
        rows = (
            self.db.query(AfterSalesTicket)
            .filter(
                AfterSalesTicket.id == ticket_id,
                AfterSalesTicket.status == from_status,
            )
            .update(
                {
                    AfterSalesTicket.status: to_status,
                    AfterSalesTicket.updated_at: datetime.now(),
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return rows

    # ===== 审计 =====

    def add_audit(self, **fields) -> ActionAuditLog:
        log = ActionAuditLog(**fields)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ===== 补偿任务 =====

    def add_compensation(self, **fields) -> CompensationTask:
        task = CompensationTask(**fields)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
