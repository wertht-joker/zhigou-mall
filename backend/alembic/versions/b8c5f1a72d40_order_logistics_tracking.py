"""订单物流轨迹：物流公司/运单号/发货时间/预计送达 + 轨迹事件表

Revision ID: b8c5f1a72d40
Revises: a1f6c3d92b70
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "b8c5f1a72d40"
down_revision = "a1f6c3d92b70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column(
            "logistics_company", sa.String(50), nullable=False, server_default=""
        ))
        batch.add_column(sa.Column(
            "tracking_no", sa.String(50), nullable=False, server_default=""
        ))
        batch.add_column(sa.Column("shipped_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column(
            "estimated_delivery_at", sa.DateTime(), nullable=True
        ))

    op.create_table(
        "order_logistics_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=""),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
        sa.Column("location", sa.String(100), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_logistics_order_time",
        "order_logistics_events",
        ["order_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_logistics_order_time", table_name="order_logistics_events")
    op.drop_table("order_logistics_events")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("estimated_delivery_at")
        batch.drop_column("shipped_at")
        batch.drop_column("tracking_no")
        batch.drop_column("logistics_company")
