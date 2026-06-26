"""
向量索引服务：从 MySQL 读取商品数据，重建推荐链路所需的全部离线产物。

产出与 `src/indexing/embedding.py`（CSV 版）完全一致，仅数据来源换成数据库：
- FAISS                  语义向量索引
- BM25Retriever          关键词检索器（pickle）
- ChromaDB               self-query 元数据索引（collection=product_collection）
- cross-encoder reranker fallback 召回器（pickle，ranker_node 运行时加载）

metadata 字段名与 CSV 版对齐（"Product Name"/"Brand"/"Price"/"Image URL"/"Size M"…），
并额外注入 `product_id`，使推荐结果能映射回数据库商品（可点详情、可加购物车）。

注意：重建产物是磁盘文件，而运行时的检索器是进程内全局缓存，
重建完成后需重启服务（或清空对应全局变量）才会加载新索引。
"""

import asyncio
import gc
import os
import pickle
import re
from pathlib import Path

from langchain.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS, Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from loguru import logger

from src.config import settings

# 与 embedding.py 保持一致的尺码别名映射
SUPPORTED_SIZE_ALIASES = {
    "xxxs": "Size XXXS", "3xs": "Size XXXS",
    "xxs": "Size XXS", "2xs": "Size XXS",
    "xs": "Size XS", "s": "Size S", "m": "Size M", "l": "Size L",
    "xl": "Size XL", "xxl": "Size XXL", "2xl": "Size XXL",
    "xxxl": "Size XXXL", "3xl": "Size XXXL",
    "one size": "Size One Size", "one-size": "Size One Size",
    "onesize": "Size One Size", "os": "Size One Size",
}
SUPPORTED_SIZE_FIELDS = list(dict.fromkeys(SUPPORTED_SIZE_ALIASES.values()))

CHROMA_COLLECTION = "product_collection"


def _get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDINGS_MODEL_NAME,
        model_kwargs={"device": "cpu"},
    )


def _to_float(v) -> float:
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        if s == "" or s.lower() == "nan":
            return 0.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _s(v) -> str:
    """统一成非空字符串（Chroma 不接受 None）。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _normalize_size_token(value: str) -> str:
    v = value.strip().lower().replace("size:", "").strip().replace("-", " ")
    return re.sub(r"\s+", " ", v)


def _extract_size_tokens(raw: str) -> list[str]:
    if not raw:
        return []
    out = []
    for tok in re.split(r"[,/|]", raw):
        norm = _normalize_size_token(tok)
        if norm:
            out.append(norm)
    return out


def _build_size_metadata(tokens: list[str]) -> dict[str, bool]:
    labels = {SUPPORTED_SIZE_ALIASES[t] for t in tokens if t in SUPPORTED_SIZE_ALIASES}
    return {field: field in labels for field in SUPPORTED_SIZE_FIELDS}


def _doc_from_product(product: dict) -> Document:
    """从 products 表的一行（含聚合的 sizes）构造与 CSV 版对齐的 Document。"""
    size_tokens = _extract_size_tokens(_s(product.get("sizes")))
    available_sizes = ", ".join(size_tokens)

    name = _s(product.get("product_name"))
    brand = _s(product.get("brand"))
    label = _s(product.get("label"))
    description = _s(product.get("description"))
    price = _to_float(product.get("price"))
    currency = _s(product.get("currency")) or "CNY"
    original_price = _to_float(product.get("original_price"))
    discount = _to_float(product.get("discount_percentage"))
    comp_outer = _s(product.get("composition_outer"))
    comp_lining = _s(product.get("composition_lining"))
    washing = _s(product.get("washing_instructions"))
    model_info = _s(product.get("model_info"))
    product_url = _s(product.get("product_url"))
    image_url = _s(product.get("image_url"))
    farfetch_id = _s(product.get("farfetch_id"))
    brand_style_id = _s(product.get("brand_style_id"))

    metadata: dict = {
        # ★ 映射回数据库的关键字段
        "product_id": int(product["id"]),
        # 与 CSV 版（utils.ATTRIBUTE_INFO / doc_to_product_item）一致的字段名
        "Product Name": name,
        "Brand": brand,
        "Label": label,
        "Description": description,
        "Price": price,
        "Currency": currency,
        "Original Price": original_price,
        "Discount Percentage": discount,
        "Available Sizes": available_sizes,
        "Composition Outer": comp_outer,
        "Composition Lining": comp_lining,
        "Washing Instructions": washing,
        "Model Info": model_info,
        "Product URL": product_url,
        "Image URL": image_url,
        "Farfetch ID": farfetch_id,
        "Brand Style ID": brand_style_id,
    }
    metadata.update(_build_size_metadata(size_tokens))

    # page_content：优先用数据库已存的；为空则按 CSV 版布局重建，保证检索文本质量
    page_content = _s(product.get("page_content"))
    if not page_content:
        page_content = "\n".join([
            f"Product Name: {name}",
            f"Brand: {brand}",
            f"Label: {label}",
            f"Description: {description}",
            f"Price: {price} {currency}".strip(),
            f"Original Price: {original_price}",
            f"Discount Percentage: {discount}",
            f"Available Sizes: {available_sizes}",
            f"Composition Outer: {comp_outer}",
            f"Composition Lining: {comp_lining}",
            f"Washing Instructions: {washing}",
            f"Model Info: {model_info}",
            f"Product URL: {product_url}",
            f"Image URL: {image_url}",
            f"Farfetch ID: {farfetch_id}",
            f"Brand Style ID: {brand_style_id}",
        ])

    return Document(page_content=page_content, metadata=metadata, id=str(product["id"]))


def rebuild_indexes_from_db_sync(products: list[dict]) -> int:
    """从 products 列表重建全部离线索引产物（同步，CPU/IO 密集，应在线程池调用）。"""
    if not products:
        return 0

    logger.info("[vector_index] Rebuilding indexes from %d products", len(products))
    documents = [_doc_from_product(p) for p in products]

    index_dir = Path(settings.INDEX_DIR)
    index_dir.mkdir(parents=True, exist_ok=True)

    embeddings = _get_embeddings()

    # 1. FAISS（同时保留内存对象，供 cross-encoder 组装复用）
    logger.info("[vector_index] Building FAISS index...")
    faiss_index = FAISS.from_documents(documents, embeddings)
    faiss_index.save_local(settings.FAISS_INDEX_PATH)
    logger.info("[vector_index] FAISS done (%d docs)", len(documents))

    # 2. BM25Retriever（pickle 对象，与 CSV 版一致）
    logger.info("[vector_index] Building BM25 retriever...")
    os.makedirs(os.path.dirname(settings.BM25_INDEX_PATH), exist_ok=True)
    bm25_retriever = BM25Retriever.from_documents(documents)
    with open(settings.BM25_INDEX_PATH, "wb") as f:
        pickle.dump(bm25_retriever, f)
    logger.info("[vector_index] BM25 done")

    # 3. ChromaDB（collection 名称必须与 self_query_node 一致）
    #    关键：不能 rmtree 删除目录——运行中的服务持有 chroma.sqlite3 句柄（chromadb
    #    共享客户端缓存），Windows 下会因文件占用导致 Rebuild 失败。改为「原地清空旧
    #    集合内容 + 重新写入」，复用同一底层客户端，既不报错也能让运行中的检索立即看到新数据。
    logger.info("[vector_index] Building Chroma index (in-place)...")
    chroma_path = Path(settings.CHROMA_INDEX_PATH)
    chroma_path.mkdir(parents=True, exist_ok=True)
    chroma = Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(chroma_path),
    )
    try:
        existing_ids = (chroma.get() or {}).get("ids") or []
        if existing_ids:
            chroma.delete(ids=existing_ids)
            logger.info("[vector_index] Cleared %d old Chroma docs", len(existing_ids))
    except Exception as e:  # noqa: BLE001
        logger.warning("[vector_index] clear existing chroma docs failed: %s", e)
    chroma.add_documents(documents)
    del chroma
    gc.collect()
    logger.info("[vector_index] Chroma done (%d docs)", len(documents))

    # 4. cross-encoder reranker（ranker_node 运行时加载的兜底召回器）
    logger.info("[vector_index] Building cross-encoder reranker...")
    faiss_retriever = faiss_index.as_retriever(
        search_type="similarity",
        search_kwargs={"k": settings.FAISS_TOP_K},
    )
    ensemble = EnsembleRetriever(
        retrievers=[faiss_retriever, bm25_retriever],
        weights=settings.RETRIEVER_WEIGHTS,
        top_k=settings.RETRIEVER_TOP_K,
    )
    cross_model = HuggingFaceCrossEncoder(model_name=settings.CROSS_ENCODER_MODEL_NAME)
    compressor = CrossEncoderReranker(model=cross_model, top_n=settings.COMPRESSOR_TOP_K)
    reranker = ContextualCompressionRetriever(
        base_compressor=compressor, base_retriever=ensemble
    )
    with open(settings.CROSS_ENCODER_RERANKER_PATH, "wb") as f:
        pickle.dump(reranker, f)
    logger.info("[vector_index] Cross-encoder reranker done")

    del faiss_index
    gc.collect()

    # 5. 清空推荐器进程内缓存，使新索引立即生效（无需重启服务）
    _reset_recommender_caches()

    logger.info("[vector_index] All indexes rebuilt (%d docs)", len(documents))
    return len(documents)


def _reset_recommender_caches() -> None:
    """重建后清空进程内缓存（Chroma / self-query / cross-encoder），让新索引立即生效。"""
    try:
        from src.recommender import self_query_node as sq
        sq._chroma_index = None
        sq._self_query_chain = None
        logger.info("[vector_index] self-query caches reset")
    except Exception as e:  # noqa: BLE001
        logger.warning("[vector_index] reset self-query caches failed: %s", e)
    try:
        from src.recommender import ranker_node as rk
        rk._cross_encoder_retriever = None
        logger.info("[vector_index] ranker cache reset")
    except Exception as e:  # noqa: BLE001
        logger.warning("[vector_index] reset ranker cache failed: %s", e)


async def rebuild_indexes_from_db(products: list[dict]) -> int:
    """异步包装：在线程池执行全量重建，避免阻塞事件循环。"""
    return await asyncio.to_thread(rebuild_indexes_from_db_sync, products)


def add_single_document_sync(product: dict) -> bool:
    """
    增量添加单个商品到 Chroma（新商品创建后调用，同步版）。

    FAISS / BM25 / cross-encoder 的增量更新成本高，仍建议低峰期全量重建；
    这里只做 Chroma 的增量 upsert，保证 self-query 能尽快检索到新品。
    """
    doc = _doc_from_product(product)
    try:
        chroma_path = Path(settings.CHROMA_INDEX_PATH)
        if chroma_path.exists():
            chroma = Chroma(
                collection_name=CHROMA_COLLECTION,
                embedding_function=_get_embeddings(),
                persist_directory=str(chroma_path),
            )
            chroma.add_documents([doc])
            del chroma
            gc.collect()
            logger.info("[vector_index] Chroma incremental add: product %s", product["id"])
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[vector_index] Chroma incremental add failed: %s", e)
    return False


async def add_single_document(product: dict) -> bool:
    """异步包装：在线程池执行 Chroma 增量写入。"""
    return await asyncio.to_thread(add_single_document_sync, product)
