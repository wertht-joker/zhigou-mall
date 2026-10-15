"""RRF（Reciprocal Rank Fusion）融合多路召回

score(d) = Σ 1 / (k + rank_i(d))

只看每条通路里的排名，不比较各通路的分数量纲，因此「向量分数」与
「BM25 分数」可以直接融合，无需归一化，简单且稳健。
"""


def rrf(rankings: list[list[dict]], k: int = 60) -> list[dict]:
    """把多路召回结果融合成一个按融合分降序的列表

    rankings: 每路都是一批命中（含 doc_id / chunk_index / text），按各自排名排序
    返回：按 (doc_id, chunk_index) 去重后的融合结果，score 为 RRF 分数
    """
    merged: dict[tuple, dict] = {}
    for hits in rankings:
        for rank, hit in enumerate(hits, start=1):
            key = (hit.get("doc_id"), hit.get("chunk_index"))
            entry = merged.get(key)
            if entry is None:
                entry = dict(hit)
                entry["score"] = 0.0
                merged[key] = entry
            entry["score"] += 1.0 / (k + rank)

    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)
