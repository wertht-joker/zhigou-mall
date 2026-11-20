"""知识缺口闭环：事件聚类、FAQ 草稿、发布入库与权限隔离"""
from datetime import datetime

from app.models.document import Document
from app.models.qa_event import QaEvent
from app.services import knowledge_gap_service


def _event(db, query: str, **kwargs) -> QaEvent:
    event = QaEvent(
        tenant_id=kwargs.get("tenant_id", 1),
        user_id=None,
        session_id=None,
        message_id=kwargs.get("message_id"),
        query=query,
        answer="（测试）暂无法确认",
        sources_count=kwargs.get("sources_count", 0),
        sufficiency=kwargs.get("sufficiency", "insufficient"),
        faithfulness=kwargs.get("faithfulness"),
        route=kwargs.get("route", "hybrid+rerank"),
        feedback=kwargs.get("feedback"),
        handled=False,
        created_at=datetime.now(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_gaps_cluster_and_attribution(db):
    _event(db, "支持花呗分期吗")
    _event(db, "可以用花呗分期付款吗")
    _event(db, "退货运费谁承担", sources_count=2, sufficiency="partial",
           faithfulness=0.4, feedback="down")

    result = knowledge_gap_service.list_gaps(db, days=30)
    assert result["problem_events"] == 3
    assert result["gap_count"] >= 2
    themes = [gap["theme"] for gap in result["gaps"]]
    assert any("花呗" in theme for theme in themes)

    causes = {cause for gap in result["gaps"] for cause in gap["causes"]}
    assert "检索无结果" in causes
    assert "顾客点踩" in causes
    # 花呗两个问法应聚成同一缺口（代表问题取最近一条）
    huabei = next(g for g in result["gaps"] if "支持花呗分期吗" in g["queries"])
    assert huabei["count"] == 2
    assert any("可以用花呗分期付款吗" == q for q in huabei["queries"])


def test_draft_contains_questions_and_evidence_section(db):
    draft = knowledge_gap_service.build_draft(
        db, ["退货运费谁承担", "退货的运费谁出"]
    )
    assert draft["title"].startswith("FAQ：")
    assert "退货运费谁承担" in draft["content"]
    assert "## 标准答案" in draft["content"]
    assert "## 依据与口径" in draft["content"]
    # 没有匹配文档时必须明确提示，不能假装有依据
    assert "暂未匹配到现有文档" in draft["content"]


def test_publish_creates_document_and_closes_gap(db, monkeypatch):
    monkeypatch.setattr(
        "app.rag.embedding.embed", lambda texts: [[0.0] * 8 for _ in texts]
    )
    monkeypatch.setattr("app.rag.vector_store.insert_chunks", lambda *a, **k: None)

    _event(db, "发票怎么开")
    _event(db, "能开发票吗")
    before = knowledge_gap_service.list_gaps(db)
    assert before["gap_count"] >= 1

    result = knowledge_gap_service.publish_draft(
        db,
        title="FAQ：发票开具说明",
        content="# FAQ：发票开具说明\n\n## 常见问题\n1. 发票怎么开\n\n## 标准答案\n支持电子发票。",
        queries=["发票怎么开", "能开发票吗"],
    )
    assert result["chunk_count"] >= 1
    assert result["handled_events"] == 2
    assert result["regression"]["total"] == 2
    assert result["regression"]["document_id"] == result["document_id"]
    doc = db.query(Document).filter(Document.id == result["document_id"]).first()
    assert doc is not None
    assert doc.status == "done"
    # 已处理的坏例不再出现在缺口看板
    after = knowledge_gap_service.list_gaps(db)
    assert after["problem_events"] == 0


def test_gaps_and_publish_are_isolated_by_tenant(db, monkeypatch):
    monkeypatch.setattr(
        "app.rag.embedding.embed", lambda texts: [[0.0] * 8 for _ in texts]
    )
    monkeypatch.setattr("app.rag.vector_store.insert_chunks", lambda *a, **k: None)

    _event(db, "支持货到付款吗", tenant_id=2)
    _event(db, "支持货到付款吗", tenant_id=1)

    all_gaps = knowledge_gap_service.list_gaps(db)
    assert all_gaps["gap_count"] == 2
    assert {gap["tenant_id"] for gap in all_gaps["gaps"]} == {1, 2}

    only_second = knowledge_gap_service.list_gaps(db, tenant_id=2)
    assert only_second["problem_events"] == 1
    assert all(gap["tenant_id"] == 2 for gap in only_second["gaps"])

    result = knowledge_gap_service.publish_draft(
        db,
        title="FAQ：货到付款说明",
        content="# FAQ：货到付款\n\n## 标准答案\n支持货到付款。",
        queries=["支持货到付款吗"],
        tenant_id=2,
    )
    # 只关闭商家 2 的缺口，商家 1 的同名问题仍保留
    assert result["handled_events"] == 1
    remaining = knowledge_gap_service.list_gaps(db)
    assert remaining["problem_events"] == 1
    assert remaining["gaps"][0]["tenant_id"] == 1


def test_regression_reports_hit_rate(db, monkeypatch):
    event = _event(db, "支持花呗分期吗")
    event.handled = True
    event.resolved_doc_id = 99
    db.commit()

    monkeypatch.setattr(
        "app.services.knowledge_gap_service.retriever.search_with_meta",
        lambda *a, **k: ([{"doc_id": 99, "score": 0.88}], {"strategy": "hybrid"}),
    )
    result = knowledge_gap_service.run_regression(db, 99, tenant_id=1)
    assert result["total"] == 1
    assert result["hits"] == 1
    assert result["hit_rate"] == 1.0
    assert result["details"][0]["rank"] == 1


def test_platform_admin_can_view_documents_across_tenants(
    client, platform_token, admin_token, db
):
    """平台管理员可按商家查看知识库，商家不能越权访问其他商家文档"""
    db.add(Document(
        tenant_id=2, name="星辰FAQ.md", type="md", size=10,
        chunk_count=1, status="done", version=1,
    ))
    db.commit()

    resp = client.get("/api/v1/documents?tenant_id=2", headers=platform_token)
    assert resp.status_code == 200
    names = [doc["name"] for doc in resp.json()["data"]]
    assert "星辰FAQ.md" in names
    assert all(doc["tenant_id"] == 2 for doc in resp.json()["data"])

    resp = client.get("/api/v1/documents", headers=admin_token)
    assert resp.status_code == 200
    assert "星辰FAQ.md" not in [doc["name"] for doc in resp.json()["data"]]

    forbidden = client.get("/api/v1/documents?tenant_id=2", headers=admin_token)
    assert forbidden.status_code == 403


def test_platform_gap_api_and_permission(client, platform_token, user_token, db, monkeypatch):
    monkeypatch.setattr(
        "app.rag.embedding.embed", lambda texts: [[0.0] * 8 for _ in texts]
    )
    monkeypatch.setattr("app.rag.vector_store.insert_chunks", lambda *a, **k: None)

    _event(db, "支持花呗分期吗")
    resp = client.get("/api/v1/platform/knowledge-gaps", headers=platform_token)
    assert resp.status_code == 200
    assert resp.json()["data"]["gap_count"] >= 1

    draft = client.post(
        "/api/v1/platform/knowledge-gaps/draft",
        headers=platform_token,
        json={"queries": ["支持花呗分期吗"]},
    )
    assert draft.status_code == 200
    payload = draft.json()["data"]
    assert payload["title"].startswith("FAQ：")

    publish = client.post(
        "/api/v1/platform/knowledge-gaps/publish",
        headers=platform_token,
        json={
            "title": payload["title"],
            "content": payload["content"],
            "queries": payload["queries"],
        },
    )
    assert publish.status_code == 200
    assert publish.json()["data"]["document_id"] > 0

    forbidden = client.get("/api/v1/platform/knowledge-gaps", headers=user_token)
    assert forbidden.status_code == 403
