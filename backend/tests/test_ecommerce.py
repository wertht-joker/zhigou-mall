"""电商平台测试：商品 / 购物车 / 地址 / 订单全流程 / AI 客服工具

运行方式（在 backend 目录下）：
    pytest -q -k ecommerce

全部用内存 SQLite + TestClient，不依赖真实 LLM / Milvus / BGE。
"""
import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


# ===== 夹具 =====

@pytest.fixture
def shop(engine):
    """自营 + 商家两租户、两件商品、商家账号，返回关键 ID"""
    from app.models.product import Product
    from app.services import tenant_service
    from app.utils import security

    Session = sessionmaker(bind=engine)
    session = Session()
    platform = tenant_service.ensure_default_tenant(session)
    merchant = None
    from app.models.tenant import Tenant
    merchant = session.query(Tenant).filter(Tenant.code == "test_shop").first()
    if not merchant:
        merchant = Tenant(code="test_shop", name="测试商家店")
        session.add(merchant)
        session.commit()
        session.refresh(merchant)

    seller = None
    from app.models.user import User
    seller = session.query(User).filter(User.username == "seller").first()
    if not seller:
        seller = User(
            username="seller",
            password_hash=security.hash_password("seller123"),
            role="admin",
            tenant_id=merchant.id,
        )
        session.add(seller)
        session.commit()
        session.refresh(seller)

    p1 = Product(
        tenant_id=merchant.id, name="测试降噪耳机", subtitle="主动降噪",
        description="测试商品详情", price=599.0, original_price=799.0,
        stock=10, sales=100, image="🎧", status="on_sale",
    )
    p2 = Product(
        tenant_id=merchant.id, name="测试机械键盘", subtitle="RGB 背光",
        description="测试商品详情", price=329.0,
        stock=5, sales=50, image="⌨️", status="on_sale",
    )
    p3 = Product(
        tenant_id=platform.id, name="测试下架商品", subtitle="",
        description="", price=99.0, stock=10, sales=0,
        image="📦", status="off_sale",
    )
    session.add_all([p1, p2, p3])
    session.commit()
    result = {
        "platform": platform.id,
        "merchant": merchant.id,
        "p1": p1.id,
        "p2": p2.id,
        "p3": p3.id,
    }
    session.close()
    return result


def _login(client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


@pytest.fixture
def buyer_token(client, make_user):
    """顾客登录态"""
    make_user("buyer", "buyer123", "customer")
    return _login(client, "buyer", "buyer123")


@pytest.fixture
def buyer2_token(client, make_user):
    """另一位顾客（越权对照）"""
    make_user("buyer2", "buyer2123", "customer")
    return _login(client, "buyer2", "buyer2123")


@pytest.fixture
def seller_token(client, shop):
    """商家管理员登录态（依赖 shop 先建好账号）"""
    return _login(client, "seller", "seller123")


@pytest.fixture
def address_id(client, buyer_token):
    resp = client.post(f"{BASE}/addresses", headers=buyer_token, json={
        "receiver": "李雷", "phone": "13800138000",
        "region": "北京市 朝阳区", "detail": "幸福小区 3 号楼 201", "is_default": True,
    })
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


# ===== 商品浏览（公开） =====

def test_public_product_list(client, shop):
    resp = client.get(f"{BASE}/products")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["data"]]
    assert "测试降噪耳机" in names
    assert "测试下架商品" not in names  # 下架商品前台不可见


def test_public_product_list_keyword(client, shop):
    resp = client.get(f"{BASE}/products", params={"keyword": "耳机"})
    names = [p["name"] for p in resp.json()["data"]]
    assert names == ["测试降噪耳机"]


def test_public_product_detail(client, shop):
    resp = client.get(f"{BASE}/products/{shop['p1']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["price"] == 599.0


def test_product_detail_not_found(client):
    assert client.get(f"{BASE}/products/9999").status_code == 404


# ===== 购物车 =====

def test_cart_add_merge_and_update(client, buyer_token, shop):
    resp = client.post(f"{BASE}/cart/items", headers=buyer_token,
                       json={"product_id": shop["p1"], "quantity": 2})
    assert resp.status_code == 200
    resp = client.post(f"{BASE}/cart/items", headers=buyer_token,
                       json={"product_id": shop["p1"], "quantity": 1})
    cart = resp.json()["data"]
    assert len(cart) == 1 and cart[0]["quantity"] == 3  # 同商品合并

    item_id = cart[0]["id"]
    resp = client.put(f"{BASE}/cart/items/{item_id}", headers=buyer_token, json={"quantity": 1})
    assert resp.json()["data"][0]["quantity"] == 1


def test_cart_rejects_offsale_and_overstock(client, buyer_token, shop):
    resp = client.post(f"{BASE}/cart/items", headers=buyer_token,
                       json={"product_id": shop["p3"], "quantity": 1})
    assert resp.json()["code"] == 404  # 下架商品按不存在处理

    resp = client.post(f"{BASE}/cart/items", headers=buyer_token,
                       json={"product_id": shop["p2"], "quantity": 6})
    assert resp.json()["code"] == 400  # 超库存


def test_cart_remove(client, buyer_token, shop):
    resp = client.post(f"{BASE}/cart/items", headers=buyer_token,
                       json={"product_id": shop["p1"], "quantity": 1})
    item_id = resp.json()["data"][0]["id"]
    resp = client.request("DELETE", f"{BASE}/cart/items", headers=buyer_token, json=[item_id])
    assert resp.json()["data"] == []


# ===== 订单全流程 =====

def _setup_order(client, buyer_token, shop, address_id):
    """加购两件商品并下单，返回 (订单数据, 下单响应)"""
    client.post(f"{BASE}/cart/items", headers=buyer_token,
                json={"product_id": shop["p1"], "quantity": 2})
    client.post(f"{BASE}/cart/items", headers=buyer_token,
                json={"product_id": shop["p2"], "quantity": 1})
    resp = client.post(f"{BASE}/orders", headers=buyer_token, json={"address_id": address_id})
    return resp


def test_order_full_lifecycle(client, buyer_token, seller_token, shop, address_id, engine):
    resp = _setup_order(client, buyer_token, shop, address_id)
    assert resp.status_code == 200
    order = resp.json()["data"]
    assert order["status"] == "待付款"
    assert order["total_amount"] == 599.0 * 2 + 329.0
    assert len(order["items"]) == 2
    assert order["receiver_name"] == "李雷"
    assert order["order_no"].startswith("ZG")

    # 下单后清空购物车、扣减库存
    assert client.get(f"{BASE}/cart", headers=buyer_token).json()["data"] == []
    Session = sessionmaker(bind=engine)
    session = Session()
    from app.models.product import Product
    p1 = session.query(Product).filter(Product.id == shop["p1"]).first()
    p2 = session.query(Product).filter(Product.id == shop["p2"]).first()
    assert (p1.stock, p2.stock) == (8, 4)  # 10-2, 5-1
    session.close()

    # 支付 → 待发货
    resp = client.post(f"{BASE}/orders/{order['id']}/pay", headers=buyer_token)
    assert resp.json()["data"]["status"] == "待发货"

    # 商家发货（订单含本店商品）
    resp = client.post(
        f"{BASE}/merchant/orders/{order['id']}/ship",
        headers=seller_token,
        json={"logistics": "顺丰速运 SF0001112223"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "已发货"

    # 顾客确认收货 → 已完成
    resp = client.post(f"{BASE}/orders/{order['id']}/confirm", headers=buyer_token)
    assert resp.json()["data"]["status"] == "已完成"
    assert resp.json()["data"]["logistics"] == "顺丰速运 SF0001112223"


def test_order_cancel_restores_stock(client, buyer_token, shop, address_id, engine):
    resp = _setup_order(client, buyer_token, shop, address_id)
    order = resp.json()["data"]
    resp = client.post(f"{BASE}/orders/{order['id']}/cancel", headers=buyer_token)
    assert resp.json()["data"]["status"] == "已取消"

    Session = sessionmaker(bind=engine)
    session = Session()
    from app.models.product import Product
    p1 = session.query(Product).filter(Product.id == shop["p1"]).first()
    assert p1.stock == 10  # 库存回补
    session.close()

    # 取消后不可再支付
    resp = client.post(f"{BASE}/orders/{order['id']}/pay", headers=buyer_token)
    assert resp.json()["code"] == 400


def test_order_isolated_between_customers(client, buyer_token, buyer2_token,
                                          shop, address_id):
    resp = _setup_order(client, buyer_token, shop, address_id)
    order_id = resp.json()["data"]["id"]

    # 另一位顾客访问订单 → 404（不泄露存在性）
    assert client.get(f"{BASE}/orders/{order_id}", headers=buyer2_token).status_code == 404
    # 本人可见
    assert client.get(f"{BASE}/orders/{order_id}", headers=buyer_token).status_code == 200
    # 他人不能操作别人的订单
    resp = client.post(f"{BASE}/orders/{order_id}/pay", headers=buyer2_token)
    assert resp.status_code == 404


def test_merchant_cannot_ship_order_without_own_items(client, buyer_token, shop,
                                                      address_id, engine):
    """订单只含自营商品时，别的商家不能发货"""
    from app.models.product import Product
    from app.services import tenant_service

    # 自营商品下单
    Session = sessionmaker(bind=engine)
    session = Session()
    platform = tenant_service.ensure_default_tenant(session)
    own = Product(
        tenant_id=platform.id, name="自营测试商品", subtitle="",
        description="", price=59.0, stock=20, sales=0,
        image="📦", status="on_sale",
    )
    session.add(own)
    session.commit()
    own_id = own.id
    session.close()

    client.post(f"{BASE}/cart/items", headers=buyer_token,
                json={"product_id": own_id, "quantity": 1})
    resp = client.post(f"{BASE}/orders", headers=buyer_token, json={"address_id": address_id})
    order_id = resp.json()["data"]["id"]
    client.post(f"{BASE}/orders/{order_id}/pay", headers=buyer_token)

    # seller（商家店铺管理员）不含本店商品 → 403
    resp = client.post(f"{BASE}/merchant/orders/{order_id}/ship",
                       headers=_login(client, "seller", "seller123"),
                       json={"logistics": "SF999"})
    assert resp.status_code == 403


# ===== 商家商品管理（权限与隔离） =====

def test_merchant_product_management_scoped(client, buyer_token, seller_token, shop):
    # 顾客无 product:manage 权限
    resp = client.get(f"{BASE}/merchant/products", headers=buyer_token)
    assert resp.status_code == 403

    # 商家可见本店商品（含下架；shop 夹具里 p1/p2 属于商家，p3 属于自营）
    resp = client.get(f"{BASE}/merchant/products", headers=seller_token)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2

    # 商家上新
    resp = client.post(f"{BASE}/merchant/products", headers=seller_token, json={
        "name": "新上的测试音箱", "price": 299.0, "stock": 30,
        "subtitle": "小钢炮", "image": "🔊",
    })
    assert resp.status_code == 200
    new_id = resp.json()["data"]["id"]

    # 修改
    resp = client.put(f"{BASE}/merchant/products/{new_id}", headers=seller_token,
                      json={"name": "新上的测试音箱", "price": 279.0, "stock": 30,
                            "subtitle": "小钢炮", "image": "🔊", "status": "off_sale"})
    assert resp.json()["data"]["status"] == "off_sale"

    # 删除
    resp = client.delete(f"{BASE}/merchant/products/{new_id}", headers=seller_token)
    assert resp.status_code == 200


# ===== AI 客服工具 =====

def _db(engine):
    return sessionmaker(bind=engine)()


def test_tool_query_my_orders(client, buyer_token, shop, address_id, engine):
    resp = _setup_order(client, buyer_token, shop, address_id)
    order = resp.json()["data"]

    from app.services import tools
    db = _db(engine)
    try:
        from app.models.user import User
        user = db.query(User).filter(User.username == "buyer").first()
        result = tools.execute_tool(
            "query_my_orders", {}, db, shop["platform"], user.id
        )
        assert order["order_no"] in result.text
        assert "待付款" in result.text
        assert result.sources == []
        assert result.payload and result.payload["type"] == "orders"
        assert result.payload["items"][0]["order_no"] == order["order_no"]

        # 按订单号精确查
        result = tools.execute_tool(
            "query_my_orders", {"order_no": order["order_no"]}, db, shop["platform"], user.id
        )
        assert order["order_no"] in result.text

        # 他人订单号 → 查不到
        result = tools.execute_tool(
            "query_my_orders", {"order_no": order["order_no"]}, db, shop["platform"], user.id + 100
        )
        assert "没有找到" in result.text
    finally:
        db.close()


def test_tool_recommend_products(client, shop, engine):
    from app.services import tools
    db = _db(engine)
    try:
        result = tools.execute_tool(
            "recommend_products", {"query": "降噪耳机"}, db, shop["platform"], None
        )
        assert "测试降噪耳机" in result.text
        assert "¥599" in result.text
        # 结构化商品卡片 payload
        assert result.payload and result.payload["type"] == "products"
        card = result.payload["items"][0]
        assert card["name"] == "测试降噪耳机"
        assert card["price"] == 599.0

        # 预算过滤：预算 100 买不到 599 的耳机
        result = tools.execute_tool(
            "recommend_products", {"query": "耳机", "budget_max": 100}, db, None, None
        )
        assert "预算" in result.text

        # 下架商品不会出现在推荐里
        result = tools.execute_tool(
            "recommend_products", {"query": "下架"}, db, None, None
        )
        assert "测试下架商品" not in result.text
    finally:
        db.close()
