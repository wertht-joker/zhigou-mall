"""FastAPI 主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, categories, chat, documents, feedback, health, sessions, tenants
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.migrations import run_migrations

# 先把日志体系接管过来（uvicorn 的日志也会走同一套格式）
setup_logging()


def create_default_admin():
    """在默认租户下创建默认管理员账号（admin / admin123），方便首次登录管理"""
    from app.models.database import SessionLocal
    from app.repositories.user_repository import UserRepository
    from app.services import tenant_service
    from app.utils import security

    db = SessionLocal()
    try:
        tenant = tenant_service.ensure_default_tenant(db)
        repo = UserRepository(db)
        if not repo.get_by_username("admin", tenant.id):
            repo.create("admin", security.hash_password("admin123"),
                        role="admin", tenant_id=tenant.id)
            print("已创建默认管理员账号: admin / admin123")
    finally:
        db.close()


def seed_demo_orders():
    """写入演示订单（仅当默认租户下订单为空时），供 Agent 的订单查询工具演示"""
    from app.models.database import SessionLocal
    from app.models.order import Order
    from app.repositories.order_repository import OrderRepository
    from app.services import tenant_service

    db = SessionLocal()
    try:
        tenant = tenant_service.ensure_default_tenant(db)
        repo = OrderRepository(db)
        if repo.exists(tenant.id):
            return
        repo.add_all([
            Order(
                tenant_id=tenant.id,
                order_no="DD20260901001",
                product_name="智能空气净化器",
                amount=899.0,
                status="已发货",
                logistics="顺丰速运 SF1234567890",
            ),
            Order(
                tenant_id=tenant.id,
                order_no="DD20260912002",
                product_name="智能音箱",
                amount=299.0,
                status="已完成",
                logistics="京东物流 JD9876543210",
            ),
            Order(
                tenant_id=tenant.id,
                order_no="DD20260920003",
                product_name="智能台灯",
                amount=159.0,
                status="待付款",
                logistics="",
            ),
        ])
        print("已写入演示订单数据，共 3 条")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时迁移数据库结构 + 创建默认管理员 + 写入演示订单"""
    if settings.run_migrations_on_start:
        run_migrations()
    create_default_admin()
    seed_demo_orders()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="企业客服知识库系统（RAG 智能问答）",
    lifespan=lifespan,
)

# 全局异常处理器：把业务异常统一转成 HTTP 状态码 + {code, message, data, trace_id}
register_exception_handlers(app)

# CORS：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求上下文：trace_id 透传/生成 + 访问日志（放最外层，覆盖全部请求）
app.add_middleware(RequestContextMiddleware)

# 注册路由
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")


@app.get("/", tags=["根路由"])
def root():
    """根路径：返回服务概览"""
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
