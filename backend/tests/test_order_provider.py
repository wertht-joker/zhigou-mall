"""订单接入测试：本地 provider 与第三方 OpenAPI provider

运行方式（在 backend 目录下）：
    pytest -q                 # 跑全部
    pytest -q -k openapi      # 只跑 OpenAPI 相关

测试不依赖真实平台凭证：OpenAPI 用例会起一个本地 mock 服务，
模拟平台约定响应，验证请求构造、字段映射与异常分支。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.database import Base
from app.models.order import Order
from app.services import order_provider, tools


@pytest.fixture
def db():
    """内存库 + 一条演示订单，测试不依赖真实的 kb.db"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Order(
        order_no="DD20260901001",
        product_name="智能空气净化器",
        amount=899.0,
        status="已发货",
        logistics="顺丰速运 SF1234567890",
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


# ===== mock 第三方平台 =====
# 约定：GET {base}{path}?order_no=&access_token=，请求头带 X-App-Key
#       响应 {"code": 0, "message": "ok", "data": {...}}

_ROUTES = {
    "/open/orders/DD20260901001": {
        "code": 0, "message": "ok", "data": {
            "order_no": "DD20260901001",
            "product_name": "智能空气净化器",
            "amount": 899.0,
            "status": "已发货",
            "logistics": "顺丰速运 SF1234567890",
        },
    },
    "/open/orders/EMPTY01": {"code": 0, "message": "ok", "data": None},
    "/open/orders/ERR0001": {"code": 40001, "message": "订单不存在", "data": None},
}


@pytest.fixture
def mock_api():
    """启动本地 mock 平台，产出 (base_url, 收到的请求列表)"""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            received.append({
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "headers": dict(self.headers),
            })
            if parsed.path == "/open/orders/BADJSON":
                payload, content_type = b"not a json", "text/plain"
            else:
                body = _ROUTES.get(parsed.path, {"code": 0, "message": "ok", "data": None})
                payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % server.server_address[1], received
    server.shutdown()


@pytest.fixture
def openapi_env(mock_api, monkeypatch):
    """把配置切到 openapi 模式并指向 mock 平台，返回请求记录"""
    base_url, received = mock_api
    monkeypatch.setattr(settings, "order_provider", "openapi")
    monkeypatch.setattr(settings, "order_api_base_url", base_url)
    monkeypatch.setattr(settings, "order_api_order_path", "/open/orders/{order_no}")
    monkeypatch.setattr(settings, "order_access_token", "tk_test")
    monkeypatch.setattr(settings, "order_app_key", "ak_test")
    monkeypatch.setattr(settings, "order_api_timeout", 2.0)
    return received


# ===== 本地（local）provider =====

def test_local_provider_hits_order(db):
    order = order_provider.get_provider(db).query("DD20260901001")
    assert order is not None
    assert order.status == "已发货"
    assert order.amount == 899.0
    assert order.logistics.startswith("顺丰")


def test_local_provider_missing_order(db):
    assert order_provider.get_provider(db).query("NOT_EXIST") is None


def test_query_order_tool_local(db, monkeypatch):
    monkeypatch.setattr(settings, "order_provider", "local")
    text, sources = tools.execute_tool("query_order", {"order_no": "DD20260901001"}, db)
    assert "DD20260901001" in text
    assert "已发货" in text
    assert "¥899.0" in text
    assert sources == []


def test_query_order_tool_blank_order_no(db):
    text, _ = tools.execute_tool("query_order", {"order_no": "   "}, db)
    assert "未提供订单号" in text


# ===== 第三方 OpenAPI provider =====

def test_openapi_maps_platform_fields(db, openapi_env):
    text, _ = tools.execute_tool("query_order", {"order_no": "DD20260901001"}, db)
    assert "DD20260901001" in text
    assert "已发货" in text
    assert "¥899.0" in text
    assert "顺丰速运" in text


def test_openapi_request_carries_order_no_and_credentials(db, openapi_env):
    tools.execute_tool("query_order", {"order_no": "DD20260901001"}, db)
    req = openapi_env[-1]
    assert req["path"] == "/open/orders/DD20260901001"
    assert req["query"]["order_no"] == ["DD20260901001"]
    assert req["query"]["access_token"] == ["tk_test"]
    assert req["headers"].get("X-App-Key") == "ak_test"


def test_openapi_empty_data_means_not_found(db, openapi_env):
    text, _ = tools.execute_tool("query_order", {"order_no": "EMPTY01"}, db)
    assert "未查询到订单号 EMPTY01" in text


def test_openapi_platform_error_is_surfaced(db, openapi_env):
    text, _ = tools.execute_tool("query_order", {"order_no": "ERR0001"}, db)
    assert "订单查询失败" in text
    assert "订单不存在" in text


def test_openapi_non_json_response(db, openapi_env):
    text, _ = tools.execute_tool("query_order", {"order_no": "BADJSON"}, db)
    assert "订单查询失败" in text
    assert "非 JSON" in text


# ===== 配置与异常分支 =====

def test_openapi_without_base_url(db, monkeypatch):
    monkeypatch.setattr(settings, "order_provider", "openapi")
    monkeypatch.setattr(settings, "order_api_base_url", "")
    text, _ = tools.execute_tool("query_order", {"order_no": "X"}, db)
    assert "未配置" in text


def test_openapi_service_unavailable(db, monkeypatch):
    # 127.0.0.1:1 必定连不上，验证网络异常被转成友好提示
    monkeypatch.setattr(settings, "order_provider", "openapi")
    monkeypatch.setattr(settings, "order_api_base_url", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "order_api_timeout", 1.0)
    text, _ = tools.execute_tool("query_order", {"order_no": "X"}, db)
    assert "订单查询失败" in text


def test_unknown_provider_does_not_silently_fall_back(db, monkeypatch):
    monkeypatch.setattr(settings, "order_provider", "mysql")
    with pytest.raises(order_provider.OrderServiceError, match="未知的 ORDER_PROVIDER"):
        order_provider.get_provider(db)


def test_provider_name_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(settings, "order_provider", "OpenAPI")
    assert isinstance(
        order_provider.get_provider(), order_provider.OpenApiOrderProvider
    )
