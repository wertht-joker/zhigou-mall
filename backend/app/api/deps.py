"""鉴权依赖：解析 JWT 获取当前用户 / 当前租户 / 校验权限

失败统一抛 AuthError / ForbiddenError，由全局异常处理器转成
HTTP 401 / 403 + 统一响应结构。

权限模型：角色 → 权限点集合（见 ROLE_PERMISSIONS）。
- platform_admin：平台管理员 —— 商家管理 / 平台分类 / 全平台数据监管 / 平台知识库
- admin    ：商家管理员 —— 商品/文档/分类管理 + 反馈查看
- editor   ：商家运营   —— 商品/文档/分类管理
- customer ：顾客 —— 逛商城、下单、与 AI 客服对话，无管理权限
- user/viewer：历史角色，等同顾客（无管理权限）

【FastAPI 依赖注入的两个惯用法】（面试常问"FastAPI 好在哪"）
  - get_current_user 是「资源依赖」：路由声明 Depends(get_current_user) 即自动完成
    取 Header → 解 JWT → 查用户，路由函数拿到的直接是 User ORM 对象，零样板代码；
  - require_permission(x) 是「依赖工厂」：闭包捕获权限点，返回一个依赖函数，
    实现声明式鉴权 require_permission("product:manage")，权限声明长在路由签名上。

【401 vs 403】未登录 / token 无效 = 401（身份问题，前端跳登录页）；
  已登录但角色权限不够 = 403（权限问题，前端提示无权限）。二者不可混用。
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
    "platform_admin": {
        "platform:manage", "tenant:manage",
        "document:manage", "category:manage", "feedback:view",
    },
    "admin": {
        "product:manage", "order:manage",
        "document:manage", "category:manage", "feedback:view",
    },
    "editor": {"product:manage", "order:manage", "document:manage", "category:manage"},
    "customer": set(),
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
    # 商家被平台停用后，已签发的 token 也立即失效
    if user.role in ("admin", "editor") and user.tenant_id:
        tenant = TenantRepository(db).get(user.tenant_id)
        if tenant and tenant.status != "active":
            raise ForbiddenError("店铺已停用，请联系平台管理员")
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
