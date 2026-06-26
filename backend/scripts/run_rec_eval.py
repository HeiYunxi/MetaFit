"""
Offline recommendation retrieval evaluation.

Compares retrieval baselines on a rule-based golden set and writes
metrics to backend/eval/results/.

Usage (from repo root):
    python backend/scripts/run_rec_eval.py
    python backend/scripts/run_rec_eval.py --include-self-query
    python backend/scripts/run_rec_eval.py --top-k 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from langchain.retrievers import EnsembleRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain.retrievers import ContextualCompressionRetriever
from langchain_core.documents import Document
from loguru import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval.catalog import (  # noqa: E402
    apply_relevance_rules,
    load_bm25_retriever,
    load_faiss_retriever,
    load_products_from_bm25,
)
from eval.metrics import aggregate_metrics, mrr, ndcg_at_k, precision_at_k, recall_at_k  # noqa: E402
from src.config import settings  # noqa: E402
from src.recommender.self_query_node import (  # noqa: E402
    build_self_query_chain,
    initialize_embeddings_model,
    load_chroma_index,
)
from src.recommender.utils import doc_to_product_item  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
GOLDEN_PATH = EVAL_DIR / "golden_set.json"
RESULTS_DIR = EVAL_DIR / "results"


def _doc_ids(docs: list[Document]) -> list[int]:
    ids: list[int] = []
    for doc in docs:
        item = doc_to_product_item(doc)
        pid = item.get("product_id")
        if pid is not None:
            ids.append(int(pid))
    return ids


def _build_baselines(top_k: int, include_self_query: bool) -> dict:
    baselines: dict = {}

    bm25 = load_bm25_retriever()
    baselines["B0_BM25"] = lambda q, r=bm25: _doc_ids(r.invoke(q))

    faiss_r = load_faiss_retriever(top_k)
    baselines["B1_FAISS"] = lambda q, r=faiss_r: _doc_ids(r.invoke(q))

    ensemble = EnsembleRetriever(
        retrievers=[faiss_r, bm25],
        weights=settings.RETRIEVER_WEIGHTS,
        top_k=top_k,
    )
    baselines["B2_Ensemble"] = lambda q, r=ensemble: _doc_ids(r.invoke(q))

    try:
        cross_model = HuggingFaceCrossEncoder(model_name=settings.CROSS_ENCODER_MODEL_NAME)
        compressor = CrossEncoderReranker(model=cross_model, top_n=top_k)
        reranker = ContextualCompressionRetriever(
            base_compressor=compressor, base_retriever=ensemble,
        )
        baselines["B3_Ensemble+Rerank"] = lambda q, r=reranker: _doc_ids(r.invoke(q))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping B3 (cross-encoder): %s", exc)

    if include_self_query:
        try:
            emb = initialize_embeddings_model()
            chroma = load_chroma_index(emb)
            sq = build_self_query_chain(chroma)
            baselines["B4_SelfQuery"] = lambda q, r=sq: _doc_ids(r.invoke({"query": q}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping B4 (self-query, needs LLM API): %s", exc)

    return baselines


def _load_golden() -> list[dict]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data["queries"]


def run_eval(top_k: int = 10, include_self_query: bool = False) -> dict:
    products = load_products_from_bm25()
    logger.info("Catalog: %d products from BM25 index", len(products))

    golden = _load_golden()
    cases: list[dict] = []
    for entry in golden:
        rel = apply_relevance_rules(products, entry.get("rules") or {})
        if not rel:
            logger.warning("Query %s has zero relevant products — skipped", entry["id"])
            continue
        cases.append({
            "id": entry["id"],
            "query": entry["query"],
            "relevant": rel,
            "rules": entry.get("rules"),
        })
    logger.info("Evaluating %d / %d golden queries", len(cases), len(golden))

    baselines = _build_baselines(top_k, include_self_query)
    summary: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_size": len(products),
        "num_queries": len(cases),
        "top_k": top_k,
        "baselines": {},
        "per_query": {},
    }

    ks = (5, min(10, top_k))
    if top_k < 5:
        ks = (top_k,)

    for name, fn in baselines.items():
        t0 = time.perf_counter()
        per_q: list[dict] = []
        for case in cases:
            retrieved = fn(case["query"])
            row = {
                "id": case["id"],
                "query": case["query"],
                "num_relevant": len(case["relevant"]),
                "retrieved_top": retrieved[:top_k],
                "mrr": mrr(retrieved, case["relevant"]),
            }
            for k in ks:
                row[f"recall@{k}"] = recall_at_k(retrieved, case["relevant"], k)
                row[f"precision@{k}"] = precision_at_k(retrieved, case["relevant"], k)
                row[f"ndcg@{k}"] = ndcg_at_k(retrieved, case["relevant"], k)
            per_q.append(row)
        elapsed = time.perf_counter() - t0
        summary["baselines"][name] = {
            **aggregate_metrics(per_q, ks=ks),
            "elapsed_sec": round(elapsed, 2),
        }
        summary["per_query"][name] = per_q
        logger.info(
            "[%s] recall@5=%.3f ndcg@5=%.3f mrr=%.3f (%.1fs)",
            name,
            summary["baselines"][name].get("recall@5", 0),
            summary["baselines"][name].get("ndcg@5", 0),
            summary["baselines"][name]["mrr"],
            elapsed,
        )

    return summary


def _write_markdown(summary: dict, path: Path) -> None:
  lines = [
      "# Recommendation Retrieval Evaluation",
      "",
      f"- Generated: {summary['generated_at']}",
      f"- Catalog size: {summary['catalog_size']}",
      f"- Queries evaluated: {summary['num_queries']}",
      f"- Top-K: {summary['top_k']}",
      "",
      "## Aggregate metrics",
      "",
      "| Baseline | Recall@5 | NDCG@5 | MRR | Avg relevant | Time (s) |",
      "|----------|----------|--------|-----|--------------|----------|",
  ]
  for name, m in summary["baselines"].items():
      lines.append(
          f"| {name} | {m.get('recall@5', 0):.3f} | {m.get('ndcg@5', 0):.3f} | "
          f"{m['mrr']:.3f} | {m.get('avg_relevant', 0):.1f} | {m.get('elapsed_sec', 0)} |"
      )
  lines += [
      "",
      "## How to interpret (thesis)",
      "",
      "- **B0→B1**: semantic (FAISS) vs lexical (BM25) alone.",
      "- **B2**: hybrid fusion improves coverage over either alone.",
      "- **B3**: cross-encoder reranking improves ranking quality (NDCG/MRR).",
      "- **B4**: self-query adds structured filters (price/size/label) when LLM API is available.",
      "",
      "Re-run after rebuilding indexes: `python backend/scripts/rebuild_index_from_db.py`",
  ]
  path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Offline recommendation retrieval evaluation")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--include-self-query", action="store_true",
                        help="Include B4 Self-Query (requires LAOZHANG_GPT_API_KEY)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary = run_eval(top_k=args.top_k, include_self_query=args.include_self_query)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"eval_{ts}.json"
    md_path = RESULTS_DIR / f"eval_{ts}.md"
    latest_json = RESULTS_DIR / "latest.json"
    latest_md = RESULTS_DIR / "latest.md"

    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    latest_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _write_markdown(summary, md_path)
    _write_markdown(summary, latest_md)

    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    print("\n--- Summary ---")
    for name, m in summary["baselines"].items():
        print(
            f"{name:22s}  R@5={m.get('recall@5', 0):.3f}  "
            f"NDCG@5={m.get('ndcg@5', 0):.3f}  MRR={m['mrr']:.3f}"
        )


if __name__ == "__main__":
    main()
