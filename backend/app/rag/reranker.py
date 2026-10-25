"""BGE-reranker 重排序：对检索结果精排，提升答案准确率

sentence_transformers 采用延迟导入（与 embedding.py 同理），失败时由
retriever 的精排策略降级逻辑兜底，不影响召回链路。
"""
import os

# 国内下载模型走镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from app.core.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "未安装 sentence-transformers，无法使用 BGE 精排。"
                "可将 RERANK_STRATEGY 设为 none 跳过精排。"
            ) from exc
        _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    """对候选段落重排序，返回 [(原始索引, 相关度分数)]，按分数降序"""
    if not passages:
        return []
    model = _get_model()
    pairs = [[query, p] for p in passages]
    scores = model.predict(pairs)
    # 分数归一化到 0~1，便于展示
    return sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
