"""政策生效时间窗口工具（方向 C：时效感知的版本化政策 RAG）

约定：
- 文档/订单时间统一使用应用本地时区的 naive datetime（项目现状如此）；
- Milvus 标量字段不支持 null，因此 effective_from / effective_to 用 0 表示“无边界”；
- 生效区间为左闭右开：effective_from <= at < effective_to。
"""
from datetime import datetime


def to_epoch(value: datetime | None) -> int:
    """datetime → 秒级时间戳；None 转为 0（无边界）"""
    return int(value.timestamp()) if value else 0


def from_epoch(value: int | None) -> datetime | None:
    """秒级时间戳 → datetime；0/None 转为 None（无边界）"""
    return datetime.fromtimestamp(int(value)) if value else None


def effective_expr(effective_at: datetime | None) -> str | None:
    """生成 Milvus 时间过滤表达式；effective_at 为空时不过滤"""
    if effective_at is None:
        return None
    ts = to_epoch(effective_at)
    return f"effective_from <= {ts} and (effective_to == 0 or effective_to > {ts})"


def within_window(effective_from: datetime | None,
                  effective_to: datetime | None,
                  at: datetime | None) -> bool:
    """判断某个业务时间是否落在政策生效区间内（用于测试与离线评测）"""
    if at is None:
        return True
    if effective_from is not None and at < effective_from:
        return False
    if effective_to is not None and at >= effective_to:
        return False
    return True
