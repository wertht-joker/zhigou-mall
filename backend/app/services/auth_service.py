"""认证服务：顾客注册 / 商家入驻 / 登录

把认证逻辑从路由搬进服务层，失败时抛 AppError 子类，
由全局异常处理器统一转成 HTTP 状态码 + 统一响应。

电商角色模型：
- platform_admin 平台管理员：管理商家与平台分类，不归属任何店铺
- customer 顾客：逛商城、下单，归属平台默认租户
- admin/editor：商家（租户）管理员/运营，管理本店商品与知识库
"""
from sqlalchemy.orm import Session

from app.core.errors import AuthError, BadRequestError, ConflictError
from app.models.user import User
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.utils import security


def register_customer(db: Session, username: str, password: str,
                      tenant_id: int) -> User:
    """顾客注册：归属平台默认租户"""
    if not username or not password:
        raise BadRequestError("用户名和密码不能为空")
    repo = UserRepository(db)
    if repo.get_by_username(username):
        raise ConflictError("用户名已存在")
    return repo.create(
        username=username,
        password_hash=security.hash_password(password),
        role="customer",
        tenant_id=tenant_id,
    )


def register_merchant(db: Session, username: str, password: str,
                      merchant_name: str) -> tuple[User, object]:
    """商家入驻：创建商家（租户）+ 该店铺管理员账号，返回 (用户, 商家)"""
    if not username or not password:
        raise BadRequestError("用户名和密码不能为空")
    if not merchant_name or not merchant_name.strip():
        raise BadRequestError("请填写店铺名称")

    user_repo = UserRepository(db)
    if user_repo.get_by_username(username):
        raise ConflictError("用户名已存在")

    tenant_repo = TenantRepository(db)
    # 商家编码自动生成：shop_ + 随机串，避免与已有编码冲突
    import uuid
    code = f"shop_{uuid.uuid4().hex[:8]}"
    tenant = tenant_repo.create(code=code, name=merchant_name.strip())
    user = user_repo.create(
        username=username,
        password_hash=security.hash_password(password),
        role="admin",
        tenant_id=tenant.id,
    )
    return user, tenant


def login(db: Session, username: str, password: str,
          tenant_code: str | None = None) -> tuple[User, object]:
    """登录校验，返回 (用户, 商家)。

    商家定位规则：显式传了 tenant_code 按编码定位；未传时按用户名全局定位
    （用户名平台级唯一，顾客与商家都无需记忆租户编码）。
    """
    repo = UserRepository(db)
    if tenant_code:
        tenant = TenantRepository(db).get_by_code(tenant_code)
        if not tenant:
            raise AuthError("租户不存在或已停用")
        user = repo.get_by_username(username, tenant.id)
    else:
        user = repo.get_by_username(username)
        tenant = None
    if not user or not security.verify_password(password, user.password_hash):
        raise AuthError("用户名或密码错误")

    if tenant is None:
        # 平台管理员不归属任何店铺，登录后直接进平台后台
        if user.role == "platform_admin":
            return user, None
        from app.services import tenant_service
        tenant = (
            tenant_service.get(db, user.tenant_id)
            if user.tenant_id
            else tenant_service.ensure_default_tenant(db)
        )
    if tenant.status != "active":
        raise AuthError("店铺已停用，请联系平台管理员")
    return user, tenant
