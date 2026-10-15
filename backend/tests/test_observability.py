"""工程化能力测试：trace_id 链路、就绪探针、限流

这些能力是 P2 阶段新增的，目标是让"可观测 + 可保护"这两件事有断言兜底。
外部依赖（Redis / Milvus / 真实库）一律打桩，保证不联网也能跑。
"""

BASE = "/api/v1"


def test_trace_id_echoed_when_provided(client):
    """上游带了 X-Request-ID 就原样回写，保证跨服务链路可串起来"""
    resp = client.get(f"{BASE}/health", headers={"X-Request-ID": "trace-from-upstream"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "trace-from-upstream"


def test_trace_id_generated_when_missing(client):
    """上游没带就自动生成一个非空的"""
    resp = client.get(f"{BASE}/health")
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]


def test_error_response_carries_same_trace_id(client):
    """错误响应体里的 trace_id 应与响应头一致，便于按 ID 查日志"""
    resp = client.get(f"{BASE}/documents")  # 未登录 → 401
    assert resp.status_code == 401
    assert resp.json()["trace_id"] == resp.headers["X-Request-ID"]


def test_ready_ok_when_critical_deps_healthy(client, monkeypatch):
    """关系库 + Milvus 都可用时，就绪探针返回 200"""
    monkeypatch.setattr("app.api.health._check_database", lambda: True)
    monkeypatch.setattr("app.api.health._check_milvus", lambda: True)
    monkeypatch.setattr("app.api.health._check_redis", lambda: False)

    resp = client.get(f"{BASE}/health/ready")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ready"] is True
    # redis 属于可降级项，不健康也照样 ready
    assert data["checks"]["redis"] is False


def test_ready_503_when_milvus_down(client, monkeypatch):
    """关键依赖 Milvus 不可用时，就绪探针返回 503 并给出明细"""
    monkeypatch.setattr("app.api.health._check_database", lambda: True)
    monkeypatch.setattr("app.api.health._check_milvus", lambda: False)

    resp = client.get(f"{BASE}/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == 503
    assert body["data"]["ready"] is False
    assert body["data"]["checks"]["milvus"] is False


def _force_memory_rate_limit(monkeypatch, capacity: int):
    """绕开 Redis（否则配额存在真实 Redis 里，测试不稳定），改用进程内令牌桶"""
    from app.core import redis as redis_cache
    from app.core.config import settings
    from app.core.rate_limit import reset_memory_buckets

    monkeypatch.setattr(redis_cache, "eval_script", lambda *a, **kw: None)
    monkeypatch.setattr(settings, "rate_limit_capacity", capacity)
    monkeypatch.setattr(settings, "rate_limit_refill_per_second", 0.0)
    reset_memory_buckets()


def test_rate_limit_returns_429(client, user_token, monkeypatch):
    """桶容量为 2 时，第三次提问应被限流拒绝"""
    _force_memory_rate_limit(monkeypatch, capacity=2)

    for _ in range(2):
        resp = client.post(f"{BASE}/chat", json={"question": "你好"}, headers=user_token)
        assert resp.status_code == 200

    resp = client.post(f"{BASE}/chat", json={"question": "你好"}, headers=user_token)
    assert resp.status_code == 429
    assert resp.json()["code"] == 429


def test_rate_limit_does_not_affect_other_endpoints(client, user_token, monkeypatch):
    """限流按接口维度隔离：问答被限流时，会话列表仍可访问"""
    _force_memory_rate_limit(monkeypatch, capacity=1)

    assert client.post(
        f"{BASE}/chat", json={"question": "你好"}, headers=user_token
    ).status_code == 200
    assert client.post(
        f"{BASE}/chat", json={"question": "你好"}, headers=user_token
    ).status_code == 429

    resp = client.get(f"{BASE}/sessions", headers=user_token)
    assert resp.status_code == 200
