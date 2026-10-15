"""BM25 关键词检索通路

中文用 jieba 分词，英文/数字按词切分；BM25Okapi 依据语料词频打分。
与向量通路互补：向量擅长「语义相近」，BM25 擅长精确关键词
（型号、专有名词、代码等），两者用 RRF 融合后召回更稳。
"""
import logging

import jieba
from rank_bm25 import BM25Okapi

# jieba 首次构建词典会打印进度，压到 ERROR 避免污染日志
jieba.setLogLevel(logging.ERROR)


def tokenize(text: str) -> list[str]:
    """分词并归一化（小写 + 去空白）"""
    return [token.strip().lower() for token in jieba.lcut(text or "") if token.strip()]


def search(query: str, corpus_chunks: list[dict], top_k: int) -> list[dict]:
    """在语料上做 BM25 检索

    corpus_chunks: [{"text", "doc_id", "chunk_index"}]（通常是本租户的全部块）
    返回按 BM25 分数降序的命中列表，每项在原字段上追加 score。
    """
    if not corpus_chunks or not query:
        return []

    tokenized_corpus = [tokenize(c["text"]) for c in corpus_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenize(query))

    ranked = sorted(range(len(corpus_chunks)), key=lambda i: scores[i], reverse=True)
    hits = []
    for i in ranked[:top_k]:
        if scores[i] <= 0:  # 完全不相关的直接丢弃
            continue
        hit = dict(corpus_chunks[i])
        hit["score"] = float(scores[i])
        hits.append(hit)
    return hits
