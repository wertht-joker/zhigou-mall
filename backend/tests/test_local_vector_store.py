"""本地 SQLite 向量库测试（无需 Docker / Milvus）

覆盖：插入与相似度检索、租户隔离、政策生效时间过滤、BM25 语料读取、
删除与空库判断。
"""
from datetime import datetime

import numpy as np

from app.core.config import settings
from app.rag import vector_store


def _unit(index: int) -> list[float]:
    vector = np.zeros(vector_store.EMBEDDING_DIM, dtype=np.float32)
    vector[index] = 1.0
    return vector.tolist()


def _use_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "vector_backend", "sqlite")
    monkeypatch.setattr(settings, "vector_db_path", str(tmp_path / "vectors.db"))


def test_local_search_applies_tenant_and_effective_window(tmp_path, monkeypatch):
    _use_sqlite(tmp_path, monkeypatch)
    v1_from = datetime(2026, 10, 1)
    v2_from = datetime(2026, 11, 1)
    vector_store.insert_chunks(
        1, ["签收后 7 天内可退货"], [_unit(0)], tenant_id=7,
        policy_key="return_policy", doc_version=1,
        effective_from=v1_from, effective_to=v2_from,
    )
    vector_store.insert_chunks(
        2, ["签收后 15 天内可退货"], [_unit(0)], tenant_id=7,
        policy_key="return_policy", doc_version=2,
        effective_from=v2_from,
    )
    vector_store.insert_chunks(
        3, ["其他商家的退货政策"], [_unit(0)], tenant_id=8,
    )

    at = datetime(2026, 10, 15)
    ts = int(at.timestamp())
    collection = vector_store.init_collection()
    collection.load()
    results = collection.search(
        data=[_unit(0)],
        anns_field="vector",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=4,
        output_fields=["text", "doc_version"],
        expr=(
            f"tenant_id == 7 and effective_from <= {ts} "
            f"and (effective_to == 0 or effective_to > {ts})"
        ),
    )

    assert [hit.entity.get("doc_version") for hit in results[0]] == [1]
    assert results[0][0].entity.get("text") == "签收后 7 天内可退货"
    assert 0.99 <= results[0][0].score <= 1.0


def test_local_fetch_has_and_delete(tmp_path, monkeypatch):
    _use_sqlite(tmp_path, monkeypatch)
    assert vector_store.ping()
    assert not vector_store.has_chunks(3)

    vector_store.insert_chunks(11, ["A", "B"], [_unit(0), _unit(1)], tenant_id=3)

    assert vector_store.has_chunks(3)
    assert not vector_store.has_chunks(4)
    assert [c["text"] for c in vector_store.fetch_chunks(3)] == ["A", "B"]

    vector_store.delete_by_doc_id(11, tenant_id=3)
    assert not vector_store.has_chunks(3)
    assert vector_store.fetch_chunks(3) == []


def test_local_fetch_respects_effective_window(tmp_path, monkeypatch):
    _use_sqlite(tmp_path, monkeypatch)
    v1_from = datetime(2026, 10, 1)
    v2_from = datetime(2026, 11, 1)
    vector_store.insert_chunks(
        21, ["旧政策"], [_unit(0)], tenant_id=5,
        doc_version=1, effective_from=v1_from, effective_to=v2_from,
    )
    vector_store.insert_chunks(
        22, ["新政策"], [_unit(1)], tenant_id=5,
        doc_version=2, effective_from=v2_from,
    )

    old = vector_store.fetch_chunks(5, effective_at=datetime(2026, 10, 20))
    new = vector_store.fetch_chunks(5, effective_at=datetime(2026, 11, 20))

    assert [c["text"] for c in old] == ["旧政策"]
    assert [c["text"] for c in new] == ["新政策"]
