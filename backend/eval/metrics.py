"""Offline retrieval metrics for recommendation evaluation."""

from __future__ import annotations

import math
from typing import Iterable


def _dedupe_preserve_order(ids: Iterable) -> list:
    seen: set = set()
    out: list = []
    for x in ids:
        if x is None or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def recall_at_k(retrieved: list, relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    top = _dedupe_preserve_order(retrieved)[:k]
    hits = sum(1 for pid in top if pid in relevant)
    return hits / len(relevant)


def precision_at_k(retrieved: list, relevant: set, k: int) -> float:
    top = _dedupe_preserve_order(retrieved)[:k]
    if not top:
        return 0.0
    hits = sum(1 for pid in top if pid in relevant)
    return hits / len(top)


def mrr(retrieved: list, relevant: set) -> float:
    for i, pid in enumerate(_dedupe_preserve_order(retrieved), start=1):
        if pid in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list, relevant: set, k: int) -> float:
    """Binary relevance NDCG@K."""
    top = _dedupe_preserve_order(retrieved)[:k]
    dcg = sum(1.0 / math.log2(i + 2) for i, pid in enumerate(top) if pid in relevant)
    ideal_hits = min(len(relevant), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def aggregate_metrics(
    per_query: list[dict],
    ks: tuple[int, ...] = (5, 10),
) -> dict:
    """Average metrics across queries."""
    if not per_query:
        return {}
    out: dict = {"num_queries": len(per_query), "avg_relevant": 0.0}
    out["avg_relevant"] = sum(q.get("num_relevant", 0) for q in per_query) / len(per_query)
    for k in ks:
        out[f"recall@{k}"] = sum(q[f"recall@{k}"] for q in per_query) / len(per_query)
        out[f"precision@{k}"] = sum(q[f"precision@{k}"] for q in per_query) / len(per_query)
        out[f"ndcg@{k}"] = sum(q[f"ndcg@{k}"] for q in per_query) / len(per_query)
    out["mrr"] = sum(q["mrr"] for q in per_query) / len(per_query)
    return out
