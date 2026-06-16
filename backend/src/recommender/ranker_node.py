"""
推荐图中的 fallback ranker 节点。

当 self-query 因过滤条件过严或索引缺失没有召回到结果时，
这里会加载离线生成好的 cross-encoder reranker 作为兜底检索链路。
"""

import os
import pickle
import sys
from typing import Any, List

from langchain.schema import Document
from langchain_huggingface import HuggingFaceEmbeddings
from loguru import logger

# local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import settings
from src.recommender.state import RecState
from src.recommender.utils import doc_to_product_item

# 进程内缓存的 fallback ranker。
# pickle 一次加载几十 MB，没有缓存的话每次请求都会重复 IO。
_cross_encoder_retriever = None


def serialize_documents(docs: List[Document]) -> tuple[str, list[dict[str, Any]]]:
    """Format ranker results for both RAG input and API output."""
    formatted_docs = "\n\n".join([f"- {doc.page_content}" for doc in docs])
    product_items = [doc_to_product_item(doc) for doc in docs]
    return formatted_docs, product_items


def load_cross_encoder_model() -> HuggingFaceEmbeddings:
    """加载离线保存的 fallback ranker（首次调用真正读取 pickle，后续从模块缓存返回）。"""
    global _cross_encoder_retriever
    if _cross_encoder_retriever is not None:
        return _cross_encoder_retriever
    try:
        with open(settings.CROSS_ENCODER_RERANKER_PATH, "rb") as f:
            _cross_encoder_retriever = pickle.load(f)
        logger.info("Cross-encoder model loaded.")
        return _cross_encoder_retriever
    except Exception as e:
        logger.exception("Failed to load cross-encoder model.")
        raise e


def build_ranker(query: str):
    """
    执行 fallback 检索。

    这里加载的并不是单独的 cross-encoder 模型权重，
    而是已经封装好 FAISS + BM25 + rerank 的可调用检索器。
    """
    cross_encoder = load_cross_encoder_model()

    product_docs = cross_encoder.invoke(query)
    logger.info(f"Retrieved {len(product_docs)} documents.")

    return serialize_documents(product_docs)


def ranker_node(state: RecState) -> RecState:
    """
    图节点包装：把兜底检索结果回写到共享状态，供后续 RAG 使用。
    """
    query = state["query"]
    state["products"], state["product_items"] = build_ranker(query)
    return state
