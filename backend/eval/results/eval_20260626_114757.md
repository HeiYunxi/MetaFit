# Recommendation Retrieval Evaluation

- Generated: 2026-06-26T03:47:52.533658+00:00
- Catalog size: 107
- Queries evaluated: 18
- Top-K: 10

## Aggregate metrics

| Baseline | Recall@5 | NDCG@5 | MRR | Avg relevant | Time (s) |
|----------|----------|--------|-----|--------------|----------|
| B0_BM25 | 0.371 | 0.554 | 0.731 | 20.6 | 0.01 |
| B1_FAISS | 0.357 | 0.569 | 0.647 | 20.6 | 0.24 |
| B2_Ensemble | 0.465 | 0.654 | 0.793 | 20.6 | 0.22 |
| B3_Ensemble+Rerank | 0.443 | 0.706 | 0.778 | 20.6 | 4.42 |

## How to interpret (thesis)

- **B0→B1**: semantic (FAISS) vs lexical (BM25) alone.
- **B2**: hybrid fusion improves coverage over either alone.
- **B3**: cross-encoder reranking improves ranking quality (NDCG/MRR).
- **B4**: self-query adds structured filters (price/size/label) when LLM API is available.

Re-run after rebuilding indexes: `python backend/scripts/rebuild_index_from_db.py`
