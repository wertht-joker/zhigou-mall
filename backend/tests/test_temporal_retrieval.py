"""时效政策检索（方向 C）测试

覆盖：
- 生效区间判断；
- 检索层时间过滤表达式；
- 工具层按订单成交时间选择政策版本；
- 文档版本 supersede 保留历史；
- 离线时效评测的版本错配率下降。
"""
import json
from datetime import datetime
from types import SimpleNamespace

from app.core.config import settings
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.rag import embedding, reranker, retriever, temporal, vector_store
from app.services import tools


class _Entity:
    def __init__(self, data):
        self._data = data

    def get(self, key):
        return self._data.get(key)


class _Hit:
    def __init__(self, chunk):
        self.score = 0.9
        self.entity = _Entity(chunk)


class _Collection:
    def __init__(self, hits, capture):
        self._hits = hits
        self._capture = capture

    def load(self):
        pass

    def search(self, **kwargs):
        self._capture.update(kwargs)
        return [[_Hit(h) for h in self._hits]]


def test_within_window_is_left_closed_right_open():
    start = datetime(2026, 10, 1)
    end = datetime(2026, 11, 1)
    assert temporal.within_window(start, end, datetime(2026, 10, 1))
    assert temporal.within_window(start, end, datetime(2026, 10, 31, 23, 59))
    assert not temporal.within_window(start, end, datetime(2026, 11, 1))
    assert temporal.within_window(None, None, datetime(2026, 1, 1))


def test_retriever_applies_temporal_expr(monkeypatch):
    """effective_at 非空时向量检索同时带租户与时间窗口过滤"""
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled", False)
    monkeypatch.setattr(settings, "rerank_strategy", "none")
    monkeypatch.setattr(embedding, "embed", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr(reranker, "rerank", lambda q, ps: [])

    captured = {}
    chunk = {
        "text": "签收后 7 天内可申请无理由退货。",
        "doc_id": 1,
        "chunk_index": 0,
        "doc_version": 1,
        "policy_key": "return_policy",
        "effective_from": int(datetime(2026, 10, 1).timestamp()),
        "effective_to": int(datetime(2026, 11, 1).timestamp()),
    }
    monkeypatch.setattr(
        vector_store, "init_collection",
        lambda: _Collection([chunk], captured),
    )

    hits = retriever.search(
        "我的订单能退吗", tenant_id=7,
        effective_at=datetime(2026, 10, 15),
    )

    assert "tenant_id == 7" in captured["expr"]
    assert "effective_from <=" in captured["expr"]
    assert "effective_to" in captured["expr"]
    assert hits[0]["policy_key"] == "return_policy"
    assert hits[0]["doc_version"] == 1


def test_search_tool_uses_order_created_at(db, monkeypatch):
    """订单问题用订单成交时间检索，并把政策版本带回引用"""
    doc = Document(
        name="退货政策.md", type="md", size=0, chunk_count=1,
        status="done", tenant_id=None, policy_key="return_policy", version=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    order_at = datetime(2026, 10, 15, 10, 0)
    monkeypatch.setattr(
        tools.OrderRepository, "get_by_order_no",
        lambda self, order_no: SimpleNamespace(
            order_no=order_no, user_id=1, created_at=order_at
        ),
    )

    captured = {}

    def _search(query, **kwargs):
        captured["effective_at"] = kwargs.get("effective_at")
        return [{
            "text": "签收后 7 天内可申请无理由退货。",
            "doc_id": doc.id,
            "chunk_index": 0,
            "score": 0.9,
            "doc_version": 1,
            "policy_key": "return_policy",
            "effective_from": int(order_at.timestamp()),
        }], {"strategy": "hybrid_rerank", "cache": "miss", "hits": 1}

    monkeypatch.setattr(retriever, "search_with_meta", _search)

    result = tools.execute_tool(
        "search_knowledge_base",
        {"query": "我的订单能退吗", "order_no": "ZG202610150001"},
        db, tenant_id=None, user_id=1,
    )

    assert captured["effective_at"] == order_at
    assert result.sources[0]["version"] == 1
    assert result.sources[0]["policy_key"] == "return_policy"
    # SSE meta 直接 json.dumps，sources 里不能出现 datetime
    assert json.loads(json.dumps(result.sources, ensure_ascii=False))[0][
        "effective_from"
    ].startswith("2026-10-15")
    assert "按订单 ZG202610150001 成交时间" in result.text
    assert result.meta["order_no"] == "ZG202610150001"


def test_search_tool_ignores_other_users_order(db, monkeypatch):
    """订单不属于当前用户时不能拿它的成交时间检索"""
    monkeypatch.setattr(
        tools.OrderRepository, "get_by_order_no",
        lambda self, order_no: SimpleNamespace(
            order_no=order_no, user_id=2, created_at=datetime(2026, 10, 15)
        ),
    )
    captured = {}
    before = datetime.now()

    def _search(query, **kwargs):
        captured["effective_at"] = kwargs.get("effective_at")
        return [], {"strategy": "hybrid_rerank", "cache": "miss", "hits": 0}

    monkeypatch.setattr(retriever, "search_with_meta", _search)

    result = tools.execute_tool(
        "search_knowledge_base",
        {"query": "我的订单能退吗", "order_no": "ZG202610150001"},
        db, tenant_id=None, user_id=1,
    )

    assert captured["effective_at"] >= before
    assert "未找到属于您的订单" in result.text


def test_document_supersede_keeps_history(db):
    """新版本取代旧版本，但旧文档保留并补上失效时间"""
    repo = DocumentRepository(db)
    old = repo.create(
        "退货政策 v1.md", "md", None,
        policy_key="return_policy", version=1,
        effective_from=datetime(2026, 10, 1),
    )
    new = repo.create(
        "退货政策 v2.md", "md", None,
        policy_key="return_policy", version=2,
        effective_from=datetime(2026, 11, 1),
    )

    repo.supersede_policy(
        "return_policy", None, datetime(2026, 11, 1), exclude_id=new.id
    )
    db.refresh(old)
    db.refresh(new)

    assert old.lifecycle_status == "superseded"
    assert old.effective_to == datetime(2026, 11, 1)
    assert new.lifecycle_status == "active"
    assert new.effective_to is None


def test_temporal_eval_reduces_version_mismatch():
    """有时间过滤时版本错配率为 0，无过滤时明显更高"""
    from evals.temporal_eval import evaluate

    report = evaluate()
    assert report["cases"] == 40
    assert report["with_filter_mismatch_rate"] == 0.0
    assert report["no_filter_mismatch_rate"] > 0.0
    assert report["temporal_accuracy"] == 1.0
    assert report["stale_answer_rate"] > 0.0


def test_cache_key_changes_with_effective_at():
    """缓存键必须区分不同业务时间，避免旧政策缓存串到新时间"""
    a = retriever._result_cache_key(
        "退货政策", 4, 7, datetime(2026, 10, 15)
    )
    b = retriever._result_cache_key(
        "退货政策", 4, 7, datetime(2026, 11, 15)
    )
    assert a != b


def test_chat_stream_meta_serializes_temporal_sources(db, monkeypatch):
    """带政策版本的引用进入 SSE meta 时必须是可 JSON 序列化的结构"""
    from app.rag import generator
    from app.services import chat_service

    doc = Document(
        name="价保政策_v2.md", type="md", size=0, chunk_count=1,
        status="done", tenant_id=None, policy_key="price_protection",
        version=2, effective_from=datetime(2026, 11, 1),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    monkeypatch.setattr(
        retriever, "search_with_meta",
        lambda *args, **kwargs: ([{
            "text": "价保政策：签收后 15 天内可申请价保。",
            "doc_id": doc.id,
            "chunk_index": 0,
            "score": 0.9,
            "doc_version": 2,
            "policy_key": "price_protection",
            "effective_from": int(datetime(2026, 11, 1).timestamp()),
        }], {"strategy": "hybrid_rerank", "cache": "miss", "hits": 1}),
    )

    calls = {"n": 0}

    def fake_chat_with_tools(messages, tool_defs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "arguments": json.dumps(
                            {"query": "价保政策是几天"}, ensure_ascii=False
                        ),
                    },
                }],
            }
        return {"role": "assistant", "content": ""}

    answer = "价保政策为签收后 15 天内可申请价保。"
    monkeypatch.setattr(generator, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(generator, "stream_answer", lambda messages: iter([answer]))
    monkeypatch.setattr(generator, "generate_text", lambda messages: answer)

    events = []
    for chunk in chat_service.ask_stream(db, "价保政策是几天？"):
        line = chunk.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    meta = next(event for event in events if event["type"] == "meta")
    source = meta["sources"][0]
    assert source["version"] == 2
    assert source["policy_key"] == "price_protection"
    assert source["effective_from"].startswith("2026-11-01")
