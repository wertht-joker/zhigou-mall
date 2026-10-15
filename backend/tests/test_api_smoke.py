"""接口冒烟测试：验证系统在打桩掉 LLM/Milvus/BGE 后整体仍可跑通

覆盖核心链路的"骨架"是否完好：健康检查、注册登录、鉴权、问答。
重构每完成一个阶段，这份用例都应保持全绿。
"""

BASE = "/api/v1"


def test_health(client):
    resp = client.get(f"{BASE}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["app"]


def test_register_then_login(client):
    resp = client.post(f"{BASE}/auth/register", json={"username": "bob", "password": "bob123"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 200

    resp = client.post(f"{BASE}/auth/login", json={"username": "bob", "password": "bob123"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"]
    assert data["user"]["role"] == "user"


def test_login_wrong_password_rejected(client, make_user):
    make_user("carol", "carol123", "user")
    resp = client.post(f"{BASE}/auth/login", json={"username": "carol", "password": "bad"})
    assert resp.json()["code"] == 401


def test_protected_endpoint_requires_login(client):
    """未带 token 访问受保护接口应 401"""
    resp = client.get(f"{BASE}/documents")
    assert resp.status_code == 401


def test_normal_user_cannot_manage_documents(client, user_token):
    """普通用户访问管理员接口应 403"""
    resp = client.get(f"{BASE}/documents", headers=user_token)
    assert resp.status_code == 403


def test_admin_can_list_documents(client, admin_token):
    resp = client.get(f"{BASE}/documents", headers=admin_token)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_chat_returns_answer(client, user_token):
    """非流式问答：LLM 已打桩，应返回固定答案并落库"""
    resp = client.post(f"{BASE}/chat", json={"question": "你好"}, headers=user_token)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "这是测试用的固定回答。"
    assert data["session_id"] > 0
    assert data["message_id"] > 0
    assert data["sources"] == []


def test_chat_continues_session(client, user_token):
    """带 session_id 追问应续接同一会话，并累积消息历史"""
    first = client.post(
        f"{BASE}/chat", json={"question": "问题一"}, headers=user_token
    ).json()["data"]
    second = client.post(
        f"{BASE}/chat",
        json={"question": "问题二", "session_id": first["session_id"]},
        headers=user_token,
    ).json()["data"]
    assert second["session_id"] == first["session_id"]

    msgs = client.get(
        f"{BASE}/sessions/{first['session_id']}/messages", headers=user_token
    ).json()["data"]
    assert len(msgs) == 4  # 两轮，每轮 user + assistant


def test_sessions_isolated_by_login(client, user_token, admin_token):
    """会话列表接口可用（骨架完好）"""
    client.post(f"{BASE}/chat", json={"question": "hi"}, headers=user_token)
    resp = client.get(f"{BASE}/sessions", headers=user_token)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1
