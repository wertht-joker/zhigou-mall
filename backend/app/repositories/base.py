"""仓储层基类与多租户辅助（数据隔离的"防线"所在层）

【多租户三种隔离方案对比】（面试高频）
  a) 独立数据库 / 独立 schema：隔离最强、成本最高，适合金融等强合规场景；
  b) 共享库 + 独立 schema：折中，但迁移与跨租户统计麻烦；
  c) 共享表 + tenant_id 字段（本项目的选择）：成本最低、扩展好，
     前提是【所有查询必须带租户过滤】——这正是过滤被下沉到仓储层的原因：
     业务代码想忘都忘不掉，防线在基础设施层而不是人的自觉。
  刻意的例外：前台商品浏览是跨租户的（真实商城就是全平台逛），
  只有"商家管理域"（商品管理/订单/知识库）才按租户隔离。

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
