"""Load product catalog from offline indexes for evaluation ground-truth."""

from __future__ import annotations

import pickle
import re
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import settings
from src.recommender.utils import doc_to_product_item


def load_products_from_bm25() -> list[dict]:
    """Return normalized product dicts with product_id from BM25 index pickle."""
    path = Path(settings.BM25_INDEX_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"BM25 index not found: {path}")
    with open(path, "rb") as f:
        retriever = pickle.load(f)
    docs = getattr(retriever, "docs", None) or []
    products: list[dict] = []
    for doc in docs:
        item = doc_to_product_item(doc)
        pid = item.get("product_id")
        if pid is None:
            continue
        products.append(item)
    return products


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def apply_relevance_rules(products: list[dict], rules: dict) -> set[int]:
    """Derive relevant product_id set from declarative rules in golden_set.json."""
    relevant: set[int] = set()
    label_contains = _norm(rules.get("label_contains", ""))
    brand_contains = _norm(rules.get("brand_contains", ""))
    name_contains = _norm(rules.get("name_contains", ""))
    query_contains = _norm(rules.get("query_contains", ""))
    price_max = rules.get("price_max")
    price_min = rules.get("price_min")
    size_required = rules.get("size")

    for p in products:
        pid = p.get("product_id")
        if pid is None:
            continue
        label = _norm(p.get("label", ""))
        brand = _norm(p.get("brand", ""))
        name = _norm(p.get("product_name", ""))
        price = float(p.get("price") or 0)
        sizes = _norm(p.get("available_sizes", ""))

        if label_contains and label_contains not in label and label_contains not in name:
            continue
        if brand_contains and brand_contains not in brand:
            continue
        if name_contains and name_contains not in name:
            continue
        if query_contains and query_contains not in name and query_contains not in label:
            continue
        if price_max is not None and price > float(price_max):
            continue
        if price_min is not None and price < float(price_min):
            continue
        if size_required:
            tok = _norm(str(size_required))
            if tok not in sizes and f"size {tok}" not in sizes:
                # also check boolean-style size fields aren't in product dict;
                # available_sizes string is enough for catalog from metadata
                continue
        relevant.add(int(pid))
    return relevant


def load_faiss_retriever(k: int):
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.EMBEDDINGS_MODEL_NAME,
        model_kwargs={"device": "cpu"},
    )
    faiss = FAISS.load_local(
        settings.FAISS_INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    return faiss.as_retriever(search_type="similarity", search_kwargs={"k": k})


def load_bm25_retriever():
    with open(settings.BM25_INDEX_PATH, "rb") as f:
        return pickle.load(f)
