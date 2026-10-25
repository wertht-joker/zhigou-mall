"""coupons table and order discount columns

Revision ID: e7f2a91c4d38
Revises: c8e1a93d5b24
Create Date: 2026-10-25 12:00:00.000000

新增：
- coupons 优惠券表（每档每用户限领一张，下单核销 / 取消退回）
- orders.discount_amount / orders.coupon_id 优惠券抵扣字段
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7f2a91c4d38'
down_revision: Union[str, Sequence[str], None] = 'c8e1a93d5b24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('coupons',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=50), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('discount', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('claimed_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('coupons', schema=None) as batch_op:
        batch_op.create_index('ix_coupons_user_status', ['user_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_coupons_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('discount_amount', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('coupon_id', sa.Integer(), nullable=True))

    # 存量表默认值：历史订单视为无优惠
    op.execute("UPDATE orders SET discount_amount = 0 WHERE discount_amount IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('coupon_id')
        batch_op.drop_column('discount_amount')

    with op.batch_alter_table('coupons', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coupons_user_id'))
        batch_op.drop_index('ix_coupons_user_status')
    op.drop_table('coupons')
