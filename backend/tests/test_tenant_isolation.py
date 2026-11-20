"""多租户隔离测试：A 租户的数据对 B 租户不可见

覆盖：登录返回租户信息、文档/会话列表按租户隔离、跨租户访问会话 404、
向量检索按 tenant_id 分区过滤。外部依赖（Milvus / BGE / LLM）全部打桩，不联网。
"""
import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


@pytest.fixture
def tenants(engine):
    """建两个租户，返回 {code: id}"""
    from app.models.tenant import Tenant

    Session = sessionmaker(bind=engine)
    session = Session()
    a = Tenant(code="tenant_a", name="A 公司")
    b = Tenant(code="tenant_b", name="B 公司")
    session.add_all([a, b])
    session.commit()
    result = {"tenant_a": a.id, "tenant_b": b.id}
    session.close()
    return result


@pytest.fixture
def stub_pipeline(monkeypatch, tmp_path):
    """打桩文档入库链路：不写真实文件、不调用 BGE / Milvus"""
    monkeypatch.setattr("app.services.document_service.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("app.rag.embedding.embed", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr("app.rag.loader.load_document", lambda path, t: "这是一段测试文档内容。")
    monkeypatch.setattr("app.rag.vector_store.insert_chunks", lambda *a, **k: None)
    monkeypatch.setattr("app.rag.vector_store.delete_by_doc_id", lambda *a, **k: None)


def _headers(client, username: str, password: str, tenant_code: str) -> dict:
    resp = client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": password, "tenant_code": tenant_code},
    )
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


@pytest.fixture
def user_a(client, make_user, tenants):
    """A 公司管理员"""
    make_user("alice", "alice123", "admin", tenants["tenant_a"])
    return _headers(client, "alice", "alice123", "tenant_a")


@pytest.fixture
def user_b(client, make_user, tenants):
    """B 公司管理员"""
    make_user("bob", "bob123", "admin", tenants["tenant_b"])
    return _headers(client, "bob", "bob123", "tenant_b")


def test_login_returns_tenant(client, make_user, tenants):
    """登录返回里带上租户信息，前端可据此展示当前数据空间"""
    make_user("alice", "alice123", "admin", tenants["tenant_a"])
    resp = client.post(
        f"{BASE}/auth/login",
        json={"username": "alice", "password": "alice123", "tenant_code": "tenant_a"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant"]["code"] == "tenant_a"
    assert data["user"]["tenant_id"] == tenants["tenant_a"]


def test_merchant_onboarding_creates_tenant(client):
    """商家入驻：自动创建商家（租户）+ 店铺管理员，店铺编码唯一"""
    resp = client.post(
        f"{BASE}/auth/register",
        json={
            "username": "newshop",
            "password": "shop123",
            "register_type": "merchant",
            "merchant_name": "新入驻的店铺",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"]["role"] == "admin"
    assert data["tenant"]["name"] == "新入驻的店铺"
    assert data["tenant"]["code"].startswith("shop_")


def test_documents_isolated_between_tenants(client, user_a, user_b, stub_pipeline):
    """A 上传的文档，B 看不到"""
    resp = client.post(
        f"{BASE}/documents/upload",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=user_a,
    )
    assert resp.status_code == 200, resp.text

    assert len(client.get(f"{BASE}/documents", headers=user_a).json()["data"]) == 1
    assert client.get(f"{BASE}/documents", headers=user_b).json()["data"] == []


def test_sessions_isolated_between_tenants(client, user_a, user_b):
    """A 的会话，B 看不到"""
    client.post(f"{BASE}/chat", json={"question": "你好"}, headers=user_a)
    assert len(client.get(f"{BASE}/sessions", headers=user_a).json()["data"]) == 1
    assert client.get(f"{BASE}/sessions", headers=user_b).json()["data"] == []


def test_cross_tenant_session_messages_denied(client, user_a, user_b):
    """B 用 A 的 session_id 读消息历史应 404"""
    session_id = client.post(
        f"{BASE}/chat", json={"question": "你好"}, headers=user_a
    ).json()["data"]["session_id"]

    resp = client.get(f"{BASE}/sessions/{session_id}/messages", headers=user_b)
    assert resp.status_code == 404


def test_cross_tenant_chat_continue_denied(client, user_a, user_b):
    """B 用 A 的 session_id 追问应 404（会话归属校验）"""
    session_id = client.post(
        f"{BASE}/chat", json={"question": "你好"}, headers=user_a
    ).json()["data"]["session_id"]

    resp = client.post(
        f"{BASE}/chat", json={"question": "继续", "session_id": session_id}, headers=user_b
    )
    assert resp.status_code == 404


def test_retriever_scopes_search_by_tenant(monkeypatch):
    """向量检索必须带 tenant_id 分区过滤 expr"""
    from app.core.config import settings
    from app.rag import embedding, reranker, retriever, vector_store

    # 关闭检索缓存：本机若在跑 Redis，历史缓存会让向量库调用被跳过，断言失真
    monkeypatch.setattr(settings, "retrieval_cache_enabled", False)

    captured = {}

    class _Hit:
        score = 0.9
        entity = {"text": "片段", "doc_id": 1, "chunk_index": 0}

    class _Collection:
        def load(self):
            pass

        def search(self, **kwargs):
            captured.update(kwargs)
            return [[_Hit()]]

    monkeypatch.setattr(embedding, "embed", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr(vector_store, "init_collection", lambda: _Collection())
    # BM25 语料走本地返回，避免真实访问 Milvus
    monkeypatch.setattr(vector_store, "fetch_chunks", lambda tenant_id=None, limit=0: [])
    monkeypatch.setattr(reranker, "rerank", lambda q, ps: [(i, 1.0) for i in range(len(ps))])

    hits = retriever.search("保修政策", tenant_id=7)
    assert captured["expr"] == "tenant_id == 7"
    assert hits and hits[0]["doc_id"] == 1


def test_tenants_endpoint_requires_platform_admin(client, user_token, platform_token, tenants):
    """租户列表仅平台管理员可访问"""
    assert client.get(f"{BASE}/tenants").status_code == 401
    assert client.get(f"{BASE}/tenants", headers=user_token).status_code == 403
    resp = client.get(f"{BASE}/tenants", headers=platform_token)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1
