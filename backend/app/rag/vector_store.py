"""Milvus 向量库操作：建集合、插入块、删除块

多租户隔离方案：**单集合 + 分区键（partition key）**。
集合里加一个 tenant_id 字段并设为 is_partition_key，检索/删除时带上
`expr: tenant_id == x` 即可实现租户隔离；无需为每个租户单独建集合，
元数据规模可控，未来也可平滑升级为按租户命名集合。
"""
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.core.config import settings

# BGE-base-zh-v1.5 的向量维度
EMBEDDING_DIM = 768


def _connect():
    """连接 Milvus（默认别名 default）"""
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )


def init_collection() -> Collection:
    """初始化集合：不存在则创建并建索引，存在则直接返回"""
    _connect()
    name = settings.milvus_collection
    if utility.has_collection(name):
        return Collection(name)

    # 字段：id 主键自增；tenant_id 作为分区键实现租户隔离；
    # text 存原文块；doc_id 关联文档；chunk_index 记录块序号；vector 存向量
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="tenant_id", dtype=DataType.INT64, is_partition_key=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4000),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
    ]
    schema = CollectionSchema(fields, description="知识库文档块（按租户分区）")
    collection = Collection(name, schema=schema)

    # 为向量字段建索引（余弦相似度 + IVF_FLAT）
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="vector", index_params=index_params)
    return collection


def insert_chunks(doc_id: int, chunks: list[str], vectors: list[list[float]],
                  tenant_id: int | None = None):
    """把一个文档的所有块插入 Milvus（带租户分区键）"""
    collection = init_collection()
    tid = int(tenant_id or 0)
    data = [
        [tid] * len(chunks),             # tenant_id（分区键）
        chunks,                          # text
        [doc_id] * len(chunks),          # doc_id
        list(range(len(chunks))),        # chunk_index
        vectors,                         # vector
    ]
    collection.insert(data)
    collection.flush()


def delete_by_doc_id(doc_id: int, tenant_id: int | None = None):
    """删除某个文档的所有向量块（限定租户，避免跨租户误删）"""
    collection = init_collection()
    expr = f"doc_id == {doc_id}"
    if tenant_id is not None:
        expr += f" and tenant_id == {int(tenant_id)}"
    collection.delete(expr=expr)
    collection.flush()


def fetch_chunks(tenant_id: int | None = None, limit: int = 1000) -> list[dict]:
    """取出某租户的全部块文本（供 BM25 关键词通路构建语料）

    演示规模下语料不大，直接拉全量到内存打分；生产可换成 Milvus 内建 sparse 向量。
    """
    collection = init_collection()
    collection.load()
    expr = f"tenant_id == {int(tenant_id)}" if tenant_id is not None else "doc_id >= 0"
    rows = collection.query(
        expr=expr,
        output_fields=["text", "doc_id", "chunk_index"],
        limit=limit,
    )
    return [
        {
            "text": row.get("text"),
            "doc_id": row.get("doc_id"),
            "chunk_index": row.get("chunk_index"),
        }
        for row in rows
    ]


def ping() -> bool:
    """探活：能连上 Milvus 即视为健康（不创建集合、不检索）"""
    try:
        _connect()
        return True
    except Exception:
        return False
