"""向量库操作：建集合、插入块、删除块

默认使用本地 SQLite 内嵌向量库（vector_backend=sqlite），无需 Docker；
演示规模下直接在内存里做余弦相似度计算，几百/几千个 chunk 足够快。
需要独立向量服务时把 VECTOR_BACKEND 设为 milvus，走原有单集合方案。

多租户隔离：
- sqlite：每次查询都带 `tenant_id = ?`；
- milvus：单集合 + 分区键（partition key），检索/删除时带 `tenant_id == x`。
"""
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime

import numpy as np
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.core.config import settings
from app.rag.temporal import effective_expr, to_epoch

# BGE-base-zh-v1.5 的向量维度
EMBEDDING_DIM = 768


def _use_local() -> bool:
    """当前是否使用本地 SQLite 向量库（默认）"""
    return (settings.vector_backend or "sqlite").strip().lower() in {
        "sqlite", "local"
    }


# ===================== 本地 SQLite 向量库 =====================

def _local_connect() -> sqlite3.Connection:
    """打开本地向量库文件；表不存在时自动创建"""
    path = settings.vector_db_path
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL,
            doc_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            doc_version INTEGER NOT NULL DEFAULT 1,
            policy_key TEXT NOT NULL DEFAULT '',
            effective_from INTEGER NOT NULL DEFAULT 0,
            effective_to INTEGER NOT NULL DEFAULT 0,
            vector BLOB NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_vc_tenant ON vector_chunks(tenant_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_vc_doc ON vector_chunks(doc_id)"
    )
    conn.commit()
    return conn


class _LocalEntity:
    """模拟 Milvus hit.entity.get 的取值方式"""

    def __init__(self, row: sqlite3.Row):
        self._row = row

    def get(self, key):
        return self._row[key]


class _LocalHit:
    def __init__(self, score: float, row: sqlite3.Row):
        self.score = float(score)
        self.entity = _LocalEntity(row)


def _local_where(expr: str | None) -> tuple[str, list]:
    """把 Milvus 过滤表达式里用到的条件翻译成 SQL

    只覆盖本项目实际生成的几种表达式（tenant/doc/生效区间），
    不做通用 Milvus 表达式解析。
    """
    if not expr:
        return "", []
    clauses: list[str] = []
    params: list[int] = []
    match = re.search(r"tenant_id\s*==\s*(-?\d+)", expr)
    if match:
        clauses.append("tenant_id = ?")
        params.append(int(match.group(1)))
    match = re.search(r"doc_id\s*==\s*(-?\d+)", expr)
    if match:
        clauses.append("doc_id = ?")
        params.append(int(match.group(1)))
    match = re.search(r"effective_from\s*<=\s*(-?\d+)", expr)
    if match:
        clauses.append("effective_from <= ?")
        params.append(int(match.group(1)))
    match = re.search(
        r"effective_to\s*==\s*0\s*or\s*effective_to\s*>\s*(-?\d+)", expr
    )
    if match:
        clauses.append("(effective_to = 0 OR effective_to > ?)")
        params.append(int(match.group(1)))
    return " AND ".join(clauses), params


class _LocalCollection:
    """本地集合：只实现检索链路用到的 load/search 两个方法"""

    def load(self):
        pass

    def search(self, data, anns_field, param, limit, output_fields, expr=None):
        query = np.asarray(data[0], dtype=np.float32)
        query_norm = float(np.linalg.norm(query)) or 1.0

        where, params = _local_where(expr)
        sql = (
            "SELECT text, doc_id, chunk_index, doc_version, policy_key, "
            "effective_from, effective_to, vector FROM vector_chunks"
        )
        if where:
            sql += " WHERE " + where
        with closing(_local_connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        if not rows:
            return [[]]

        matrix = np.frombuffer(
            b"".join(row["vector"] for row in rows), dtype=np.float32
        ).reshape(len(rows), -1)
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        scores = (matrix @ query) / (norms * query_norm)
        order = np.argsort(-scores)[:limit]
        return [[_LocalHit(scores[i], rows[i]) for i in order]]


def _local_insert(doc_id: int, chunks: list[str], vectors: list[list[float]],
                  tenant_id: int | None,
                  policy_key: str | None,
                  doc_version: int,
                  effective_from: datetime | None,
                  effective_to: datetime | None) -> None:
    rows = [
        (
            int(tenant_id or 0),
            text,
            int(doc_id),
            index,
            int(doc_version or 1),
            policy_key or "",
            to_epoch(effective_from),
            to_epoch(effective_to),
            np.asarray(vector, dtype=np.float32).tobytes(),
        )
        for index, (text, vector) in enumerate(zip(chunks, vectors))
    ]
    with closing(_local_connect()) as conn:
        conn.executemany(
            "INSERT INTO vector_chunks (tenant_id, text, doc_id, chunk_index, "
            "doc_version, policy_key, effective_from, effective_to, vector) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


# ===================== Milvus =====================

def _connect():
    """连接 Milvus（默认别名 default）"""
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )


def _init_milvus() -> Collection:
    """初始化集合：不存在则创建并建索引，存在则直接返回"""
    _connect()
    name = settings.milvus_collection
    if utility.has_collection(name):
        return Collection(name)

    # 字段：id 主键自增；tenant_id 作为分区键实现租户隔离；
    # text 存原文块；doc_id 关联文档；chunk_index 记录块序号；
    # 方向 C 追加政策版本与生效区间（0 表示无边界）；vector 存向量
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="tenant_id", dtype=DataType.INT64, is_partition_key=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4000),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="doc_version", dtype=DataType.INT64),
        FieldSchema(name="policy_key", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="effective_from", dtype=DataType.INT64),
        FieldSchema(name="effective_to", dtype=DataType.INT64),
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


def init_collection():
    """返回当前后端的集合对象（本地为 _LocalCollection）"""
    if _use_local():
        return _LocalCollection()
    return _init_milvus()


def insert_chunks(doc_id: int, chunks: list[str], vectors: list[list[float]],
                  tenant_id: int | None = None,
                  policy_key: str | None = None,
                  doc_version: int = 1,
                  effective_from: datetime | None = None,
                  effective_to: datetime | None = None):
    """把一个文档的所有块写入向量库（带租户 + 政策版本/生效期）"""
    if _use_local():
        _local_insert(
            doc_id, chunks, vectors, tenant_id, policy_key, doc_version,
            effective_from, effective_to,
        )
        return

    collection = init_collection()
    tid = int(tenant_id or 0)
    data = [
        [tid] * len(chunks),                       # tenant_id（分区键）
        chunks,                                    # text
        [doc_id] * len(chunks),                    # doc_id
        list(range(len(chunks))),                  # chunk_index
        [int(doc_version or 1)] * len(chunks),     # doc_version
        [policy_key or ""] * len(chunks),          # policy_key
        [to_epoch(effective_from)] * len(chunks),  # effective_from
        [to_epoch(effective_to)] * len(chunks),    # effective_to
        vectors,                                   # vector
    ]
    collection.insert(data)
    collection.flush()


def delete_by_doc_id(doc_id: int, tenant_id: int | None = None):
    """删除某个文档的所有向量块（限定租户，避免跨租户误删）"""
    if _use_local():
        sql = "DELETE FROM vector_chunks WHERE doc_id = ?"
        params: list[int] = [int(doc_id)]
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params.append(int(tenant_id))
        with closing(_local_connect()) as conn:
            conn.execute(sql, params)
            conn.commit()
        return

    collection = init_collection()
    expr = f"doc_id == {doc_id}"
    if tenant_id is not None:
        expr += f" and tenant_id == {int(tenant_id)}"
    collection.delete(expr=expr)
    collection.flush()


def fetch_chunks(tenant_id: int | None = None, limit: int = 1000,
                 effective_at: datetime | None = None) -> list[dict]:
    """取出某租户的全部块文本（供 BM25 关键词通路构建语料）

    effective_at 非空时只取该业务时间点生效的政策版本；演示规模下直接拉全量
    到内存打分，生产可换成 Milvus 内建 sparse 向量。
    """
    if _use_local():
        sql = (
            "SELECT text, doc_id, chunk_index, doc_version, policy_key, "
            "effective_from, effective_to FROM vector_chunks"
        )
        clauses: list[str] = []
        params: list[int] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(int(tenant_id))
        if effective_at is not None:
            ts = to_epoch(effective_at)
            clauses.append("(effective_from <= ? AND (effective_to = 0 OR effective_to > ?))")
            params.extend([ts, ts])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id LIMIT ?"
        params.append(int(limit))
        with closing(_local_connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "text": row["text"],
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "doc_version": row["doc_version"] or 1,
                "policy_key": row["policy_key"] or None,
                "effective_from": row["effective_from"] or 0,
                "effective_to": row["effective_to"] or 0,
            }
            for row in rows
        ]

    collection = init_collection()
    collection.load()
    expr_parts = []
    if tenant_id is not None:
        expr_parts.append(f"tenant_id == {int(tenant_id)}")
    time_expr = effective_expr(effective_at)
    if time_expr:
        expr_parts.append(time_expr)
    expr = " and ".join(expr_parts) or "doc_id >= 0"
    rows = collection.query(
        expr=expr,
        output_fields=[
            "text", "doc_id", "chunk_index", "doc_version",
            "policy_key", "effective_from", "effective_to",
        ],
        limit=limit,
    )
    return [
        {
            "text": row.get("text"),
            "doc_id": row.get("doc_id"),
            "chunk_index": row.get("chunk_index"),
            "doc_version": row.get("doc_version") or 1,
            "policy_key": row.get("policy_key") or None,
            "effective_from": row.get("effective_from") or 0,
            "effective_to": row.get("effective_to") or 0,
        }
        for row in rows
    ]


def has_chunks(tenant_id: int | None = None) -> bool:
    """集合里是否已有该租户的块（用于新集合首次启动时触发重建索引）"""
    if _use_local():
        sql = "SELECT 1 FROM vector_chunks"
        params: list[int] = []
        if tenant_id is not None:
            sql += " WHERE tenant_id = ?"
            params.append(int(tenant_id))
        sql += " LIMIT 1"
        try:
            with closing(_local_connect()) as conn:
                return conn.execute(sql, params).fetchone() is not None
        except Exception:
            return False

    try:
        collection = init_collection()
        collection.load()
        expr = f"tenant_id == {int(tenant_id)}" if tenant_id is not None else "doc_id >= 0"
        rows = collection.query(expr=expr, output_fields=["doc_id"], limit=1)
        return bool(rows)
    except Exception:
        return False


def ping() -> bool:
    """探活：本地库检查文件可读写；Milvus 检查连接"""
    if _use_local():
        try:
            with closing(_local_connect()) as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    try:
        _connect()
        return True
    except Exception:
        return False
