"""aftersale agent tables: pending actions, tickets, audit, compensation

Revision ID: f9a3b7d21c05
Revises: e7f2a91c4d38
Create Date: 2026-11-17 10:00:00.000000

新增：
- pending_actions 待确认写操作提案（一次性令牌 / 参数摘要 / 幂等键）
- after_sales_tickets 售后工单（退款申请）
- action_audit_logs 写操作审计日志
- compensation_tasks 补偿任务（库存回补 / 券退回失败时落库）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f9a3b7d21c05'
down_revision: Union[str, Sequence[str], None] = 'e7f2a91c4d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pending_actions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=32), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=False),
        sa.Column('params_hash', sa.String(length=64), nullable=False),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_pending_actions_idempotency_key'),
    )
    op.create_index(
        'ix_pending_actions_token', 'pending_actions', ['token'], unique=True
    )
    op.create_index(
        'ix_pending_actions_user_created',
        'pending_actions',
        ['user_id', 'created_at'],
        unique=False,
    )

    op.create_table(
        'after_sales_tickets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticket_no', sa.String(length=30), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('order_no', sa.String(length=30), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_no'),
    )
    op.create_index(
        'ix_after_sales_tickets_order', 'after_sales_tickets', ['order_id'], unique=False
    )
    op.create_index(
        'ix_after_sales_tickets_user', 'after_sales_tickets', ['user_id'], unique=False
    )

    op.create_table(
        'action_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trace_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=32), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=64), nullable=False),
        sa.Column('before_json', sa.Text(), nullable=False),
        sa.Column('after_json', sa.Text(), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.Column('error', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_action_audit_user_created',
        'action_audit_logs',
        ['user_id', 'created_at'],
        unique=False,
    )

    op.create_table(
        'compensation_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('action_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(length=32), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_compensation_tasks_status', 'compensation_tasks', ['status'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_compensation_tasks_status', table_name='compensation_tasks')
    op.drop_table('compensation_tasks')

    op.drop_index('ix_action_audit_user_created', table_name='action_audit_logs')
    op.drop_table('action_audit_logs')

    op.drop_index('ix_after_sales_tickets_user', table_name='after_sales_tickets')
    op.drop_index('ix_after_sales_tickets_order', table_name='after_sales_tickets')
    op.drop_table('after_sales_tickets')

    op.drop_index('ix_pending_actions_user_created', table_name='pending_actions')
    op.drop_index('ix_pending_actions_token', table_name='pending_actions')
    op.drop_table('pending_actions')
