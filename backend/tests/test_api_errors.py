"""统一响应与全局异常处理契约测试

P1 起：成功 = HTTP 200 + {code,message,data}；
失败 = 真实 HTTP 状态码 + {code,message,data,trace_id}。
这组用例把契约固定下来，后续阶段改动不应破坏它。
"""

BASE = "/api/v1"


def test_success_envelope_shape(client):
    resp = client.get(f"{BASE}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 200
    assert body["message"] == "ok"


def test_duplicate_username_returns_409(client):
    client.post(f"{BASE}/auth/register", json={"username": "dup", "password": "x1"})
    resp = client.post(f"{BASE}/auth/register", json={"username": "dup", "password": "x2"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == 409
    assert "已存在" in body["message"]
    assert body["data"] is None
    assert body["trace_id"]


def test_blank_register_returns_400(client):
    resp = client.post(f"{BASE}/auth/register", json={"username": "", "password": ""})
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


def test_validation_error_returns_400(client, user_token):
    """缺少必填字段（question）应返回 400 而非默认 422"""
    resp = client.post(f"{BASE}/chat", json={}, headers=user_token)
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 400
    assert "参数校验失败" in body["message"]
    assert body["trace_id"]


def test_delete_missing_document_returns_404(client, admin_token):
    resp = client.delete(f"{BASE}/documents/999999", headers=admin_token)
    assert resp.status_code == 404
    assert resp.json()["code"] == 404


def test_delete_missing_category_returns_404(client, admin_token):
    resp = client.delete(f"{BASE}/categories/999999", headers=admin_token)
    assert resp.status_code == 404


def test_feedback_invalid_type_returns_400(client, user_token):
    resp = client.post(
        f"{BASE}/feedback", json={"message_id": 1, "type": "meh"}, headers=user_token
    )
    assert resp.status_code == 400


def test_unauthorized_body_has_trace_id(client):
    resp = client.get(f"{BASE}/documents")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 401
    assert body["trace_id"]
