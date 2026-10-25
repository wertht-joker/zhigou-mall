"""ecommerce schema

Revision ID: b4d8c2e61f07
Revises: c199f3e3215b
Create Date: 2026-10-24 10:00:00.000000

电商平台改造：
- 新增 product_categories / products / cart_items / addresses / order_items
- orders 表由「演示订单」重建为电商订单头（归属顾客 user_id + 收货快照 + 状态机）
  （旧表只有演示数据，直接 drop 重建；启动种子会重新写入演示订单）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4d8c2e61f07'
down_revision: Union[str, Sequence[str], None] = 'c199f3e3215b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('product_categories',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('icon', sa.String(length=20), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )

    op.create_table('products',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('subtitle', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('original_price', sa.Float(), nullable=True),
    sa.Column('stock', sa.Integer(), nullable=False),
    sa.Column('sales', sa.Integer(), nullable=False),
    sa.Column('image', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('ix_products_category', ['category_id'], unique=False)
        batch_op.create_index('ix_products_tenant_created', ['tenant_id', 'created_at'], unique=False)

    op.create_table('cart_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'product_id', name='uq_cart_user_product')
    )
    with op.batch_alter_table('cart_items', schema=None) as batch_op:
        batch_op.create_index('ix_cart_items_user', ['user_id'], unique=False)

    op.create_table('addresses',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('receiver', sa.String(length=50), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('region', sa.String(length=100), nullable=False),
    sa.Column('detail', sa.String(length=200), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('addresses', schema=None) as batch_op:
        batch_op.create_index('ix_addresses_user', ['user_id'], unique=False)

    # 旧 orders 是演示数据表，直接重建为电商订单头
    op.drop_index('ix_orders_tenant_no', table_name='orders')
    op.drop_table('orders')

    op.create_table('orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('order_no', sa.String(length=30), nullable=False),
    sa.Column('total_amount', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('receiver_name', sa.String(length=50), nullable=False),
    sa.Column('receiver_phone', sa.String(length=20), nullable=False),
    sa.Column('receiver_address', sa.String(length=255), nullable=False),
    sa.Column('logistics', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_no')
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index('ix_orders_user_created', ['user_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_user_id'), ['user_id'], unique=False)

    op.create_table('order_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('merchant_id', sa.Integer(), nullable=True),
    sa.Column('product_name', sa.String(length=100), nullable=False),
    sa.Column('image', sa.String(length=20), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.create_index('ix_order_items_merchant', ['merchant_id'], unique=False)
        batch_op.create_index('ix_order_items_order', ['order_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_order_items_order', table_name='order_items')
    op.drop_index('ix_order_items_merchant', table_name='order_items')
    op.drop_table('order_items')

    op.drop_index('ix_orders_user_id', table_name='orders')
    op.drop_index('ix_orders_user_created', table_name='orders')
    op.drop_table('orders')

    # 还原为旧版演示订单表
    op.create_table('orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('order_no', sa.String(length=30), nullable=False),
    sa.Column('product_name', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('logistics', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_no')
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index('ix_orders_tenant_no', ['tenant_id', 'order_no'], unique=False)

    op.drop_index('ix_addresses_user', table_name='addresses')
    op.drop_table('addresses')

    op.drop_index('ix_cart_items_user', table_name='cart_items')
    op.drop_table('cart_items')

    op.drop_index('ix_products_tenant_created', table_name='products')
    op.drop_index('ix_products_category', table_name='products')
    op.drop_table('products')

    op.drop_table('product_categories')
