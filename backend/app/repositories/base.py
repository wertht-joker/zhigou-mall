"""仓储层基类与多租户辅助

多租户预留：所有仓储方法都接受 tenant_id。P3 之前模型上还没有 tenant_id 列，
辅助函数会自动跳过过滤，因此现在就能把签名固定下来，P3 直接透传即可生效。
"""
from sqlalchemy.orm import Query, Session


def _has_tenant_column(model) -> bool:
    """模型是否已有 tenant_id 列（P3 之前为 False）"""
    return "tenant_id" in model.__table__.columns


def scoped(query: Query, model, tenant_id: int | None) -> Query:
    """追加租户过滤；列不存在或未指定租户时为 no-op"""
    if tenant_id is None or not _has_tenant_column(model):
        return query
    return query.filter(model.tenant_id == tenant_id)


def apply_tenant(obj, tenant_id: int | None):
    """写入租户归属；列不存在或未指定租户时为 no-op"""
    if tenant_id is not None and _has_tenant_column(type(obj)):
        obj.tenant_id = tenant_id
    return obj


class BaseRepository:
    """仓储基类：统一持有数据库会话"""

    def __init__(self, db: Session):
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, obj):
        self.db.refresh(obj)
        return obj
