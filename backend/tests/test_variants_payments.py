"""商品多规格（SKU）与支付流水测试

覆盖：规格 CRUD / 规格加购与合并 / 按规格计价与扣库存 / 取消回补 /
支付单创建与确认 / 幂等键 / 旧一步支付接口。
"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


@pytest.fixture
def catalog(engine):
    """一家商家、一个多规格商品、一个无规格商品"""
    from app.models.product import Product, ProductVariant
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services import tenant_service
    from app.utils import security

    Session = sessionmaker(bind=engine)
    session = Session()
    platform = tenant_service.ensure_default_tenant(session)

    merchant = Tenant(code="sku_shop", name="规格测试店")
    session.add(merchant)
    session.commit()
    session.refresh(merchant)

    seller = User(
        username="skuseller",
        password_hash=security.hash_password("seller123"),
        role="admin",
        tenant_id=merchant.id,
    )
    session.add(seller)
    session.commit()

    phone = Product(
        tenant_id=merchant.id, name="规格测试手机", subtitle="多版本可选",
        description="", price=3999.0, original_price=4299.0,
        stock=200, sales=100, image="📱", status="on_sale",
    )
    simple = Product(
        tenant_id=merchant.id, name="规格测试耳机", subtitle="无规格",
        description="", price=199.0, stock=10, sales=10,
        image="🎧", status="on_sale",
    )
    session.add_all([phone, simple])
    session.commit()
    session.refresh(phone)
    session.refresh(simple)

    v1 = ProductVariant(
        product_id=phone.id, spec="12GB+256GB", price=3999.0,
        original_price=4299.0, stock=120,
    )
    v2 = ProductVariant(
        product_id=phone.id, spec="16GB+512GB", price=4599.0,
        original_price=4899.0, stock=80,
    )
    session.add_all([v1, v2])
    session.commit()
    result = {
        "merchant": merchant.id,
        "phone": phone.id,
        "simple": simple.id,
        "v1": v1.id,
        "v2": v2.id,
        "platform": platform.id,
    }
    session.close()
    return result


def _login(client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


@pytest.fixture
def buyer_token(client, make_user):
    make_user("skubuyer", "buyer123", "customer")
    return _login(client, "skubuyer", "buyer123")


@pytest.fixture
def seller_token(client, catalog):
    return _login(client, "skuseller", "seller123")


@pytest.fixture
def address_id(client, buyer_token):
    resp = client.post(f"{BASE}/addresses", headers=buyer_token, json={
        "receiver": "李雷", "phone": "13800138000",
        "region": "北京市 朝阳区", "detail": "幸福小区 3 号楼 201", "is_default": True,
    })
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def _add_cart(client, headers, product_id, quantity=1, variant_id=None):
    return client.post(f"{BASE}/cart/items", headers=headers, json={
        "product_id": product_id, "quantity": quantity, "variant_id": variant_id,
    })


def _create_order(client, headers, address_id):
    return client.post(f"{BASE}/orders", headers=headers, json={"address_id": address_id})


# ===== 规格展示与商家维护 =====

def test_product_detail_returns_variants(client, catalog):
    resp = client.get(f"{BASE}/products/{catalog['phone']}")
    data = resp.json()["data"]
    assert data["has_variants"] is True
    assert [v["spec"] for v in data["variants"]] == ["12GB+256GB", "16GB+512GB"]
    assert data["variants"][1]["price"] == 4599.0


def test_merchant_create_and_update_variants(client, seller_token, catalog):
    resp = client.post(f"{BASE}/merchant/products", headers=seller_token, json={
        "name": "规格新建平板", "subtitle": "测试", "price": 100.0, "stock": 0,
        "image": "📟",
        "variants": [
            {"spec": "8G+128G", "price": 999.0, "stock": 5},
            {"spec": "8G+256G", "price": 1299.0, "stock": 3},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["price"] == 999.0  # 最低规格价
    assert data["stock"] == 8      # 规格库存汇总
    assert len(data["variants"]) == 2

    keep = data["variants"][0]
    resp = client.put(f"{BASE}/merchant/products/{data['id']}", headers=seller_token, json={
        "name": "规格新建平板", "subtitle": "测试", "price": 100.0, "stock": 0,
        "image": "📟",
        "variants": [{"id": keep["id"], "spec": "8G+128G", "price": 899.0, "stock": 2}],
    })
    updated = resp.json()["data"]
    assert updated["price"] == 899.0
    assert updated["stock"] == 2
    assert len(updated["variants"]) == 1

    # 清空规格后回落到商品自身价格/库存
    resp = client.put(f"{BASE}/merchant/products/{data['id']}", headers=seller_token, json={
        "name": "规格新建平板", "subtitle": "测试", "price": 799.0, "stock": 9,
        "image": "📟", "variants": [],
    })
    assert resp.json()["data"]["variants"] == []
    assert resp.json()["data"]["price"] == 799.0


def test_merchant_upload_product_image(client, seller_token, catalog):
    """商家上传主图：落盘到 static/uploads，并把 image_url 写回商品"""
    resp = client.post(
        f"{BASE}/merchant/products/{catalog['phone']}/image",
        headers=seller_token,
        files={"file": ("cover.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert resp.status_code == 200
    url = resp.json()["data"]["image_url"]
    assert url.startswith("/static/uploads/products/")

    saved = Path("static") / url.removeprefix("/static/")
    assert saved.exists()
    saved.unlink()


# ===== 购物车：按规格区分 =====

def test_cart_requires_variant_and_merges_by_variant(client, buyer_token, catalog):
    resp = _add_cart(client, buyer_token, catalog["phone"], 1)
    assert resp.json()["code"] == 400
    assert "规格" in resp.json()["message"]

    _add_cart(client, buyer_token, catalog["phone"], 1, catalog["v1"])
    resp = _add_cart(client, buyer_token, catalog["phone"], 2, catalog["v1"])
    cart = resp.json()["data"]
    assert len(cart) == 1
    assert cart[0]["quantity"] == 3
    assert cart[0]["variant"]["spec"] == "12GB+256GB"
    assert cart[0]["unit_price"] == 3999.0

    # 不同规格各占一行
    resp = _add_cart(client, buyer_token, catalog["phone"], 1, catalog["v2"])
    cart = resp.json()["data"]
    assert len(cart) == 2
    assert {c["variant"]["spec"] for c in cart} == {"12GB+256GB", "16GB+512GB"}

    # 超出规格库存
    resp = _add_cart(client, buyer_token, catalog["phone"], 99, catalog["v2"])
    assert resp.json()["code"] == 400


# ===== 订单：规格计价 + 两级库存 =====

def test_order_uses_variant_price_and_stock(client, buyer_token, catalog,
                                            address_id, engine):
    _add_cart(client, buyer_token, catalog["phone"], 2, catalog["v2"])
    resp = _create_order(client, buyer_token, address_id)
    assert resp.status_code == 200
    order = resp.json()["data"]
    assert order["total_amount"] == 4599.0 * 2
    assert order["items"][0]["variant_spec"] == "16GB+512GB"

    Session = sessionmaker(bind=engine)
    session = Session()
    from app.models.product import Product, ProductVariant
    product = session.query(Product).filter(Product.id == catalog["phone"]).first()
    variant = session.query(ProductVariant).filter(ProductVariant.id == catalog["v2"]).first()
    assert product.stock == 198   # 200 - 2
    assert variant.stock == 78    # 80 - 2
    session.close()

    # 取消订单：商品汇总库存与规格库存同时回补
    resp = client.post(f"{BASE}/orders/{order['id']}/cancel", headers=buyer_token)
    assert resp.json()["data"]["status"] == "已取消"
    session = Session()
    product = session.query(Product).filter(Product.id == catalog["phone"]).first()
    variant = session.query(ProductVariant).filter(ProductVariant.id == catalog["v2"]).first()
    assert product.stock == 200
    assert variant.stock == 80
    session.close()


def test_buy_now_skips_cart(client, buyer_token, catalog, address_id, engine):
    """立即购买：不写购物车、直接按规格下单并扣库存"""
    _add_cart(client, buyer_token, catalog["phone"], 1, catalog["v1"])
    before = client.get(f"{BASE}/cart", headers=buyer_token).json()["data"]
    assert len(before) == 1

    resp = client.post(f"{BASE}/orders", headers=buyer_token, json={
        "address_id": address_id,
        "buy_now": {
            "product_id": catalog["phone"],
            "variant_id": catalog["v2"],
            "quantity": 2,
        },
    })
    assert resp.status_code == 200
    order = resp.json()["data"]
    assert order["items"][0]["variant_spec"] == "16GB+512GB"
    assert order["total_amount"] == 4599.0 * 2

    # 购物车保持不变（下单前那条仍在）
    after = client.get(f"{BASE}/cart", headers=buyer_token).json()["data"]
    assert len(after) == 1
    assert after[0]["variant"]["spec"] == "12GB+256GB"
    assert after[0]["quantity"] == 1

    # 商品汇总库存与规格库存都已扣减
    Session = sessionmaker(bind=engine)
    session = Session()
    from app.models.product import Product, ProductVariant
    product = session.query(Product).filter(Product.id == catalog["phone"]).first()
    variant = session.query(ProductVariant).filter(ProductVariant.id == catalog["v2"]).first()
    assert product.stock == 198
    assert variant.stock == 78
    session.close()


def test_pending_order_auto_cancelled_after_timeout(client, buyer_token, catalog,
                                                    address_id, engine):
    """超时未支付：清理任务取消订单并回补商品与规格库存"""
    _add_cart(client, buyer_token, catalog["phone"], 1, catalog["v1"])
    order = _create_order(client, buyer_token, address_id).json()["data"]
    assert order["status"] == "待付款"
    assert order["expire_at"]  # 下单即写入支付截止时间

    Session = sessionmaker(bind=engine)
    session = Session()
    from app.models.order import Order
    from app.models.product import Product, ProductVariant
    from app.services import order_service

    row = session.query(Order).filter(Order.id == order["id"]).first()
    row.expire_at = datetime.now() - timedelta(minutes=1)
    session.commit()

    assert order_service.cancel_expired_orders(session) == 1
    session.refresh(row)
    assert row.status == "已取消"

    product = session.query(Product).filter(Product.id == catalog["phone"]).first()
    variant = session.query(ProductVariant).filter(ProductVariant.id == catalog["v1"]).first()
    assert product.stock == 200
    assert variant.stock == 120
    session.close()


# ===== 支付流水 =====
def _pending_order(client, buyer_token, catalog, address_id):
    _add_cart(client, buyer_token, catalog["phone"], 1, catalog["v1"])
    resp = _create_order(client, buyer_token, address_id)
    assert resp.status_code == 200
    return resp.json()["data"]


def test_payment_create_confirm_and_idempotency(client, buyer_token, catalog,
                                                address_id):
    order = _pending_order(client, buyer_token, catalog, address_id)

    resp = client.post(
        f"{BASE}/orders/{order['id']}/payments",
        headers={**buyer_token, "Idempotency-Key": "pay-key-001"},
        json={"method": "wechat"},
    )
    assert resp.status_code == 200
    payment = resp.json()["data"]
    assert payment["status"] == "pending"
    assert payment["method_label"] == "微信支付"
    assert payment["amount"] == 3999.0

    # 相同幂等键重复提交 → 同一支付单
    resp = client.post(
        f"{BASE}/orders/{order['id']}/payments",
        headers={**buyer_token, "Idempotency-Key": "pay-key-001"},
        json={"method": "wechat"},
    )
    assert resp.json()["data"]["payment_no"] == payment["payment_no"]

    # 支付流水可查
    resp = client.get(f"{BASE}/orders/{order['id']}/payments", headers=buyer_token)
    assert len(resp.json()["data"]) == 1

    # 确认支付 → 订单待发货，记录支付方式
    resp = client.post(f"{BASE}/payments/{payment['payment_no']}/confirm", headers=buyer_token)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["payment"]["status"] == "success"
    assert result["order"]["status"] == "待发货"
    assert result["order"]["payment_method"] == "wechat"
    assert result["order"]["paid_at"]

    # 重复确认幂等（不会重复流转）
    resp = client.post(f"{BASE}/payments/{payment['payment_no']}/confirm", headers=buyer_token)
    assert resp.status_code == 200
    assert resp.json()["data"]["order"]["status"] == "待发货"


def test_legacy_pay_and_cancelled_order(client, buyer_token, catalog, address_id):
    # 旧一步支付接口仍可用
    order = _pending_order(client, buyer_token, catalog, address_id)
    resp = client.post(f"{BASE}/orders/{order['id']}/pay", headers=buyer_token)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "待发货"
    assert resp.json()["data"]["payment_method"] == "alipay"

    # 已取消订单不能再发起支付
    cancelled = _pending_order(client, buyer_token, catalog, address_id)
    client.post(f"{BASE}/orders/{cancelled['id']}/cancel", headers=buyer_token)
    resp = client.post(
        f"{BASE}/orders/{cancelled['id']}/payments",
        headers=buyer_token, json={"method": "alipay"},
    )
    assert resp.status_code == 400
