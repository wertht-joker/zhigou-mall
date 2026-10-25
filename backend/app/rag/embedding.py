"""本地 Embedding：使用 BGE 模型做文本向量化（离线，免 API）

sentence_transformers 较重（连带 torch 约 2GB），采用延迟导入：
模块导入不触发模型库加载，真正调用 embed() 时才需要它已安装。
"""
import os

# 国内访问 huggingface.co 会超时，走镜像加速下载
# 用 setdefault 保证：用户若已设 HF_ENDPOINT 则尊重其配置
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from app.core.config import settings

# 模块级缓存，避免每次请求都重新加载模型（模型加载较慢）
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "未安装 sentence-transformers，无法本地向量化。"
                "请执行：pip install sentence-transformers（首次会下载 BGE 模型约 400MB）"
            ) from exc
        # 首次调用会从 HuggingFace 下载模型（约 400MB），国内可设 HF_ENDPOINT 镜像
        _model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """批量生成向量（归一化，便于用余弦相似度检索）"""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()
