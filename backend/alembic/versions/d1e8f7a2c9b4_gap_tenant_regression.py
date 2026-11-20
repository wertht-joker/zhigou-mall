"""知识缺口按商家隔离 + FAQ 发布后命中率回归

Revision ID: d1e8f7a2c9b4
Revises: c7d9e4f10a63
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "d1e8f7a2c9b4"
down_revision = "c7d9e4f10a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_events",
        sa.Column("resolved_doc_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("qa_events", "resolved_doc_id")
