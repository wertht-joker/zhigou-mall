"""平台管理员角色：admin 从商家管理员中剥离

Revision ID: a1f6c3d92b70
Revises: d4b8f1c92e03
Create Date: 2026-11-18

平台管理员（platform_admin）不归属任何商家，登录后只进入平台后台；
商家管理员仍为 admin，只管理自己店铺。
"""
from alembic import op

revision = "a1f6c3d92b70"
down_revision = "d4b8f1c92e03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 演示库中的 admin 是平台管理员，迁移为独立角色并解除商家归属
    op.execute(
        """
        UPDATE users
        SET role = 'platform_admin', tenant_id = NULL
        WHERE username = 'admin' AND role = 'admin'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'admin',
            tenant_id = (SELECT id FROM tenants WHERE code = 'default')
        WHERE username = 'admin' AND role = 'platform_admin'
        """
    )
