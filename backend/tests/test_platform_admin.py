"""平台管理员：独立后台接口与权限隔离"""
import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


@pytest.fixture
def stub_docs(monkeypatch, tmp_path):
    """打桩文档入库链路，避免测试时加载向量模型"""
    monkeypatch.setattr("app.services.document_service.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.rag.embedding.embed", lambda texts: [[0.0] * 8 for _ in texts]
    )
    monkeypatch.setattr(
        "app.rag.loader.load_document", lambda path, t: "这是一段测试知识文档内容。"
    )
    monkeypatch.setattr(
        "app.rag.splitter.split_text", lambda text: ["这是一段测试知识文档内容。"]
    )
    monkeypatch.setattr("app.rag.vector_store.insert_chunks", lambda *a, **k: None)
    monkeypatch.setattr("app.rag.vector_store.delete_by_doc_id", lambda *a, **k: None)


def test_platform_overview_and_tenants(client, platform_token):
    resp = client.get(f"{BASE}/platform/overview", headers=platform_token)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "tenants" in data and "orders" in data
    assert len(data["trend"]) == 7
    assert set(data["orders"]["by_status"]) == {"待付款", "待发货", "已发货", "已完成", "已取消"}

    resp = client.get(f"{BASE}/platform/tenants", headers=platform_token)
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert rows and rows[0]["code"] == "default"
    assert rows[0]["is_platform_store"] is True


def test_platform_insights(client, platform_token):
    resp = client.get(f"{BASE}/platform/insights", headers=platform_token)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["brief"]
    assert set(data["pulse"]) == {
        "today_gmv", "today_orders", "gmv_growth",
        "order_growth", "pending_ship", "open_after_sales",
    }
    assert "low_stock" in data["alerts"]
    assert "slow_moving" in data["alerts"]
    assert isinstance(data["merchant_health"], list)
    assert isinstance(data["knowledge_gaps"], list)


def test_platform_admin_cannot_use_merchant_api(client, platform_token):
    """平台管理员不具备 product:manage，不能进入商家经营接口"""
    assert client.get(f"{BASE}/merchant/products", headers=platform_token).status_code == 403
    assert client.get(f"{BASE}/merchant/orders", headers=platform_token).status_code == 403


def test_merchant_admin_cannot_use_platform_api(client, admin_token):
    """商家管理员不能看平台级数据"""
    assert client.get(f"{BASE}/platform/overview", headers=admin_token).status_code == 403
    assert client.get(f"{BASE}/platform/tenants", headers=admin_token).status_code == 403


def test_platform_category_crud(client, platform_token, engine):
    from app.models.product import Product

    resp = client.post(f"{BASE}/platform/product-categories", headers=platform_token,
                       json={"name": "平台测试分类", "icon": "🧪", "sort": 99})
    assert resp.status_code == 200
    category_id = resp.json()["data"]["id"]

    assert client.post(f"{BASE}/platform/product-categories", headers=platform_token,
                       json={"name": "平台测试分类", "icon": "🧪", "sort": 99}).status_code == 409

    resp = client.put(f"{BASE}/platform/product-categories/{category_id}",
                      headers=platform_token,
                      json={"name": "平台测试分类-改", "icon": "🔬", "sort": 98})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "平台测试分类-改"

    # 分类下有商品时不允许删除
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Product(name="分类占用商品", price=1.0, stock=1,
                        category_id=category_id, tenant_id=None))
    session.commit()
    session.close()
    assert client.delete(f"{BASE}/platform/product-categories/{category_id}",
                         headers=platform_token).status_code == 400


def test_platform_can_manage_merchant_status(client, platform_token, engine):
    from app.models.tenant import Tenant

    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = Tenant(code="status_shop", name="状态测试店")
    session.add(tenant)
    session.commit()
    tenant_id = tenant.id
    session.close()

    resp = client.patch(f"{BASE}/platform/tenants/{tenant_id}/status",
                        headers=platform_token, json={"status": "disabled"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "disabled"

    # 平台自营店不允许停用
    rows = client.get(f"{BASE}/platform/tenants", headers=platform_token).json()["data"]
    default_id = next(r["id"] for r in rows if r["code"] == "default")
    resp = client.patch(f"{BASE}/platform/tenants/{default_id}/status",
                        headers=platform_token, json={"status": "disabled"})
    assert resp.status_code == 400


def test_platform_products_and_orders_readonly(client, platform_token):
    resp = client.get(f"{BASE}/platform/products", headers=platform_token)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)

    resp = client.get(f"{BASE}/platform/orders", headers=platform_token)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_platform_content_and_operations_pages(client, platform_token):
    """平台知识库 / 知识分类 / 反馈 / 用户 / 审计均可访问"""
    assert client.get(f"{BASE}/documents", headers=platform_token).status_code == 200
    assert client.get(f"{BASE}/categories", headers=platform_token).status_code == 200
    assert client.get(f"{BASE}/feedback/stats", headers=platform_token).status_code == 200
    assert client.get(f"{BASE}/platform/customers", headers=platform_token).status_code == 200
    assert client.get(f"{BASE}/platform/feedback", headers=platform_token).status_code == 200
    assert client.get(f"{BASE}/platform/audit-logs", headers=platform_token).status_code == 200

    resp = client.get(f"{BASE}/platform/customers", headers=platform_token)
    assert resp.status_code == 200
    resp = client.get(f"{BASE}/platform/feedback", headers=platform_token)
    assert resp.json()["data"]["total"] == 0


def test_document_edit_and_version_management(client, platform_token, stub_docs):
    """文档编辑 + 新版本上传 + 版本切换 + 生效版本删除保护"""
    def upload(name: str, policy_key: str | None = None, version: int | None = None):
        data = {}
        if policy_key:
            data["policy_key"] = policy_key
        if version:
            data["version"] = str(version)
        return client.post(
            f"{BASE}/documents/upload",
            files={"file": (name, b"content", "text/plain")},
            data=data,
            headers=platform_token,
        )

    resp = upload("policy_v1.txt", "test_policy", 1)
    assert resp.status_code == 200, resp.text
    v1 = resp.json()["data"]

    resp = upload("policy_v2.txt", "test_policy")
    assert resp.status_code == 200, resp.text
    v2 = resp.json()["data"]
    assert v2["version"] == 2

    # 重复上传旧版本号被拒绝
    assert upload("policy_dup.txt", "test_policy", 1).status_code == 400

    versions = client.get(
        f"{BASE}/documents/{v2['id']}/versions", headers=platform_token
    ).json()["data"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["lifecycle_status"] == "active"
    assert versions[1]["lifecycle_status"] == "superseded"

    # 编辑元数据（改名 + 分类 + 生效区间）
    resp = client.put(
        f"{BASE}/documents/{v1['id']}",
        headers=platform_token,
        json={
            "name": "政策历史版本.txt",
            "category_id": None,
            "effective_from": None,
            "effective_to": None,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["name"] == "政策历史版本.txt"

    # 切换旧版本为当前版本
    resp = client.post(f"{BASE}/documents/{v1['id']}/activate", headers=platform_token)
    assert resp.status_code == 200, resp.text
    versions = client.get(
        f"{BASE}/documents/{v1['id']}/versions", headers=platform_token
    ).json()["data"]
    by_version = {v["version"]: v for v in versions}
    assert by_version[1]["lifecycle_status"] == "active"
    assert by_version[2]["lifecycle_status"] == "superseded"

    # 生效中的版本不能直接删除
    assert client.delete(
        f"{BASE}/documents/{v1['id']}", headers=platform_token
    ).status_code == 400
    # 先删历史版本，再删当前版本
    assert client.delete(
        f"{BASE}/documents/{v2['id']}", headers=platform_token
    ).status_code == 200
    assert client.delete(
        f"{BASE}/documents/{v1['id']}", headers=platform_token
    ).status_code == 200
