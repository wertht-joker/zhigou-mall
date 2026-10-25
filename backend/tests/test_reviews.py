"""评价功能测试：凭已完成订单明细评价 / 一单一评 / 公开列表与统计 / 商家回复

运行方式（在 backend 目录下）：
    pytest -q -k reviews

全部用内存 SQLite + TestClient，不依赖真实 LLM / Milvus / BGE。
"""
import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


def _login(client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


def _add_address(client, token: dict, receiver: str) -> int:
    resp = client.post(f"{BASE}/addresses", headers=token, json={
        "receiver": receiver, "phone": "13900139000",
        "region": "上海市 浦东新区", "detail": "世纪大道 100 号", "is_default": True,
    })
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


# ===== 夹具 =====

@pytest.fixture
def review_env(engine):
    """商家店 + 在售商品，返回关键 ID（评价人/买家通过 make_user 另行创建）"""
    from app.models.product import Product
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services import tenant_service
    from app.utils import security

    Session = sessionmaker(bind=engine)
    session = Session()
    platform = tenant_service.ensure_default_tenant(session)
    merchant = session.query(Tenant).filter(Tenant.code == "rv_shop").first()
    if not merchant:
        merchant = Tenant(code="rv_shop", name="评价测试店")
        session.add(merchant)
        session.commit()
        session.refresh(merchant)

    seller = session.query(User).filter(User.username == "rv_seller").first()
    if not seller:
        seller = User(
            username="rv_seller",
            password_hash=security.hash_password("seller123"),
            role="admin",
            tenant_id=merchant.id,
        )
        session.add(seller)
        session.commit()
        session.refresh(seller)

    product = Product(
        tenant_id=merchant.id, name="评价测试耳机", subtitle="主动降噪",
        description="测试商品详情", price=599.0, original_price=799.0,
        stock=10, sales=1, image="🎧", status="on_sale",
    )
    session.add(product)
    session.commit()
    env = {"platform": platform.id, "merchant": merchant.id, "product": product.id}
    session.close()
    return env


@pytest.fixture
def buyer_token(client, review_env, make_user):
    make_user("rv_buyer", "buyer123", "customer")
    return _login(client, "rv_buyer", "buyer123")


@pytest.fixture
def seller_token(client, review_env):
    """评价测试店的商家管理员登录态"""
    return _login(client, "rv_seller", "seller123")


@pytest.fixture
def address_id(client, buyer_token):
    """买家默认收货地址"""
    return _add_address(client, buyer_token, "韩梅梅")


def _completed_order(client, buyer_token, seller_token, review_env, address_id):
    """买家下单 → 支付 → 商家发货 → 确认收货，返回订单数据（items 里的 id 即订单明细 ID）"""
    client.post(f"{BASE}/cart/items", headers=buyer_token,
                json={"product_id": review_env["product"], "quantity": 1})
    resp = client.post(f"{BASE}/orders", headers=buyer_token, json={"address_id": address_id})
    order = resp.json()["data"]
    client.post(f"{BASE}/orders/{order['id']}/pay", headers=buyer_token)
    client.post(f"{BASE}/merchant/orders/{order['id']}/ship",
                headers=seller_token, json={"logistics": "顺丰速运 SF555666777"})
    resp = client.post(f"{BASE}/orders/{order['id']}/confirm", headers=buyer_token)
    assert resp.json()["data"]["status"] == "已完成"
    return order


# ===== 评价前置校验 =====

def test_review_requires_completed_order(client, buyer_token, seller_token,
                                         review_env, address_id):
    """未完成订单（待付款）不能评价"""
    client.post(f"{BASE}/cart/items", headers=buyer_token,
                json={"product_id": review_env["product"], "quantity": 1})
    order = client.post(f"{BASE}/orders", headers=buyer_token,
                        json={"address_id": address_id}).json()["data"]
    item_id = order["items"][0]["id"]

    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": item_id, "rating": 5, "content": "还没收货就想评"})
    assert resp.status_code == 400


def test_review_rejects_foreign_order_item(client, buyer_token, seller_token,
                                           review_env, address_id, make_user):
    """不能拿别人的订单明细去评价（按不存在处理，不泄露）"""
    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    item_id = order["items"][0]["id"]

    make_user("rv_buyer2", "buyer2123", "customer")
    other = _login(client, "rv_buyer2", "buyer2123")
    resp = client.post(f"{BASE}/reviews", headers=other,
                       json={"order_item_id": item_id, "rating": 5, "content": "蹭个评价"})
    assert resp.status_code == 404


def test_review_rating_bounds(client, buyer_token, seller_token, review_env, address_id):
    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    item_id = order["items"][0]["id"]
    for rating in (0, 6):
        resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                           json={"order_item_id": item_id, "rating": rating, "content": "评个分"})
        assert resp.status_code >= 400


# ===== 评价主流程 =====

def test_review_flow_public_list_and_stats(client, buyer_token, seller_token,
                                           review_env, address_id):
    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    item_id = order["items"][0]["id"]
    product_id = review_env["product"]

    # 已完成订单明细出现在「可评价」列表，且带订单号
    resp = client.get(f"{BASE}/reviews/my/reviewable", headers=buyer_token)
    assert resp.status_code == 200
    reviewable = resp.json()["data"]
    assert item_id in [i["order_item_id"] for i in reviewable]
    assert reviewable[0]["order_no"] == order["order_no"]

    # 发表评价
    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": item_id, "rating": 5,
                             "content": "降噪效果一流，续航给力！"})
    assert resp.status_code == 200
    review = resp.json()["data"]
    assert review["rating"] == 5
    # 用户名脱敏展示
    assert review["username"] not in ("rv_buyer", "")
    assert "**" in review["username"]

    # 重复评价同一明细 → 409
    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": item_id, "rating": 4, "content": "再评一次"})
    assert resp.status_code == 409

    # 评价后不再出现在「可评价」列表
    resp = client.get(f"{BASE}/reviews/my/reviewable", headers=buyer_token)
    assert item_id not in [i["order_item_id"] for i in resp.json()["data"]]

    # 公开评价列表：游客可见，带统计
    resp = client.get(f"{BASE}/products/{product_id}/reviews")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["stats"]["avg_rating"] == 5.0
    assert body["stats"]["positive_rate"] == 100
    assert body["items"][0]["content"] == "降噪效果一流，续航给力！"
    assert body["items"][0]["product_name"] == "评价测试耳机"

    # 商品详情聚合评价数与均分
    resp = client.get(f"{BASE}/products/{product_id}")
    detail = resp.json()["data"]
    assert detail["review_count"] == 1
    assert detail["avg_rating"] == 5.0


def test_review_stats_mixed_ratings(client, buyer_token, seller_token,
                                    review_env, address_id, make_user):
    """多个买家评价后统计正确（好评率按 4/5 星计）"""
    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": order["items"][0]["id"],
                             "rating": 3, "content": "一般般"})
    assert resp.status_code == 200

    # 第二位买家自建地址 → 再买一件 → 打 5 星
    make_user("rv_buyer2", "buyer2123", "customer")
    other = _login(client, "rv_buyer2", "buyer2123")
    addr2 = _add_address(client, other, "王二")
    client.post(f"{BASE}/cart/items", headers=other,
                json={"product_id": review_env["product"], "quantity": 1})
    order2 = client.post(f"{BASE}/orders", headers=other,
                         json={"address_id": addr2}).json()["data"]
    client.post(f"{BASE}/orders/{order2['id']}/pay", headers=other)
    client.post(f"{BASE}/merchant/orders/{order2['id']}/ship",
                headers=seller_token, json={"logistics": "SF888"})
    client.post(f"{BASE}/orders/{order2['id']}/confirm", headers=other)
    resp = client.post(f"{BASE}/reviews", headers=other,
                       json={"order_item_id": order2["items"][0]["id"],
                             "rating": 5, "content": "非常好"})
    assert resp.status_code == 200

    resp = client.get(f"{BASE}/products/{review_env['product']}/reviews")
    stats = resp.json()["data"]["stats"]
    assert stats["total"] == 2
    assert stats["avg_rating"] == 4.0
    assert stats["per_star"]["3"] == 1 and stats["per_star"]["5"] == 1
    assert stats["positive_rate"] == 50


def test_merchant_reply_flow(client, buyer_token, seller_token, review_env, address_id):
    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    item_id = order["items"][0]["id"]
    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": item_id, "rating": 4, "content": "总体不错"})
    review_id = resp.json()["data"]["id"]

    # 顾客无权访问商家评价接口
    assert client.get(f"{BASE}/merchant/reviews", headers=buyer_token).status_code == 403

    # 本店商家可看到并回复
    resp = client.get(f"{BASE}/merchant/reviews", headers=seller_token)
    assert resp.status_code == 200
    assert review_id in [r["id"] for r in resp.json()["data"]["items"]]

    resp = client.post(f"{BASE}/merchant/reviews/{review_id}/reply",
                       headers=seller_token, json={"reply": "感谢支持，欢迎再次光临！"})
    assert resp.status_code == 200
    assert resp.json()["data"]["reply"] == "感谢支持，欢迎再次光临！"
    assert resp.json()["data"]["replied_at"]

    # 一条评价只能回复一次（重复回复按冲突处理）
    resp = client.post(f"{BASE}/merchant/reviews/{review_id}/reply",
                       headers=seller_token, json={"reply": "再回一次"})
    assert resp.status_code == 409

    # 回复内容游客可见
    resp = client.get(f"{BASE}/products/{review_env['product']}/reviews")
    assert resp.json()["data"]["items"][0]["reply"] == "感谢支持，欢迎再次光临！"


def test_reply_scoped_to_own_store(client, buyer_token, seller_token, review_env,
                                   address_id, make_user):
    """其他商家（平台管理员）看不到、也不能回复别家店铺的评价 → 404"""
    make_user("rv_admin", "admin123", "admin")
    other_admin = _login(client, "rv_admin", "admin123")

    order = _completed_order(client, buyer_token, seller_token, review_env, address_id)
    item_id = order["items"][0]["id"]
    resp = client.post(f"{BASE}/reviews", headers=buyer_token,
                       json={"order_item_id": item_id, "rating": 5, "content": "好评"})
    review_id = resp.json()["data"]["id"]

    resp = client.get(f"{BASE}/merchant/reviews", headers=other_admin)
    assert review_id not in [r["id"] for r in resp.json()["data"]["items"]]

    resp = client.post(f"{BASE}/merchant/reviews/{review_id}/reply",
                       headers=other_admin, json={"reply": "越权回复"})
    assert resp.status_code == 404
