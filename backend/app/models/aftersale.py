"""可执行售后 Agent 的数据模型：操作提案 / 售后工单 / 审计日志 / 补偿任务

【核心设计：模型不可信 → 写操作必须"提议-确认-执行"三段式】
模型只能调用 propose 工具生成一条 *提案*（pending_actions），提案本身不改任何业务数据。
真正执行发生在独立的 confirm 接口，且必须同时满足：
  - 令牌存在且归属当前登录用户（换人确认 → 404，不泄露存在性）
  - 归属发起时的会话（换会话确认 → 拒绝）
  - 参数摘要与提案时一致（请求参数被篡改 → 拒绝）
  - 未超过有效期（默认 5 分钟）
  - 未被使用过（重复确认 → 回放首次结果，不重复执行）
执行结果写入 action_audit_logs（谁 / 做了什么 / 变更前后 / trace_id），
逆向操作失败则落 compensation_tasks（库存回补、券退回），由后台对账补偿。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base

# ===== 可执行的售后动作 =====
ACTION_CANCEL_ORDER = "cancel_order"
ACTION_CREATE_REFUND = "create_refund_ticket"
ACTION_CHANGE_ADDRESS = "change_address"
ACTION_TYPES = {
    ACTION_CANCEL_ORDER: "取消订单",
    ACTION_CREATE_REFUND: "申请退款",
    ACTION_CHANGE_ADDRESS: "修改收货地址",
}

# ===== 提案状态 =====
ACTION_STATUS_PENDING = "pending"
ACTION_STATUS_EXECUTING = "executing"
ACTION_STATUS_CONFIRMED = "confirmed"
ACTION_STATUS_CANCELLED = "cancelled"
ACTION_STATUS_EXPIRED = "expired"
ACTION_STATUS_FAILED = "failed"

# ===== 售后工单状态 =====
TICKET_PENDING = "待商家处理"
TICKET_PROCESSING = "处理中"
TICKET_DONE = "已完成"
TICKET_REJECTED = "已驳回"
TICKET_OPEN_STATUSES = [TICKET_PENDING, TICKET_PROCESSING]

# ===== 补偿任务状态 =====
COMPENSATION_PENDING = "待补偿"
COMPENSATION_DONE = "已补偿"


class PendingAction(Base):
    """待确认的写操作提案（不产生任何业务变更）"""

    __tablename__ = "pending_actions"
    __table_args__ = (
        Index("ix_pending_actions_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 一次性确认令牌（前端卡片携带；不携带任何权限信息，权限每次都回查）
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    # 发起人
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 发起会话（防止令牌被挪到其他会话使用）
    session_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 动作类型：cancel_order / create_refund_ticket / change_address
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 规范化参数（JSON）与其 SHA-256 摘要（确认时比对，防篡改）
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 给模型与前端卡片看的一句话说明 + 明细
    summary: Mapped[str] = mapped_column(String(255), default="")
    details_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default=ACTION_STATUS_PENDING)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # 抢占时间：条件更新成功才写入，是并发下的"只执行一次"闸门
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 首次执行结果（重复确认直接回放）
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 幂等键（可选，客户端重试时带入；唯一约束兜底跨提案去重）
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AfterSalesTicket(Base):
    """售后工单：退款申请（演示环境不做真实资金流转，只落工单状态）"""

    __tablename__ = "after_sales_tickets"
    __table_args__ = (
        Index("ix_after_sales_tickets_order", "order_id"),
        Index("ix_after_sales_tickets_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 订单号快照（工单列表不依赖订单表）
    order_no: Mapped[str] = mapped_column(String(30), default="")
    # 售后类型（当前仅退款；换货/维修可扩展）
    kind: Mapped[str] = mapped_column(String(20), default="退款")
    # 申请退款金额（当前为整单金额）
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=TICKET_PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class ActionAuditLog(Base):
    """写操作审计日志：actor / action / target / before / after / trace_id"""

    __tablename__ = "action_audit_logs"
    __table_args__ = (
        Index("ix_action_audit_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 与访问日志/错误响应共用的链路 ID
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 操作对象：order / after_sales_ticket
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    # success / partial / failed
    result: Mapped[str] = mapped_column(String(20), default="success")
    error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CompensationTask(Base):
    """补偿任务：主操作成功但逆向动作失败时落库，供后台重试/对账

    典型场景：订单已置为"已取消"，但回补库存或退回优惠券时数据库异常。
    记录 itself 不修复数据，只保证"失败可追踪、可重放"，符合事务协议的补偿语义。
    """

    __tablename__ = "compensation_tasks"
    __table_args__ = (
        Index("ix_compensation_tasks_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 关联的提案 ID
    action_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # restore_stock / release_coupon
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default=COMPENSATION_PENDING)
    error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
