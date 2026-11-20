"""知识缺口闭环：AI 问答事件表

Revision ID: c7d9e4f10a63
Revises: b8c5f1a72d40
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "c7d9e4f10a63"
down_revision = "b8c5f1a72d40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sufficiency", sa.String(20), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("route", sa.String(30), nullable=True),
        sa.Column("feedback", sa.String(10), nullable=True),
        sa.Column("handled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_qa_events_tenant_created", "qa_events", ["tenant_id", "created_at"]
    )
    op.create_index("ix_qa_events_message", "qa_events", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_qa_events_message", table_name="qa_events")
    op.drop_index("ix_qa_events_tenant_created", table_name="qa_events")
    op.drop_table("qa_events")
