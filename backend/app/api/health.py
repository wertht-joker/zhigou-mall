"""健康检查接口

- /health       存活探针（liveness）：进程活着就返回 200，不依赖外部组件
- /health/ready 就绪探针（readiness）：探 DB / Milvus / Redis，任一不可用返回 503
"""
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import deepseek_key_status, settings
from app.core.errors import ServiceUnavailableError
from app.core.response import success

router = APIRouter(tags=["健康检查"])


def _check_database() -> bool:
    """能否对关系库执行一次最简查询"""
    try:
        from app.models.database import SessionLocal

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    from app.core import redis as redis_cache

    return redis_cache.ping()


def _check_milvus() -> bool:
    try:
        from app.rag import vector_store

        return vector_store.ping()
    except Exception:
        return False


def _check_llm() -> bool:
    """大模型是否已配置（未配置不算依赖故障，仅提示）"""
    return deepseek_key_status()[0]


@router.get("/health")
def health():
    """存活探针：返回服务状态与配置概况"""
    llm_ok, llm_hint = deepseek_key_status()
    return success({
        "app": settings.app_name,
        "deepseek_configured": llm_ok,
        "deepseek_config_hint": llm_hint,
        "deepseek_model": settings.deepseek_model,
        "vector_backend": settings.vector_backend,
        "vector_store": (
            f"sqlite:{settings.vector_db_path}"
            if (settings.vector_backend or "").lower() != "milvus"
            else f"milvus:{settings.milvus_host}:{settings.milvus_port}"
        ),
        "embedding_model": settings.embedding_model,
        "top_k": settings.top_k,
    })


@router.get("/health/ready")
def readiness():
    """就绪探针：任一关键依赖不可用即返回 503"""
    checks = {
        "database": _check_database(),
        "milvus": _check_milvus(),
        "redis": _check_redis(),
        "llm_configured": _check_llm(),
    }
    # 关键依赖：database / milvus；redis 与 llm 为可降级项
    critical = {"database": checks["database"], "milvus": checks["milvus"]}
    payload = {"ready": all(critical.values()), "checks": checks}
    if not payload["ready"]:
        raise ServiceUnavailableError("依赖组件未就绪", data=payload)
    return success(payload)


@router.get("/metrics/retrieval")
def retrieval_metrics():
    """方向 D 观测：检索策略分布、缓存命中率、P50/P95 延迟"""
    from app.rag import metrics

    return success(metrics.snapshot())
