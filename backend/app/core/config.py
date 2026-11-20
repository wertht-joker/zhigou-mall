"""全局配置管理：从 .env / 环境变量读取配置"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== 应用 =====
    app_name: str = "智购商城 · AI 智能客服电商平台"
    # 运行环境：development / production；生产环境会强制校验 JWT 密钥
    app_env: str = "development"

    # ===== DeepSeek 对话模型 =====
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ===== Milvus 向量库 =====
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    # v3：chunk 增加政策版本 / 生效期字段（时效政策检索），
    # 旧集合（kb_documents / v2）保留回滚，新集合需重新导入知识文档。
    milvus_collection: str = "kb_documents_v3"

    # ===== 向量库后端 =====
    # sqlite：本地内嵌向量库（默认，无需 Docker，适合演示/单机）；
    # milvus：独立向量服务（docker-compose 部署时由环境变量覆盖）
    vector_backend: str = "sqlite"
    # 本地向量库文件（相对 backend 运行目录）
    vector_db_path: str = "./vector.db"

    # ===== 本地 Embedding 模型 =====
    embedding_model: str = "BAAI/bge-base-zh-v1.5"
    embedding_device: str = "cpu"

    # ===== 数据库 =====
    # 默认 SQLite（零依赖即可跑起来）；生产置为 PostgreSQL，如
    # postgresql+psycopg://kb:kb@localhost:5432/kb
    database_url: str = "sqlite:///./kb.db"
    # 启动时自动把库结构迁移到最新（等价于 alembic upgrade head）
    run_migrations_on_start: bool = True

    # ===== 日志与可观测性 =====
    log_level: str = "INFO"
    # True 输出 JSON 行日志（便于采集），False 输出可读文本
    log_json: bool = True

    # ===== Redis（查询缓存 / 限流；不可用时自动降级）=====
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    # ===== 限流（令牌桶）=====
    rate_limit_enabled: bool = True
    # 桶容量（突发上限）与每秒补充令牌数
    rate_limit_capacity: int = 20
    rate_limit_refill_per_second: float = 0.5

    # ===== JWT =====
    jwt_secret: str = "kb-jwt-secret-please-change-in-production-0123456789"
    jwt_expire_hours: int = 24

    # ===== 检索参数 =====
    top_k: int = 4
    chunk_size: int = 500
    chunk_overlap: int = 50
    # 向量检索先召回的数量，再交给 reranker 精排
    retrieve_top_k: int = 20

    # ===== 混合检索（向量 + BM25）=====
    # 关闭则回退为纯向量召回
    hybrid_retrieval_enabled: bool = True
    # BM25 关键词通路召回的候选数量
    bm25_top_k: int = 20
    # BM25 语料最多取多少块参与打分（演示规模）
    bm25_corpus_limit: int = 1000
    # RRF 融合参数：score = Σ 1 / (rrf_k + rank)
    rrf_k: int = 60

    # ===== Rerank 策略 =====
    # none 不精排 / always 总是精排 / conditional 候选数达到阈值才精排
    rerank_strategy: str = "always"
    rerank_min_candidates: int = 8
    reranker_model: str = "BAAI/bge-reranker-base"

    # ===== 检索缓存（Redis，不可用时自动失效）=====
    retrieval_cache_enabled: bool = True

    # ===== 方向 D：自适应检索路由 + 语义缓存 =====
    # 按问题复杂度选择 none / vector / hybrid_rerank；关闭则沿用固定链路
    adaptive_retrieval_enabled: bool = True
    # 排障/评测用：强制指定策略（none/vector/hybrid/hybrid_rerank），留空表示自动
    retrieval_force_strategy: str = ""
    # 语义缓存：相似问题（embedding 近邻）复用检索结果
    semantic_cache_enabled: bool = True
    # 余弦相似度阈值；0.76 配合意图归一校验，覆盖同义改写并拒绝跨意图命中
    semantic_cache_threshold: float = 0.76
    semantic_cache_ttl_seconds: int = 3600
    # 每个（租户 + 知识库版本 + 日期 + 策略）桶最多保留多少条
    semantic_cache_max_entries: int = 100

    # ===== Agent 参数 =====
    # 工具调用循环的最大轮数，防止模型陷入无限调用
    agent_max_steps: int = 5
    # 单次工具执行的耗时预算（秒）：超过只记 warning 供观测，
    # 因为同步 DB 工具无法安全强杀线程；真正的截止由下面的总预算控制
    tool_timeout_seconds: float = 10.0
    # 一轮问答（含模型调用与全部工具）的总时间预算（秒）
    agent_timeout_seconds: float = 60.0

    # ===== 大模型调用重试 =====
    # 网络抖动 / 限流 / 5xx 时的最大尝试次数（指数退避）
    llm_max_retries: int = 2
    # 连接超时（秒）：模型服务不可达时尽快失败，走本地降级回答
    llm_connect_timeout: float = 5.0
    # 读取超时（秒）：给模型生成留足时间
    llm_read_timeout: float = 60.0

    # ===== 可信回答守卫（方向 B）=====
    # 关闭后不计算充分性与 claim 校验，SSE 也不再推 verify 事件
    faithfulness_enabled: bool = True
    # 证据充分性门控阈值：问题关键词覆盖率低于该值判为 partial
    sufficiency_threshold: float = 0.6
    # 句子忠实度阈值：supported / total 低于该值触发低置信提示
    faithfulness_threshold: float = 0.8
    # 单条答案最多校验多少句，防止长答案把校验成本拖长
    verifier_max_claims: int = 8

    # ===== 订单超时自动取消 =====
    # 待付款订单超过该时长自动取消并回补库存（防止库存被长期占用）
    order_pending_timeout_minutes: int = 30
    # 后台清理任务开关与扫描间隔（秒）
    order_expire_sweep_enabled: bool = True
    order_expire_sweep_interval_seconds: int = 60

    # ===== 演示数据种子 =====
    # 启动时写入演示店铺 / 商品 / 顾客历史订单
    seed_demo_data: bool = True
    # 启动时把 samples/ 下的客服知识文档导入平台知识库（需可加载 Embedding 模型）
    seed_knowledge: bool = True
    # 知识文档目录（相对项目根目录）
    samples_dir: str = "samples"


# 全局单例，供各模块 import
settings = Settings()

# 生产环境安全兜底：默认密钥只能用于本地演示，必须显式覆盖
_DEFAULT_JWT_SECRET = "kb-jwt-secret-please-change-in-production-0123456789"
if (settings.app_env or "").lower() in {"prod", "production"}:
    if settings.jwt_secret == _DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "生产环境必须通过环境变量 JWT_SECRET 配置强随机密钥（不能使用默认值）"
        )


# 示例占位符：.env.example / 未填写时会出现
_DEEPSEEK_PLACEHOLDERS = {
    "sk-xxxxxxxxxxxxxxxx",
    "sk-你的deepseek-key",
}


def deepseek_key_status() -> tuple[bool, str]:
    """校验 DeepSeek Key 是否可用，返回 (是否可用, 不可用原因)。

    含中文/全角字符的 Key 会让 HTTP 请求头编码失败（UnicodeEncodeError），
    因此必须在调用模型前拦截，给前端一个可读的错误提示。
    """
    key = (settings.deepseek_api_key or "").strip()
    if not key:
        return False, "未配置 DEEPSEEK_API_KEY"
    if not key.isascii():
        return False, "DEEPSEEK_API_KEY 含中文或全角字符"
    if key in _DEEPSEEK_PLACEHOLDERS:
        return False, "DEEPSEEK_API_KEY 仍是示例占位符"
    return True, ""

