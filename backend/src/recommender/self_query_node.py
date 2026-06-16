"""
Self-query 检索节点。

这一步的目标不是简单向量召回，而是先让 LLM 把自然语言问题拆成：
- 语义查询文本
- 结构化过滤条件（价格、尺码、品类等）

随后再交给 Chroma 做带元数据过滤的检索。
"""

import os
import sys
from functools import lru_cache
from typing import Any, List

from langchain.chains.query_constructor.base import load_query_constructor_runnable
from langchain.retrievers import SelfQueryRetriever
from langchain.schema import Document
from langchain_chroma import Chroma
from langchain_core.runnables import RunnableLambda
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import settings
from src.recommender.state import RecState
from src.recommender.utils import CustomChromaTranslator, doc_to_product_item, get_metadata_info

# 进程内缓存：Chroma 索引 + SelfQueryRetriever 都比较重，每次请求都重建会显著拖慢首响应。
_chroma_index = None
_self_query_chain = None


def serialize_documents(docs: List[Document]) -> tuple[str, list[dict[str, Any]]]:
    """Format LangChain documents for both RAG input and API output."""
    formatted_docs = "\n\n".join([f"- {doc.page_content}" for doc in docs])
    product_items = [doc_to_product_item(doc) for doc in docs]
    return formatted_docs, product_items


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
@lru_cache(maxsize=1)
def initialize_embeddings_model() -> HuggingFaceEmbeddings:
    """Initializes the HuggingFace embeddings model with retries and caching."""
    try:
        model_name = settings.EMBEDDINGS_MODEL_NAME
        embeddings = HuggingFaceEmbeddings(model_name=model_name)
        logger.info(f"Successfully initialized embeddings model: {model_name}")
        return embeddings
    except Exception as e:
        logger.exception("Failed to initialize embeddings model.")
        raise e


def load_chroma_index(embeddings: HuggingFaceEmbeddings) -> Chroma:
    """
    加载并复用 Chroma 索引（模块级缓存）。
    """
    global _chroma_index
    if _chroma_index is not None:
        return _chroma_index
    try:
        logger.info("Loading the chroma index...")
        _chroma_index = Chroma(
            collection_name="product_collection",
            embedding_function=embeddings,
            persist_directory=settings.CHROMA_INDEX_PATH,
        )
        logger.info("Chroma index loaded.")
        logger.info(
            f"Number of documents in Chroma index: {_chroma_index._collection.count()}"
        )
        return _chroma_index
    except Exception as e:
        logger.exception("Failed to load the chroma index.")
        raise e


def build_self_query_chain(vectorstore: Chroma) -> RunnableLambda:
    """
    构建（或复用） self-query 链。

    返回的 Runnable 接受 `{"query": ...}`，内部会先让 LLM 生成结构化查询，
    再把查询翻译成 Chroma 能执行的过滤表达式。

    模块级缓存，避免每次请求重建检索器与 LLM 客户端。
    """
    global _self_query_chain
    if _self_query_chain is not None:
        return _self_query_chain

    api_key = settings.LAOZHANG_GPT_API_KEY.get_secret_value() or None
    llm = ChatOpenAI(
        model=settings.LAOZHANG_GPT_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        base_url=settings.LAOZHANG_GPT_BASE_URL,
        api_key=api_key,
    )

    attribute_info, doc_contents = get_metadata_info()
    translator = CustomChromaTranslator()

    # 先让 LLM 按 ATTRIBUTE_INFO 生成结构化查询，再由 translator 转成 Chroma 过滤器。
    query_constructor = load_query_constructor_runnable(
        llm=llm,
        document_contents=doc_contents,
        attribute_info=attribute_info,
        allowed_comparators=tuple(translator.allowed_comparators),
        allowed_operators=tuple(translator.allowed_operators),
        fix_invalid=True,
    )

    # SelfQueryRetriever 会同时结合语义检索和元数据过滤，不需要手写条件拼接。
    retriever = SelfQueryRetriever(
        query_constructor=query_constructor,
        vectorstore=vectorstore,
        verbose=True,
        structured_query_translator=translator,
    )
    _self_query_chain = RunnableLambda(lambda inputs: retriever.invoke(inputs["query"]))
    return _self_query_chain


def self_query_retrieve(state: RecState) -> RecState:
    """
    根据当前图状态做主召回。

    如果返回为空，不在这里直接报错，而是把 `self_query_state` 标记成 `empty`，
    交给图中的 ranker 节点做兜底召回。
    """
    embeddings = initialize_embeddings_model()
    chroma_index = load_chroma_index(embeddings)
    self_query_chain = build_self_query_chain(chroma_index)

    query = state["query"]
    logger.info(f"Processing query: {query}")

    # 主召回：优先使用结构化过滤命中更符合用户约束的商品。
    results = self_query_chain.invoke({"query": query})
    logger.info(f"Retrieved {len(results)} products for query: {query}")
    if len(results) == 0:
        logger.warning("No products found for the query.")
        state["self_query_state"] = "empty"
        state["product_items"] = []
    else:
        state["self_query_state"] = "success"
        state["products"], state["product_items"] = serialize_documents(results)
    return state
