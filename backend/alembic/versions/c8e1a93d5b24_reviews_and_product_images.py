"""reviews and product images

Revision ID: c8e1a93d5b24
Revises: b4d8c2e61f07
Create Date: 2026-10-24 23:00:00.000000

新增：
- reviews 评价表（京东式：凭已完成订单明细评价，一单一评，商家可回复）
- products.image_url 实物宣传图 URL 列（保留原 emoji image 作为回退）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8e1a93d5b24'
down_revision: Union[str, Sequence[str], None] = 'b4d8c2e61f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reviews',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('merchant_id', sa.Integer(), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('order_item_id', sa.Integer(), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('reply', sa.Text(), nullable=True),
    sa.Column('replied_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_item_id', name='uq_review_order_item')
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index('ix_reviews_merchant', ['merchant_id'], unique=False)
        batch_op.create_index('ix_reviews_product_created', ['product_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_reviews_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('image_url')

    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reviews_user_id'))
        batch_op.drop_index('ix_reviews_product_created')
        batch_op.drop_index('ix_reviews_merchant')
    op.drop_table('reviews')
