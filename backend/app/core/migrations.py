"""启动时自动迁移数据库结构（等价于 alembic upgrade head）

用 Alembic 取代原先的 Base.metadata.create_all，保证结构变更可追溯、可回滚。

兼容历史遗留库：早期用 create_all 建的库没有 alembic_version 表，
这里先打上基线标记（stamp head），避免迁移时重复建表而报错。
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings

logger = logging.getLogger("app.migrations")

# backend 目录（alembic.ini 与 alembic/ 都在这里）
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _build_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def _stamp_legacy_if_needed(config: Config) -> None:
    """旧库（有业务表但没有 alembic_version）直接标记为最新基线"""
    engine = create_engine(settings.database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if tables and "alembic_version" not in tables:
        logger.info("检测到历史库结构，标记为迁移基线：%s", sorted(tables))
        command.stamp(config, "head")


def run_migrations() -> None:
    """把数据库结构迁移到最新版本"""
    config = _build_config()
    _stamp_legacy_if_needed(config)
    command.upgrade(config, "head")
    logger.info("数据库结构已迁移到最新版本：%s", settings.database_url)
