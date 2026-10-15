"""数据库连接与会话管理（SQLAlchemy）

默认 SQLite，可通过 DATABASE_URL 切到 PostgreSQL（见 .env.example）。
表结构由 Alembic 迁移维护（见 app/core/migrations.py），不再用 create_all。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _engine_options(url: str) -> dict:
    """按数据库方言给出合适的连接参数"""
    if url.startswith("sqlite"):
        # SQLite 需要 check_same_thread=False，否则 FastAPI 多线程下会报错
        return {"connect_args": {"check_same_thread": False}}
    # 非 SQLite：连接前探活，避免拿到已断开的连接
    return {"pool_pre_ping": True}


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承它"""
    pass


def get_db():
    """FastAPI 依赖：提供数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
