"""订单支付截止时间：待付款超时自动取消

Revision ID: e2b4c8d91f07
Revises: d1e8f7a2c9b4
Create Date: 2026-11-20 12:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2b4c8d91f07'
down_revision: Union[str, Sequence[str], None] = 'd1e8f7a2c9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("expire_at", sa.DateTime(), nullable=True))
    op.create_index("ix_orders_status_expire", "orders", ["status", "expire_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_status_expire", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("expire_at")
