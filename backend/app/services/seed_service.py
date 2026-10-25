"""演示数据种子服务：启动时幂等写入商城演示数据

- 平台（默认租户）= 智购自营官方旗舰店；另建一家商家店铺演示多商家入驻
- 商品分类 + 京东风格商品数据
- 演示顾客 + 收货地址 + 历史订单（供 AI 客服「查我的订单」直接演示）
- 将 samples/ 下的客服知识文档自动导入平台知识库（可关闭）

全部操作幂等：已有数据（按唯一键判断）则跳过，可安全重复启动。
"""
import logging
import os

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database import SessionLocal
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCategory
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.product_repository import (
    ProductCategoryRepository,
    ProductRepository,
)
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services import tenant_service
from app.utils import security

logger = logging.getLogger(__name__)

# 平台自营默认租户改名（历史库中叫「默认租户」，这里统一升级为商城语义）
PLATFORM_STORE_NAME = "智购自营官方旗舰店"
# 演示商家
DEMO_MERCHANT_CODE = "star"
DEMO_MERCHANT_NAME = "星辰数码旗舰店"
# 演示评价账号统一密码
DEMO_REVIEWER_PASSWORD = "123456"

# 实物宣传图目录（backend/static/products，由 /static 静态托管）
PRODUCT_IMG_DIR = "/static/products"

# 演示评价数据：商品 → [(评价人, 星级, 内容, 商家回复|None)]
REVIEW_SEEDS = [
    ("智星 X1 5G 智能手机", [
        ("小明", 5, "手机手感非常棒，屏幕色彩细腻，夜景拍照超出预期，67W 快充半小时就能回血大半，这个价位真的香！",
         "感谢您的认可与支持，欢迎推荐给身边的朋友，祝您使用愉快！"),
        ("红红", 4, "整体满意，系统流畅不卡顿，续航一天半没问题，就是出厂贴膜不太好贴。", None),
        ("大伟", 5, "给爸妈买的，大字体模式操作简单，客服耐心指导设置，第二天就送到了。",
         "祝长辈使用愉快，有问题随时联系我们～"),
    ]),
    ("智能空气净化器 Pro", [
        ("红红", 5, "新房除甲醛买的，APP 能看实时数值，睡眠模式几乎听不到声音，滤网更换还有提醒，很省心。",
         "感谢选择智购自营，有任何问题欢迎随时联系客服～"),
        ("阿丽", 4, "净化效果不错，开一小时 PM2.5 明显下降，就是机身比想象中大一点。", None),
    ]),
    ("AI 智能音箱 mini", [
        ("小明", 5, "语音识别很灵敏，一句话点歌、设闹钟都行，还能控制家里的灯，299 这个价格无敌了。",
         "感谢支持，后续固件会持续升级更多技能哦～"),
        ("大伟", 4, "音质对得起价格，低音比预期好，希望以后支持更多智能家居品牌。", None),
    ]),
    ("主动降噪蓝牙耳机", [
        ("阿丽", 5, "通勤地铁上开启降噪瞬间世界安静了，通透模式切回来说话不耽误，久戴耳朵也不胀痛。",
         "感谢您的详细分享，这正是我们想要带给用户的体验～"),
    ]),
    ("智星 Book 14 轻薄笔记本", [
        ("大伟", 5, "1.4kg 确实轻，通勤放背包没负担，1T 固态够用，开十几个网页加视频会议完全无压力。",
         "感谢认可，选购配件欢迎回店看看～"),
    ]),
    ("全自动扫地机器人", [
        ("小明", 4, "建图很快，扫拖一体省心，床底下的灰全清出来了，就是遇到数据线偶尔会绕住。",
         "感谢反馈！建议清扫前收起地面线材，固件后续会优化防缠绕策略～"),
    ]),
    ("星辰 Watch S 智能手表", [
        ("红红", 5, "表盘精致，血氧心率监测数据看着挺准，14 天续航名副其实，运动模式种类超多。",
         "感谢选择星辰数码，佩戴中如有疑问随时联系店铺客服～"),
    ]),
    ("智能电饭煲 4L", [
        ("阿丽", 5, "煮饭口感可以选，家里人都爱吃 Q 弹那档，预约功能早上起来就能喝到热粥。", None),
    ]),
]


def run_seed() -> None:
    """启动入口：建表后写入全部演示数据"""
    db = SessionLocal()
    try:
        platform = _ensure_stores(db)
        _ensure_users(db, platform)
        categories = _ensure_categories(db)
        _ensure_products(db, platform.id, categories)
        _ensure_demo_customer_data(db)
        _ensure_demo_reviews(db)
        if settings.seed_knowledge:
            _ingest_sample_knowledge(db, platform.id)
    finally:
        db.close()


def _ensure_stores(db: Session):
    """确保平台自营与演示商家两家店铺存在"""
    platform = tenant_service.ensure_default_tenant(db)
    if platform.name in ("默认租户", "default"):
        platform.name = PLATFORM_STORE_NAME
        db.commit()
        db.refresh(platform)

    merchant_repo = TenantRepository(db)
    merchant = merchant_repo.get_by_code(DEMO_MERCHANT_CODE)
    if merchant is None:
        merchant = merchant_repo.create(DEMO_MERCHANT_CODE, DEMO_MERCHANT_NAME)
        logger.info("已创建演示商家：%s（编码 %s）", merchant.name, merchant.code)
    return platform


def _ensure_users(db: Session, platform) -> None:
    """默认账号：平台管理员 / 商家管理员 / 演示顾客"""
    user_repo = UserRepository(db)
    merchant = TenantRepository(db).get_by_code(DEMO_MERCHANT_CODE)

    def _create(username: str, password: str, role: str, tenant_id: int) -> None:
        if user_repo.get_by_username(username):
            return
        user_repo.create(
            username=username,
            password_hash=security.hash_password(password),
            role=role,
            tenant_id=tenant_id,
        )
        logger.info("已创建演示账号：%s / %s（%s）", username, password, role)

    _create("admin", "admin123", "admin", platform.id)
    if merchant:
        _create("shop", "shop123", "admin", merchant.id)
    _create("demo", "demo123", "customer", platform.id)


def _ensure_categories(db: Session) -> dict[str, int]:
    """商品分类（平台级）"""
    repo = ProductCategoryRepository(db)
    seeds = [
        ("手机数码", "📱", 1),
        ("电脑办公", "💻", 2),
        ("家用电器", "🏠", 3),
        ("智能家居", "💡", 4),
        ("服饰鞋包", "👕", 5),
        ("食品生鲜", "🍎", 6),
    ]
    existing = {c.name: c.id for c in repo.list()}
    for name, icon, sort in seeds:
        if name not in existing:
            category = repo.create(name, icon, sort)
            existing[name] = category.id
    return existing


def _ensure_products(db: Session, platform_tenant_id: int,
                     categories: dict[str, int]) -> None:
    """京东风格商品数据：平台自营 + 演示商家"""
    repo = ProductRepository(db)
    products = [
        # (租户|None=演示商家, 名称, 副标题, 价, 原价, 库存, 销量, emoji, 实物图文件, 分类, 描述)
        # 平台自营（智购自营官方旗舰店）
        (platform_tenant_id, "智星 X1 5G 智能手机", "12GB+256GB 曜石黑 120Hz 高刷屏",
         3999.0, 4299.0, 200, 1523, "📱", "smartphone.jpg", "手机数码",
         "6.7 英寸 OLED 直屏，骁龙旗舰芯片，5000mAh 长续航，支持 67W 快充。"),
        (platform_tenant_id, "智星 Book 14 轻薄笔记本", "i7 处理器 16G+1T 高色域屏",
         5499.0, 5999.0, 120, 866, "💻", "laptop.jpg", "电脑办公",
         "1.4kg 轻巧机身，全功能 Type-C，办公通勤两相宜。"),
        (platform_tenant_id, "智能空气净化器 Pro", "除甲醛除 PM2.5 APP 远程操控",
         899.0, 1099.0, 300, 2311, "🌬️", "airpurifier.jpg", "智能家居",
         "CADR 值 600m³/h，滤网更换提醒，睡眠模式静音运行。"),
        (platform_tenant_id, "AI 智能音箱 mini", "语音助手 蓝牙音响 海量内容",
         299.0, 349.0, 500, 5020, "🔊", "speaker.jpg", "智能家居",
         "一句话点歌、查天气、控家电，是音箱也是智能家居中控。"),
        (platform_tenant_id, "智感护眼台灯", "国 AA 级照度 无频闪减蓝光",
         159.0, 199.0, 400, 1877, "💡", "lamp.jpg", "智能家居",
         "自动感光调节亮度，学习阅读两档色温，守护视力。"),
        (platform_tenant_id, "全自动扫地机器人", "激光导航 扫拖一体 4000Pa",
         1299.0, 1599.0, 150, 764, "🤖", "vacuum.jpg", "家用电器",
         "建图规划清扫路线，自动回充， app 远程预约。"),
        (platform_tenant_id, "智能电饭煲 4L", "24 小时预约 球釜内胆",
         349.0, 429.0, 260, 980, "🍚", "ricecooker.jpg", "家用电器",
         "多种煮米口感可选，上盖可拆洗，预约早餐一键搞定。"),
        (platform_tenant_id, "主动降噪蓝牙耳机", "半入耳式 40dB 深度降噪",
         599.0, 799.0, 350, 3245, "🎧", "headphones.jpg", "手机数码",
         "通透模式随时切，单次续航 8 小时，配合充电盒 32 小时。"),
        (platform_tenant_id, "机械键盘 87 键", "RGB 背光 热插拔轴体",
         329.0, 399.0, 220, 1408, "⌨️", "keyboard.jpg", "电脑办公",
         "全键无冲，PBT 键帽，游戏办公手感兼顾。"),
        # 演示商家（星辰数码旗舰店）
        (None, "星辰 Watch S 智能手表", "血氧心率监测 14 天续航",
         1299.0, 1499.0, 180, 653, "⌚", "smartwatch.jpg", "手机数码",
         "100+ 运动模式，5ATM 防水，蓝牙通话。"),
        (None, "星辰 Pad 11 英寸平板", "2.5K 高刷屏 8G+256G",
         2299.0, 2699.0, 90, 412, "📟", "tablet.jpg", "电脑办公",
         "四扬声器影音体验，支持手写笔，网课办公神器。"),
        (None, "星辰移动电源 20000mAh", "22.5W 超级快充 双口输出",
         149.0, 199.0, 600, 2870, "🔋", "powerbank.jpg", "手机数码",
         "数显电量，可上飞机，出门在外不断电。"),
    ]
    star = TenantRepository(db).get_by_code(DEMO_MERCHANT_CODE)
    for tenant_id, name, subtitle, price, original, stock, sales, image, img_file, cat, desc in products:
        if tenant_id is None and star:
            tenant_id = star.id
        image_url = f"{PRODUCT_IMG_DIR}/{img_file}" if img_file else None
        existing = repo.list_merchant(name, tenant_id)
        if existing:
            # 幂等：历史库商品补挂实物图（不覆盖已配置的自定义图）
            product = existing[0]
            if image_url and not (product.image_url or "").startswith(PRODUCT_IMG_DIR):
                product.image_url = image_url
                db.commit()
            continue
        repo.create(
            tenant_id=tenant_id,
            category_id=categories.get(cat),
            name=name,
            subtitle=subtitle,
            description=desc,
            price=price,
            original_price=original,
            stock=stock,
            sales=sales,
            image=image,
            image_url=image_url,
        )
    logger.info("商品数据就绪（共 %d 件在售）", len(repo.list_public()))


def _ensure_demo_customer_data(db: Session) -> None:
    """演示顾客：收货地址 + 两笔历史订单（供 AI 客服演示查订单）"""
    from app.models.address import Address

    user = UserRepository(db).get_by_username("demo")
    if not user:
        return

    if not db.query(Address).filter(Address.user_id == user.id).first():
        db.add(Address(
            user_id=user.id, receiver="李雷", phone="13800138000",
            region="北京市 朝阳区 望京街道", detail="幸福小区 3 号楼 2 单元 201",
            is_default=True,
        ))
        db.commit()

    # 已有订单则不再写演示订单
    if db.query(Order).filter(Order.user_id == user.id).first():
        return

    demo_orders = [
        (["智能空气净化器 Pro", "智感护眼台灯"], "已发货", "顺丰速运 SF1234567890"),
        (["AI 智能音箱 mini"], "已完成", "京东物流 JD9876543210"),
        (["主动降噪蓝牙耳机"], "待付款", ""),
    ]
    from datetime import datetime, timedelta

    base = datetime.now() - timedelta(days=5)
    for i, (product_names, status, logistics) in enumerate(demo_orders):
        items = []
        total = 0.0
        for name in product_names:
            product = ProductRepository(db).get_by_name(name)
            if not product:
                continue
            items.append((product, 1))
            total += product.price
        if not items:
            continue
        order = Order(
            user_id=user.id,
            order_no=f"ZG{base:%Y%m%d}000{len(demo_orders) - i}{i + 1}",
            total_amount=round(total, 2),
            status=status,
            receiver_name="李雷", receiver_phone="13800138000",
            receiver_address="北京市 朝阳区 望京街道 幸福小区 3 号楼 2 单元 201",
            logistics=logistics,
            created_at=base + timedelta(days=i),
        )
        db.add(order)
        db.flush()  # 拿到 order.id 再写明细
        for product, quantity in items:
            db.add(OrderItem(
                order_id=order.id, product_id=product.id,
                merchant_id=product.tenant_id, product_name=product.name,
                image=product.image, price=product.price, quantity=quantity,
            ))
    db.commit()
    logger.info("已写入演示顾客的历史订单")


def _ensure_demo_reviews(db: Session) -> None:
    """演示评价：为热门商品造「已完成」订单并写入评价（含商家回复）

    评价锚定订单明细（一单明细一评），评价人用户名脱敏后前台展示（如 小明 → 小**）。
    幂等：同一用户对同一商品已有评价则跳过。
    """
    from datetime import datetime, timedelta

    from app.models.order import OrderItem
    from app.models.review import Review

    user_repo = UserRepository(db)
    product_repo = ProductRepository(db)
    now = datetime.now()
    created = 0

    for product_name, review_list in REVIEW_SEEDS:
        product = product_repo.get_by_name(product_name)
        if not product:
            continue
        for idx, (username, rating, content, reply) in enumerate(review_list):
            user = user_repo.get_by_username(username)
            if not user:
                user = user_repo.create(
                    username=username,
                    password_hash=security.hash_password(DEMO_REVIEWER_PASSWORD),
                    role="customer",
                    tenant_id=product.tenant_id,
                )
                logger.info("已创建演示评价账号：%s / %s", username, DEMO_REVIEWER_PASSWORD)
            exists = (
                db.query(Review)
                .filter(Review.user_id == user.id, Review.product_id == product.id)
                .first()
            )
            if exists:
                continue
            ordered_at = now - timedelta(days=10 + idx * 3)
            order = Order(
                user_id=user.id,
                order_no=f"ZGR{product.id:03d}{user.id:03d}",
                total_amount=round(product.price, 2),
                status="已完成",
                receiver_name=username,
                receiver_phone="13800000000",
                receiver_address="北京市 朝阳区 望京街道 幸福小区",
                logistics="京东物流 JD8866000123",
                created_at=ordered_at,
            )
            db.add(order)
            db.flush()
            item = OrderItem(
                order_id=order.id, product_id=product.id,
                merchant_id=product.tenant_id, product_name=product.name,
                image=product.image, price=product.price, quantity=1,
            )
            db.add(item)
            db.flush()
            reviewed_at = ordered_at + timedelta(days=4)
            db.add(Review(
                user_id=user.id, product_id=product.id,
                merchant_id=product.tenant_id,
                order_id=order.id, order_item_id=item.id,
                rating=rating, content=content,
                reply=reply,
                replied_at=(reviewed_at + timedelta(days=1)) if reply else None,
                created_at=reviewed_at,
            ))
            created += 1
    if created:
        db.commit()
        logger.info("已写入演示商品评价 %d 条", created)


def _ingest_sample_knowledge(db: Session, tenant_id: int) -> None:
    """把项目根目录 samples/ 下的客服知识文档导入平台知识库（幂等）"""
    from app.rag import embedding, loader, splitter, vector_store

    samples_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", settings.samples_dir)
    )
    if not os.path.isdir(samples_dir):
        logger.warning("知识文档目录不存在，跳过导入：%s", samples_dir)
        return

    repo = DocumentRepository(db)
    existing = {d.name for d in repo.list(tenant_id=tenant_id)}
    imported = 0
    for filename in sorted(os.listdir(samples_dir)):
        if not filename.lower().endswith((".md", ".txt")) or filename in existing:
            continue
        path = os.path.join(samples_dir, filename)
        try:
            text = loader.load_document(path, "md")
            if not text.strip():
                continue
            chunks = splitter.split_text(text)
            if not chunks:
                continue
            vectors = embedding.embed(chunks)
            doc = repo.create(filename, "md", tenant_id)
            doc.size = os.path.getsize(path)
            vector_store.insert_chunks(doc.id, chunks, vectors, tenant_id)
            doc.chunk_count = len(chunks)
            doc.status = "done"
            repo.save(doc)
            imported += 1
        except Exception as exc:  # 模型/向量库不可用时不阻断启动
            logger.warning("知识文档导入失败（%s）：%s", filename, exc)
    if imported:
        logger.info("已自动导入平台知识库文档 %d 篇（目录 %s）", imported, samples_dir)
