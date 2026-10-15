"""Alembic 迁移环境

连接串从 app.core.config 的 DATABASE_URL 读取（而不是写死在 alembic.ini），
这样应用启动时的 run_migrations() 与命令行 alembic 用的是同一份配置。
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 保证 `alembic` 命令行也能 import 到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  导入以把全部模型注册进 Base.metadata

config = context.config

# 用应用配置里的连接串覆盖 alembic.ini 中的占位值
config.set_main_option("sqlalchemy.url", settings.database_url)

# 迁移日志沿用 alembic.ini 的配置，但不动应用已有的 logger
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# SQLite 不支持大部分 ALTER TABLE，改动字段时用“重建表”的方式执行
_render_as_batch = settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_render_as_batch,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=_render_as_batch,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
