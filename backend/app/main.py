"""智购商城 · AI 智能客服电商平台 —— FastAPI 主入口"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    addresses,
    aftersale,
    auth,
    cart,
    categories,
    chat,
    coupons,
    documents,
    feedback,
    geo,
    health,
    orders,
    platform,
    products,
    reviews,
    sessions,
    tenants,
)
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.migrations import run_migrations

# 先把日志体系接管过来（uvicorn 的日志也会走同一套格式）
setup_logging()


def run_seed() -> None:
    """启动时写入商城演示数据（幂等）：店铺/账号/商品/演示订单/知识库"""
    if not settings.seed_demo_data:
        return
    try:
        from app.services import seed_service
        seed_service.run_seed()
    except Exception as exc:
        # 演示数据写入失败不阻断启动（例如 Embedding 模型尚未就绪）
        print(f"[seed] 演示数据写入失败（不阻断启动）：{exc}")


def _sweep_expired_orders(session_factory, order_service) -> None:
    """同步执行一次超时订单清理（放到线程池，避免阻塞事件循环）"""
    db = session_factory()
    try:
        order_service.cancel_expired_orders(db)
    finally:
        db.close()


async def _expire_orders_loop() -> None:
    """后台循环：定期取消超时未支付订单，避免库存被长期占用

    启动即扫一次，之后按 interval 轮询；单次失败只打印日志，不中断循环。
    """
    from app.models.database import SessionLocal
    from app.services import order_service

    while True:
        try:
            await asyncio.to_thread(_sweep_expired_orders, SessionLocal, order_service)
        except Exception as exc:  # noqa: BLE001 - 后台任务不能因单次失败退出
            print(f"[order-expire] 清理任务失败（不阻断服务）：{exc}")
        await asyncio.sleep(settings.order_expire_sweep_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时迁移数据库结构 + 写入演示数据 + 启动超时订单清理

    【为什么迁移放启动时】任何环境（同事机器 / CI / 生产）拉代码直接启动即得
    最新表结构，配合 Alembic 修订链杜绝"我本地能跑"的 schema 漂移；
    seed 是幂等的（按唯一键判重 upsert），改种子后重启即补数据；
    seed 失败不阻断启动（raise 不出去，如模型未就绪）——演示系统的容错取舍。

    【为什么用后台协程而不是独立调度服务】演示/单机部署下少一个进程依赖；
    生产可换成 Celery beat / APScheduler，任务函数与这里完全复用。
    """
    if settings.run_migrations_on_start:
        run_migrations()
    run_seed()
    expire_task = None
    if settings.order_expire_sweep_enabled:
        expire_task = asyncio.create_task(_expire_orders_loop())
    yield
    if expire_task:
        expire_task.cancel()


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="多商家入驻电商平台 + RAG 智能客服（ReAct Agent 工具调用）",
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

# 商品实物宣传图等静态资源（backend/static/）
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 注册路由
app.include_router(health.router, prefix="/api/v1")
app.include_router(geo.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(cart.router, prefix="/api/v1")
app.include_router(coupons.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(platform.router, prefix="/api/v1")
app.include_router(aftersale.router, prefix="/api/v1")
app.include_router(addresses.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")


@app.get("/", tags=["根路由"])
def root():
    """根路径：返回服务概览"""
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
