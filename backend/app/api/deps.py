"""鉴权依赖：解析 JWT 获取当前用户 / 当前租户 / 校验权限

失败统一抛 AuthError / ForbiddenError，由全局异常处理器转成
HTTP 401 / 403 + 统一响应结构。

权限模型：角色 → 权限点集合（见 ROLE_PERMISSIONS）。
- admin  ：文档管理 + 分类管理 + 反馈查看 + 租户管理
- editor ：文档管理 + 分类管理
- viewer ：仅可问答/查看（user 为历史角色，等同 viewer）
"""
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AuthError, ForbiddenError
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services import tenant_service
from app.utils import security

# 角色 → 权限点
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"document:manage", "category:manage", "feedback:view", "tenant:manage"},
    "editor": {"document:manage", "category:manage"},
    "viewer": set(),
}


def get_current_user(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """获取当前登录用户（未登录抛 401）"""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("未登录或登录已过期")
    token = authorization[7:]
    try:
        payload = security.decode_token(token)
        user_id = int(payload["sub"])
    except Exception:
        raise AuthError("登录已过期，请重新登录")

    user = UserRepository(db).get(user_id)
    if not user:
        raise AuthError("用户不存在")
    return user


def get_current_tenant(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    """获取当前用户所属租户（缺失时退回默认租户，保证历史数据可用）"""
    tenant = None
    if user.tenant_id:
        tenant = TenantRepository(db).get(user.tenant_id)
    if tenant is None:
        tenant = tenant_service.ensure_default_tenant(db)
    return tenant


def require_permission(permission: str):
    """生成一个权限依赖：当前用户角色不含该权限点则 403"""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            raise ForbiddenError(f"需要权限：{permission}")
        return user

    return _dependency
