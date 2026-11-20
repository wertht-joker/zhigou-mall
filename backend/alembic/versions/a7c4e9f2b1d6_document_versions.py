"""文档版本与生效期（方向 C：时效感知的版本化政策 RAG）

Revision ID: a7c4e9f2b1d6
Revises: f9a3b7d21c05
Create Date: 2026-11-17 16:00:00.000000

新增：
- documents.policy_key 同一政策的稳定标识
- documents.version 版本号
- documents.effective_from / effective_to 生效区间
- documents.supersedes_id 被哪个版本取代
- documents.lifecycle_status active / superseded

老文档统一回填为 version=1、active、effective_from=null（表示长期有效），
保证升级后检索行为不变。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7c4e9f2b1d6'
down_revision: Union[str, Sequence[str], None] = 'f9a3b7d21c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('documents') as batch_op:
        batch_op.add_column(sa.Column('policy_key', sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column('version', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(sa.Column('effective_from', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('effective_to', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('supersedes_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'lifecycle_status',
                sa.String(length=20),
                nullable=False,
                server_default='active',
            )
        )
        batch_op.create_index(
            'ix_documents_policy', ['tenant_id', 'policy_key', 'version'], unique=False
        )
        batch_op.create_index(
            'ix_documents_effective', ['tenant_id', 'effective_from'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents') as batch_op:
        batch_op.drop_index('ix_documents_effective')
        batch_op.drop_index('ix_documents_policy')
        batch_op.drop_column('lifecycle_status')
        batch_op.drop_column('supersedes_id')
        batch_op.drop_column('effective_to')
        batch_op.drop_column('effective_from')
        batch_op.drop_column('version')
        batch_op.drop_column('policy_key')
