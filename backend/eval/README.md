# Recommendation Evaluation

Offline retrieval evaluation for the MetaFit hybrid recommender.

## Quick start

```bash
# From repo root (requires built indexes under backend/data/indexes/)
python backend/scripts/run_rec_eval.py

# Include self-query baseline (needs LAOZHANG_GPT_API_KEY in .env)
python backend/scripts/run_rec_eval.py --include-self-query

# Custom top-K
python backend/scripts/run_rec_eval.py --top-k 10
```

## Outputs

- `backend/eval/results/latest.json` — full per-query metrics
- `backend/eval/results/latest.md` — thesis-ready summary table
- Timestamped copies under `backend/eval/results/eval_*.json`

## Golden set

`backend/eval/golden_set.json` defines 20 queries with **rule-based relevance**
(e.g. `label_contains: dress`, `price_max: 3000`). Ground truth is computed from
the BM25 catalog at eval time — reproducible without hand-labeling every product.

Extend the golden set before your final thesis run:

1. Add a query + rules that match your demo scenarios.
2. Re-run eval after `python backend/scripts/rebuild_index_from_db.py`.

## Baselines

| ID | Name | Description |
|----|------|-------------|
| B0 | BM25 | Lexical keyword retrieval |
| B1 | FAISS | Dense semantic retrieval |
| B2 | Ensemble | FAISS + BM25 fusion (0.5/0.5) |
| B3 | Ensemble+Rerank | B2 + cross-encoder reranking |
| B4 | SelfQuery | Chroma + LLM metadata filters (optional) |

## Metrics

- **Recall@K** — fraction of relevant items retrieved in top K
- **NDCG@K** — ranking quality (primary metric for reranker ablation)
- **MRR** — how early the first relevant item appears
- **Precision@K** — precision of the retrieved set

## Thesis chapter outline

1. **Dataset** — N products, M evaluation queries, rule-based relevance.
2. **Baselines** — table above with citations to BM25 / dense retrieval literature.
3. **Results** — paste `latest.md` table; discuss B0→B3 gains.
4. **Ablation** — each component's contribution to NDCG@5 / MRR.
5. **Limitations** — small catalog (~107 items), rule-based labels, no live user study yet.
