"""演示数据种子服务：启动时幂等写入商城演示数据

- 平台（默认租户）= 智购自营官方旗舰店；另建一家商家店铺演示多商家入驻
- 商品分类 + 京东风格商品数据
- 演示顾客 + 收货地址 + 历史订单（供 AI 客服「查我的订单」直接演示）
- 将 samples/ 下的客服知识文档自动导入平台知识库（可关闭）

全部操作幂等：已有数据（按唯一键判断）则跳过，可安全重复启动。
"""
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database import SessionLocal
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCategory
from app.models.qa_event import QaEvent
from app.models.user import User
from app.repositories.category_repository import CategoryRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.product_repository import (
    ProductCategoryRepository,
    ProductRepository,
    ProductVariantRepository,
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


# 多规格演示数据：商品名 → [(规格名, 售价, 原价, 库存)]
VARIANT_SEEDS = [
    ("智星 X1 5G 智能手机", [
        ("12GB+256GB 曜石黑", 3999.0, 4299.0, 120),
        ("16GB+512GB 曜石黑", 4599.0, 4899.0, 50),
        ("16GB+1TB 冰川蓝", 5299.0, 5599.0, 30),
    ]),
    ("智星 Book 14 轻薄笔记本", [
        ("16G+1T 深空灰", 5499.0, 5999.0, 80),
        ("32G+1T 深空灰", 6499.0, 6999.0, 40),
    ]),
    ("星辰 Pad 11 英寸平板", [
        ("8G+256G 星空灰", 2299.0, 2699.0, 60),
        ("12G+512G 星空灰", 2899.0, 3199.0, 30),
    ]),
]


def run_seed() -> None:
    """启动入口：建表后写入全部演示数据"""
    db = SessionLocal()
    try:
        platform = _ensure_stores(db)
        _ensure_users(db, platform)
        categories = _ensure_categories(db)
        _ensure_knowledge_categories(db, platform.id)
        _ensure_products(db, platform.id, categories)
        _ensure_variants(db)
        _ensure_demo_customer_data(db)
        _ensure_demo_reviews(db)
        _ensure_demo_qa_events(db, platform)
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

    def _create(username: str, password: str, role: str,
                tenant_id: int | None) -> None:
        if user_repo.get_by_username(username):
            return
        user_repo.create(
            username=username,
            password_hash=security.hash_password(password),
            role=role,
            tenant_id=tenant_id,
        )
        logger.info("已创建演示账号：%s / %s（%s）", username, password, role)

    # 平台管理员不归属商家；shop 是第三方商家管理员；self 是自营店铺店长
    _create("admin", "admin123", "platform_admin", None)
    _create("self", "self123", "admin", platform.id)
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
        ("运动户外", "🏃", 7),
        ("美妆个护", "💄", 8),
        ("图书文娱", "📚", 9),
    ]
    existing = {c.name: c.id for c in repo.list()}
    for name, icon, sort in seeds:
        if name not in existing:
            category = repo.create(name, icon, sort)
            existing[name] = category.id
    return existing


def _ensure_knowledge_categories(db: Session, tenant_id: int) -> None:
    """平台知识库分类（AI 客服文档归档）"""
    repo = CategoryRepository(db)
    existing = {c.name for c in repo.list(tenant_id)}
    for name, sort in [
        ("售后服务", 1),
        ("物流配送", 2),
        ("会员与积分", 3),
        ("购物指南", 4),
    ]:
        if name not in existing:
            repo.create(name=name, sort=sort, tenant_id=tenant_id)


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
        # 服饰鞋包
        (platform_tenant_id, "轻量缓震运动鞋", "透气网面 男女同款跑步鞋",
         269.0, 329.0, 300, 1860, "👟", "shoes.jpg", "服饰鞋包",
         "单只约 230g，回弹中底，日常通勤与慢跑都合适。"),
        (platform_tenant_id, "纯棉基础款 T 恤", "100% 新疆棉 多色可选",
         79.0, 99.0, 800, 6420, "👕", "tshirt.jpg", "服饰鞋包",
         "260g 重磅纯棉，不易变形，四季可穿的基础款。"),
        (platform_tenant_id, "城市通勤双肩包", "15.6 英寸电脑仓 防泼水",
         189.0, 239.0, 260, 1245, "🎒", "backpack.jpg", "服饰鞋包",
         "独立电脑隔层，背部透气，出差通勤一包搞定。"),
        # 食品生鲜
        (platform_tenant_id, "云南高山蓝莓 4 盒装", "当季鲜果 果径 18mm+",
         89.0, 119.0, 400, 3310, "🫐", "blueberry.jpg", "食品生鲜",
         "冷链直发，果粉完整，酸甜适口，开盒即食。"),
        (platform_tenant_id, "原切牛排套餐 1.5kg", "谷饲西冷 10 片装",
         199.0, 259.0, 200, 1580, "🥩", "steak.jpg", "食品生鲜",
         "原切不拼接，独立真空包装，送黄油与黑椒酱。"),
        (platform_tenant_id, "每日坚果礼盒 30 包", "6 种坚果科学配比",
         129.0, 169.0, 500, 4870, "🥜", "nuts.jpg", "食品生鲜",
         "独立小包锁鲜，无添加蔗糖，办公室与送礼皆宜。"),
        # 运动户外
        (platform_tenant_id, "加厚防滑瑜伽垫", "10mm 回弹 TPE 材质",
         99.0, 139.0, 350, 2210, "🧘", "yogamat.jpg", "运动户外",
         "双面防滑纹路，回弹护膝，附赠绑带与收纳袋。"),
        (platform_tenant_id, "户外折叠露营椅", "航空铝架 承重 150kg",
         159.0, 219.0, 180, 960, "🏕️", "campingchair.jpg", "运动户外",
         "一秒展开，收纳后仅 38cm，附带便携提袋。"),
        (platform_tenant_id, "智能计数跳绳", "无绳/有绳双模式",
         69.0, 99.0, 600, 3560, "🏃", "jumprope.jpg", "运动户外",
         "屏幕实时计数，支持卡路里估算，居家健身方便。"),
        # 美妆个护
        (platform_tenant_id, "氨基酸温和洁面乳", "敏感肌适用 120g",
         79.0, 109.0, 700, 5120, "🧴", "cleanser.jpg", "美妆个护",
         "弱酸性配方，洗后不紧绷，早晚均可使用。"),
        (platform_tenant_id, "玻尿酸保湿修护面霜", "50g 深层锁水",
         129.0, 179.0, 450, 2760, "💧", "facecream.jpg", "美妆个护",
         "多重玻尿酸复配，质地清爽，换季保湿维稳。"),
        (platform_tenant_id, "声波电动牙刷", "5 档模式 90 天续航",
         199.0, 299.0, 380, 1980, "🪥", "toothbrush.jpg", "美妆个护",
         "声波震动清洁，智能计时，附赠 2 支刷头。"),
        # 图书文娱
        (platform_tenant_id, "《深入理解计算机系统》", "原书第 3 版 精装",
         139.0, 168.0, 150, 870, "📘", "csapp.jpg", "图书文娱",
         "计算机专业经典教材，覆盖程序结构与系统原理。"),
        (platform_tenant_id, "桌面拼装积木花束", "520 颗粒 解压摆件",
         89.0, 129.0, 320, 1640, "🧱", "blocks.jpg", "图书文娱",
         "免胶拼装，附步骤图，成品可长期摆放装饰桌面。"),
        (platform_tenant_id, "无线蓝牙翻页笔", "教师/演讲适用 100 米遥控",
         59.0, 89.0, 500, 2310, "📡", "presenter.jpg", "图书文娱",
         "支持翻页、全屏、黑屏，USB-C 充电，即插即用。"),
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
        (None, "星辰降噪运动耳机", "IPX5 防水 30 小时续航",
         299.0, 399.0, 200, 1120, "🎧", "sportsearbuds.jpg", "运动户外",
         "耳挂式稳固佩戴，运动防汗，支持环境音模式。"),
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


def _ensure_variants(db: Session) -> None:
    """为演示商品补齐多规格（幂等：已有规格的商品跳过）

    同步商品汇总字段：price = 最低规格价，stock = 各规格库存之和，
    与商家后台保存规格时的规则保持一致。
    """
    repo = ProductVariantRepository(db)
    product_repo = ProductRepository(db)
    created = 0
    for product_name, variants in VARIANT_SEEDS:
        product = product_repo.get_by_name(product_name)
        if not product or repo.list_by_product(product.id):
            continue
        for spec, price, original, stock in variants:
            repo.create(
                product_id=product.id,
                spec=spec,
                price=price,
                original_price=original,
                stock=stock,
            )
            created += 1
        product.price = min(v[1] for v in variants)
        product.stock = sum(v[3] for v in variants)
        db.commit()
    if created:
        logger.info("已写入商品规格 %d 个", created)


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


def _reindex_uploaded_docs(db: Session, tenant_id: int,
                           existing_docs: dict, indexed_names: set[str]) -> int:
    """向量库为空时，把 uploads/ 下已上传文档重建索引

    切换向量后端（Milvus → 本地 SQLite）后 documents 元数据还在，
    但向量需要重建；政策文档不在 samples/ 里，必须从 uploads/ 补齐，
    否则历史政策版本会从检索结果里消失。
    """
    from app.rag import embedding, loader, splitter, vector_store

    upload_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
    )
    repo = DocumentRepository(db)
    imported = 0
    for name, doc in existing_docs.items():
        if name in indexed_names:
            continue
        path = os.path.join(upload_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            text = loader.load_document(path, doc.type or "md")
            if not text.strip():
                continue
            chunks = splitter.split_text(text)
            if not chunks:
                continue
            vectors = embedding.embed(chunks)
            vector_store.insert_chunks(
                doc.id, chunks, vectors, tenant_id,
                policy_key=doc.policy_key,
                doc_version=doc.version,
                effective_from=doc.effective_from,
                effective_to=doc.effective_to,
            )
            doc.chunk_count = len(chunks)
            doc.status = "done"
            repo.save(doc)
            imported += 1
        except Exception as exc:  # 单篇失败不影响其他文档重建
            logger.warning("已上传文档重建索引失败（%s）：%s", name, exc)
    return imported


def _ensure_demo_qa_events(db: Session, platform) -> None:
    """按商家预置知识缺口演示事件（每个商家只写一次）

    覆盖：检索无结果、证据不足、顾客点踩、忠实度偏低；
    自营店与第三方商家各有一组，用于演示「缺口按商家隔离」。
    """
    demo = UserRepository(db).get_by_username("demo")
    user_id = demo.id if demo else None
    now = datetime.now()

    platform_seeds = [
        ("支持花呗分期吗", 0, "hybrid+rerank", "insufficient", None, None),
        ("可以用花呗分期付款吗", 0, "hybrid+rerank", "insufficient", None, None),
        ("发票怎么开", 0, "hybrid", "insufficient", None, None),
        ("能开发票吗", 0, "hybrid", "insufficient", None, None),
        ("退货运费谁承担", 2, "hybrid+rerank", "partial", 0.42, "down"),
        ("退货的运费谁出", 1, "hybrid+rerank", "partial", 0.48, "down"),
        ("可以修改收货地址吗", 1, "hybrid+rerank", "partial", 0.52, "down"),
        ("发货后能改地址吗", 1, "hybrid+rerank", "partial", 0.55, "down"),
    ]
    merchant_seeds = [
        ("星辰数码支持货到付款吗", 0, "hybrid+rerank", "insufficient", None, None),
        ("可以货到付款吗", 0, "hybrid", "insufficient", None, None),
        ("你们店有延保服务吗", 0, "hybrid+rerank", "insufficient", None, None),
        ("耳机坏了怎么保修", 1, "hybrid+rerank", "partial", 0.5, "down"),
    ]

    def _seed_tenant(tenant, seeds) -> int:
        if not tenant or db.query(QaEvent).filter(
            QaEvent.tenant_id == tenant.id
        ).count() > 0:
            return 0
        for index, (query, sources, route, sufficiency, faithfulness, feedback) in enumerate(seeds):
            db.add(QaEvent(
                tenant_id=tenant.id,
                user_id=user_id,
                session_id=None,
                message_id=None,
                query=query,
                answer="（演示数据）知识库未覆盖该问题，系统提示转人工核实。",
                sources_count=sources,
                sufficiency=sufficiency,
                faithfulness=faithfulness,
                route=route,
                feedback=feedback,
                handled=False,
                created_at=now - timedelta(days=index % 5, hours=index),
            ))
        db.commit()
        return len(seeds)

    merchant = TenantRepository(db).get_by_code(DEMO_MERCHANT_CODE)
    written = _seed_tenant(platform, platform_seeds)
    written += _seed_tenant(merchant, merchant_seeds)
    if written:
        logger.info("已写入 %d 条知识缺口演示事件（按商家隔离）", written)


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
    existing_docs = {d.name: d for d in repo.list(tenant_id=tenant_id)}
    # 新集合（如 v3 增加政策版本字段）首次启动时向量为空，
    # 但 documents 元数据还在：此时强制从 samples/ 重建索引，避免“有元数据没向量”。
    needs_reindex = not vector_store.has_chunks(tenant_id)
    imported = 0
    indexed_names: set[str] = set()
    for filename in sorted(os.listdir(samples_dir)):
        if not filename.lower().endswith((".md", ".txt")):
            continue
        if filename in existing_docs and not needs_reindex:
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
            doc = existing_docs.get(filename)
            if doc is None:
                doc = repo.create(filename, "md", tenant_id)
            doc.size = os.path.getsize(path)
            vector_store.insert_chunks(
                doc.id, chunks, vectors, tenant_id,
                policy_key=doc.policy_key,
                doc_version=doc.version,
                effective_from=doc.effective_from,
                effective_to=doc.effective_to,
            )
            doc.chunk_count = len(chunks)
            doc.status = "done"
            repo.save(doc)
            imported += 1
            indexed_names.add(filename)
        except Exception as exc:  # 模型/向量库不可用时不阻断启动
            logger.warning("知识文档导入失败（%s）：%s", filename, exc)

    if needs_reindex:
        imported += _reindex_uploaded_docs(
            db, tenant_id, existing_docs, indexed_names
        )

    if imported:
        from app.core.redis import bump_kb_version

        bump_kb_version()
        logger.info("已自动导入平台知识库文档 %d 篇（目录 %s）", imported, samples_dir)
