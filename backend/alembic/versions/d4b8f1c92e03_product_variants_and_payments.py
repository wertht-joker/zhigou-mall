"""商品多规格与支付流水

Revision ID: d4b8f1c92e03
Revises: a7c4e9f2b1d6
Create Date: 2026-11-18 10:00:00.000000

新增：
- product_variants 商品规格/SKU（独立价格与库存）
- payments 支付流水（支付方式、状态、幂等键、支付时间）
- cart_items.variant_id，唯一键改为 (user_id, product_id, variant_id)
- order_items.variant_id / variant_spec 规格快照
- orders.payment_method / paid_at 支付结果
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4b8f1c92e03'
down_revision: Union[str, Sequence[str], None] = 'a7c4e9f2b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'product_variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('spec', sa.String(length=100), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('original_price', sa.Float(), nullable=True),
        sa.Column('stock', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'spec', name='uq_product_variants_spec'),
    )
    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.create_index(
            'ix_product_variants_product', ['product_id'], unique=False
        )

    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('payment_no', sa.String(length=30), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_no'),
        sa.UniqueConstraint('idempotency_key'),
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index('ix_payments_order', ['order_id'], unique=False)
        batch_op.create_index('ix_payments_user', ['user_id'], unique=False)

    with op.batch_alter_table('cart_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('variant_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('uq_cart_user_product', type_='unique')
        batch_op.create_unique_constraint(
            'uq_cart_user_product_variant',
            ['user_id', 'product_id', 'variant_id'],
        )

    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('variant_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'variant_spec', sa.String(length=100), nullable=False,
                server_default='',
            )
        )

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'payment_method', sa.String(length=20), nullable=False,
                server_default='',
            )
        )
        batch_op.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('paid_at')
        batch_op.drop_column('payment_method')

    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.drop_column('variant_spec')
        batch_op.drop_column('variant_id')

    with op.batch_alter_table('cart_items', schema=None) as batch_op:
        batch_op.drop_constraint('uq_cart_user_product_variant', type_='unique')
        batch_op.create_unique_constraint(
            'uq_cart_user_product', ['user_id', 'product_id']
        )
        batch_op.drop_column('variant_id')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index('ix_payments_user')
        batch_op.drop_index('ix_payments_order')
    op.drop_table('payments')

    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.drop_index('ix_product_variants_product')
    op.drop_table('product_variants')
