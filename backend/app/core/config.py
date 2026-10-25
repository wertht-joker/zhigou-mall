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

    # ===== DeepSeek 对话模型 =====
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ===== Milvus 向量库 =====
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    # 多租户改造后集合新增了 tenant_id 分区键（破坏性变更），改用新集合名，
    # 旧集合（kb_documents）需手动 drop 或忽略，新集合需清库重灌。
    milvus_collection: str = "kb_documents_v2"

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

    # ===== Agent 参数 =====
    # 工具调用循环的最大轮数，防止模型陷入无限调用
    agent_max_steps: int = 5

    # ===== 大模型调用重试 =====
    # 网络抖动 / 限流 / 5xx 时的最大尝试次数（指数退避）
    llm_max_retries: int = 3

    # ===== 演示数据种子 =====
    # 启动时写入演示店铺 / 商品 / 顾客历史订单
    seed_demo_data: bool = True
    # 启动时把 samples/ 下的客服知识文档导入平台知识库（需可加载 Embedding 模型）
    seed_knowledge: bool = True
    # 知识文档目录（相对项目根目录）
    samples_dir: str = "samples"


# 全局单例，供各模块 import
settings = Settings()
