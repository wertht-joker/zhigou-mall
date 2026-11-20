"""AI 客服扩展工具测试：售后进度查询 / 优惠券凑单助手

复用内存库与测试客户端夹具；工具直接走 services.tools.execute_tool，
验证「数据边界 + 结构化卡片 + 真实金额计算」。
"""
import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


def _db(engine):
    return sessionmaker(bind=engine)()


def _login(client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


def _user_id(engine, username: str) -> int:
    from app.models.user import User

    session = _db(engine)
    try:
        return session.query(User).filter(User.username == username).first().id
    finally:
        session.close()


def _make_product(engine, name: str, price: float, stock: int = 20,
                  sales: int = 0) -> int:
    from app.models.product import Product
    from app.services import tenant_service

    session = _db(engine)
    try:
        tenant = tenant_service.ensure_default_tenant(session)
        product = Product(
            tenant_id=tenant.id, name=name, subtitle="", description="",
            price=price, stock=stock, sales=sales, image="📦", status="on_sale",
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        return product.id
    finally:
        session.close()


@pytest.fixture
def buyer(client, make_user):
    make_user("buyer", "buyer123", "user")
    return _login(client, "buyer", "buyer123")


@pytest.fixture
def buyer_id(engine, buyer):
    return _user_id(engine, "buyer")


@pytest.fixture
def address_id(client, buyer):
    resp = client.post(f"{BASE}/addresses", headers=buyer, json={
        "receiver": "李雷", "phone": "13800138000",
        "region": "北京市 朝阳区", "detail": "幸福小区 3 号楼 201",
    })
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


# ===== 售后进度查询 =====

def test_query_my_aftersale_returns_ticket_progress(
    client, buyer, buyer_id, address_id, engine
):
    """退款工单创建后，工具返回真实工单状态与结构化卡片"""
    from app.services import aftersale_service, tools

    product_id = _make_product(engine, "售后进度商品", 100.0)
    client.post(f"{BASE}/cart/items", headers=buyer,
                json={"product_id": product_id, "quantity": 2})
    order = client.post(f"{BASE}/orders", headers=buyer,
                        json={"address_id": address_id}).json()["data"]
    client.post(f"{BASE}/orders/{order['id']}/pay", headers=buyer)

    session = _db(engine)
    try:
        proposal = aftersale_service.propose(
            session, buyer_id, 1, "create_refund_ticket",
            {"order_no": order["order_no"], "reason": "尺码不合适"},
        )
    finally:
        session.close()
    resp = client.post(f"{BASE}/aftersale/actions/{proposal['token']}/confirm",
                       headers=buyer, json={"session_id": 1})
    ticket_no = resp.json()["data"]["ticket_no"]

    session = _db(engine)
    try:
        result = tools.execute_tool(
            "query_my_aftersale", {}, session, None, buyer_id, 1
        )
        assert result.payload["type"] == "aftersale"
        item = result.payload["items"][0]
        assert item["ticket_no"] == ticket_no
        assert item["status"] == "待商家处理"
        assert item["amount"] == 200.0
        assert "尺码不合适" in result.text
        assert "待商家处理" in result.text

        # 按订单号过滤：不存在的单号只返回话术，不泄露他人数据
        empty = tools.execute_tool(
            "query_my_aftersale", {"order_no": "ZG-FAKE-001"},
            session, None, buyer_id, 1,
        )
        assert empty.payload is None
        assert "没有找到订单" in empty.text

        # 未登录：直接拒绝
        anonymous = tools.execute_tool("query_my_aftersale", {}, session, None, None)
        assert anonymous.payload is None
        assert "未登录" in anonymous.text
    finally:
        session.close()


def test_query_my_aftersale_is_user_scoped(client, make_user, engine):
    """工具只返回当前 user_id 的工单，新用户查不到别人的售后"""
    from app.services import tools

    make_user("buyer2", "buyer2123", "user")
    buyer2_id = _user_id(engine, "buyer2")
    session = _db(engine)
    try:
        result = tools.execute_tool(
            "query_my_aftersale", {}, session, None, buyer2_id, 1
        )
        assert result.payload is None
        assert "还没有售后工单" in result.text
    finally:
        session.close()


# ===== 优惠券凑单助手 =====

def test_promotion_without_coupons_guides_to_claim(client, buyer, buyer_id, engine):
    from app.services import tools

    _make_product(engine, "凑单测试商品", 100.0)
    session = _db(engine)
    try:
        result = tools.execute_tool(
            "recommend_promotion", {}, session, None, buyer_id, 1
        )
        assert result.payload is None
        assert "还没有未使用的优惠券" in result.text
        assert "满199减30" in result.text
    finally:
        session.close()


def test_promotion_recommends_product_to_fill_gap(client, buyer, buyer_id, engine):
    """购物车 100 元、目标满 199：差 99 元，优先推荐刚过差额的耳机"""
    from app.services import tools

    resp = client.post(f"{BASE}/coupons/claim", headers=buyer,
                       json={"threshold": 199})
    assert resp.status_code == 200
    cart_product = _make_product(engine, "测试商品", 100.0)
    client.post(f"{BASE}/cart/items", headers=buyer,
                json={"product_id": cart_product, "quantity": 1})
    _make_product(engine, "补差耳机", 120.0, sales=1)
    _make_product(engine, "高价耳机", 300.0, sales=9)
    _make_product(engine, "便宜耳机", 50.0)

    session = _db(engine)
    try:
        result = tools.execute_tool(
            "recommend_promotion",
            {"target_threshold": 199, "query": "耳机"},
            session, None, buyer_id, 1,
        )
        assert result.payload["type"] == "products"
        names = [item["name"] for item in result.payload["items"]]
        assert names[0] == "补差耳机"
        assert "还差 ¥99.00" in result.text
        assert "补差耳机" in result.text
    finally:
        session.close()


def test_promotion_reports_usable_coupon_and_next_tier(client, buyer, buyer_id, engine):
    """购物车已满 199：先告知当前可用券，再测算下一档 399 的差额"""
    from app.services import tools

    for threshold in (199, 399):
        resp = client.post(f"{BASE}/coupons/claim", headers=buyer,
                           json={"threshold": threshold})
        assert resp.status_code == 200
    product_id = _make_product(engine, "中价商品", 250.0)
    client.post(f"{BASE}/cart/items", headers=buyer,
                json={"product_id": product_id, "quantity": 1})

    session = _db(engine)
    try:
        result = tools.execute_tool(
            "recommend_promotion", {}, session, None, buyer_id, 1
        )
        assert "已可使用" in result.text
        assert "满199减30" in result.text
        assert "还差 ¥149.00" in result.text
        assert result.payload["type"] == "products"
    finally:
        session.close()
