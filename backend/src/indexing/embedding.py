"""
数据索引构建脚本。

负责把原始商品数据清洗成统一字段，并一次性产出推荐链路需要的
FAISS、BM25、Chroma 以及 cross-encoder fallback ranker。
"""

import json
import os
import pickle
import re
import sys
import warnings
from typing import Optional

import pandas as pd
from langchain.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_chroma import Chroma
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.document_loaders import CSVLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from loguru import logger

# Append project root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.config import settings

warnings.filterwarnings("ignore")

SUPPORTED_SIZE_ALIASES = {
    "xxxs": "Size XXXS",
    "3xs": "Size XXXS",
    "xxs": "Size XXS",
    "2xs": "Size XXS",
    "xs": "Size XS",
    "s": "Size S",
    "m": "Size M",
    "l": "Size L",
    "xl": "Size XL",
    "xxl": "Size XXL",
    "2xl": "Size XXL",
    "xxxl": "Size XXXL",
    "3xl": "Size XXXL",
    "one size": "Size One Size",
    "one-size": "Size One Size",
    "onesize": "Size One Size",
    "os": "Size One Size",
}

SUPPORTED_SIZE_FIELDS = list(dict.fromkeys(SUPPORTED_SIZE_ALIASES.values()))


def get_raw_data_path() -> str:
    """
    Resolve raw data path. Checks project root, then data/ directory.
    Data source: Farfetch.com local CSV (FashionDataset.csv).
    """
    # 1. Project root (e.g. ./FashionDataset.csv)
    root_path = settings.BASE_DIR / "FashionDataset.csv"
    if root_path.exists():
        logger.info(f"Using local dataset at {root_path}")
        return str(root_path)
    # 2. data/ directory
    if os.path.exists(settings.RAW_DATA_PATH):
        logger.info(f"Using dataset at {settings.RAW_DATA_PATH}")
        return settings.RAW_DATA_PATH
    # 3. Missing — raise clear error
    logger.error(
        f"Dataset not found. Please place FashionDataset.csv (Farfetch data) "
        f"in {settings.DATA_DIR} or project root before building indexes."
    )
    raise FileNotFoundError(
        f"FashionDataset.csv not found at {settings.RAW_DATA_PATH}. "
        "Place your Farfetch data CSV in backend/data/."
    )


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the new dataset columns into application-friendly labels."""
    rename_dict = {
        "product_url": "Product URL",
        "brand": "Brand",
        "product_name": "Product Name",
        "price": "Price",
        "currency": "Currency",
        "original_price": "Original Price",
        "discount_percentage": "Discount Percentage",
        "image_url": "Image URL",
        "sizes": "Available Sizes",
        "label": "Label",
        "description": "Description",
        "composition_outer": "Composition Outer",
        "composition_lining": "Composition Lining",
        "washing_instructions": "Washing Instructions",
        "model_info": "Model Info",
        "farfetch_id": "Farfetch ID",
        "brand_style_id": "Brand Style ID",
    }
    return df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns})


def load_and_preprocess_data(
    n_samples: Optional[int] = 2000,
    raw_path: Optional[str] = None,
) -> pd.DataFrame:
    """Load the dataset, normalize columns, and save a processed CSV."""
    path = raw_path or settings.RAW_DATA_PATH
    if not os.path.exists(path):
        logger.error(
            f"Dataset not found at {path}. Place FashionDataset.csv in project root or run data_loader.py."
        )
        raise FileNotFoundError(f"Dataset not found at {path}")

    df = pd.read_csv(path)
    logger.info(f"Loaded dataset with {len(df)} records.")

    df = clean_column_names(df)

    valid_columns = [
        "Product URL",
        "Brand",
        "Product Name",
        "Price",
        "Currency",
        "Original Price",
        "Discount Percentage",
        "Image URL",
        "Available Sizes",
        "Label",
        "Description",
        "Composition Outer",
        "Composition Lining",
        "Washing Instructions",
        "Model Info",
        "Farfetch ID",
        "Brand Style ID",
    ]
    df = df[[col for col in valid_columns if col in df.columns]]

    required_text_columns = [
        "Product Name",
        "Brand",
        "Description",
        "Image URL",
        "Available Sizes",
        "Label",
    ]
    for col in required_text_columns:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
            df = df[df[col] != ""]

    if "Price" in df.columns:
        df = df[df["Price"].notna()]

    optional_text_columns = [
        "Product URL",
        "Currency",
        "Composition Outer",
        "Composition Lining",
        "Washing Instructions",
        "Model Info",
        "Farfetch ID",
        "Brand Style ID",
    ]
    for col in optional_text_columns:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    optional_numeric_columns = ["Original Price", "Discount Percentage"]
    for col in optional_numeric_columns:
        if col in df.columns:
            df[col] = df[col].fillna("")

    if n_samples and n_samples < len(df):
        df = df.sample(n_samples, random_state=42)

    # Save processed data
    df.to_csv(settings.PROCESSED_DATA_PATH, index=False)
    logger.info(f"Processed dataset saved to {settings.PROCESSED_DATA_PATH}")

    return df


def generate_documents(use_csv_loader: bool = False) -> list:
    """Converts CSV data into LangChain Document objects."""
    if use_csv_loader:
        try:
            loader = CSVLoader(settings.PROCESSED_DATA_PATH, encoding="utf-8")
            documents = loader.load()
            logger.info(f"Generated {len(documents)} documents.")
            return documents
        except Exception as e:
            logger.exception("Failed to generate documents.")
            raise e

    def convert_price(value):
        try:
            cleaned_value = str(value).replace(",", "").replace("%", "").strip()
            if cleaned_value == "" or cleaned_value.lower() == "nan":
                return 0.0
            return float(cleaned_value)
        except ValueError:
            return 0.0

    def normalize_size_token(value: str) -> str:
        """Normalize a raw size token into a canonical lookup key."""
        normalized_value = value.strip().lower()
        normalized_value = normalized_value.replace("size:", "").strip()
        normalized_value = normalized_value.replace("-", " ")
        normalized_value = re.sub(r"\s+", " ", normalized_value)
        return normalized_value

    def extract_size_tokens(value) -> list[str]:
        """Extract normalized size tokens from a raw size field."""
        if pd.isna(value) or not isinstance(value, str):
            return []

        raw_tokens = re.split(r"[,/|]", value)
        normalized_tokens = []
        for token in raw_tokens:
            normalized_token = normalize_size_token(token)
            if normalized_token:
                normalized_tokens.append(normalized_token)
        return normalized_tokens

    def convert_sizes(value):
        """Normalize sizes into a lowercase comma-separated string."""
        size_tokens = extract_size_tokens(value)
        return ", ".join(size_tokens)

    def build_size_metadata(value) -> dict[str, bool]:
        """
        为每个标准尺码展开布尔字段。

        这样 self-query 阶段就能直接过滤 `Size M == true`，
        而不需要在字符串 `"XS,S,M"` 上做不稳定的模糊匹配。
        """
        size_tokens = extract_size_tokens(value)
        size_labels = {
            SUPPORTED_SIZE_ALIASES[token]
            for token in size_tokens
            if token in SUPPORTED_SIZE_ALIASES
        }
        return {size_field: size_field in size_labels for size_field in SUPPORTED_SIZE_FIELDS}

    df = pd.read_csv(settings.PROCESSED_DATA_PATH)

    if "Available Sizes" in df.columns:
        df["Available Sizes"] = df["Available Sizes"].apply(convert_sizes)

    numeric_columns = ["Price", "Original Price", "Discount Percentage"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].apply(convert_price)

    # page_content 主要服务 RAG 展示，metadata 主要服务过滤和结构化响应。
    documents = []
    for _, row in df.iterrows():
        metadata = row.to_dict()
        metadata.update(build_size_metadata(metadata.get("Available Sizes", "")))

        documents.append(
            Document(
                page_content="\n".join(
                    [
                        f"Product Name: {metadata.get('Product Name', '')}",
                        f"Brand: {metadata.get('Brand', '')}",
                        f"Label: {metadata.get('Label', '')}",
                        f"Description: {metadata.get('Description', '')}",
                        f"Price: {metadata.get('Price', 0.0)} {metadata.get('Currency', '')}".strip(),
                        f"Original Price: {metadata.get('Original Price', 0.0)}",
                        f"Discount Percentage: {metadata.get('Discount Percentage', 0.0)}",
                        f"Available Sizes: {metadata.get('Available Sizes', '')}",
                        f"Composition Outer: {metadata.get('Composition Outer', '')}",
                        f"Composition Lining: {metadata.get('Composition Lining', '')}",
                        f"Washing Instructions: {metadata.get('Washing Instructions', '')}",
                        f"Model Info: {metadata.get('Model Info', '')}",
                        f"Product URL: {metadata.get('Product URL', '')}",
                        f"Image URL: {metadata.get('Image URL', '')}",
                        f"Farfetch ID: {metadata.get('Farfetch ID', '')}",
                        f"Brand Style ID: {metadata.get('Brand Style ID', '')}",
                    ]
                ),
                metadata=metadata,
                id=str(row.name),
            )
        )
    logger.info(f"Generated {len(documents)} documents.")
    return documents


def initialize_embeddings_model() -> HuggingFaceEmbeddings:
    """Initializes the HuggingFace embeddings model."""
    try:
        model_name = settings.EMBEDDINGS_MODEL_NAME
        embeddings = HuggingFaceEmbeddings(model_name=model_name)
        logger.info(f"Successfully initialized embeddings model: {model_name}")
        return embeddings
    except Exception as e:
        logger.exception("Failed to initialize embeddings model.")
        raise e


def create_faiss_index(embeddings: HuggingFaceEmbeddings, documents: list) -> FAISS:
    """创建并保存 FAISS 索引，同时返回内存中的索引对象。"""
    try:
        logger.info("Creating FAISS index...")
        faiss_index = FAISS.from_documents(documents, embeddings)
        faiss_index.save_local(settings.FAISS_INDEX_PATH)
        logger.info(f"FAISS index saved at {settings.FAISS_INDEX_PATH}")
        return faiss_index
    except Exception as e:
        logger.exception("Failed to create FAISS index.")
        raise e


def create_chroma_index(embeddings: HuggingFaceEmbeddings, documents: list) -> None:
    """Creates and saves a Chroma index."""
    try:
        logger.info("Creating Chroma index...")
        vector_store = Chroma(
            collection_name="product_collection",
            embedding_function=embeddings,
            persist_directory=settings.CHROMA_INDEX_PATH,
        )
        vector_store.add_documents(documents)
        logger.info(f"Chroma index saved at {settings.CHROMA_INDEX_PATH}")
        logger.info(f"Number of documents in Chroma index: {len(documents)}")
    except Exception as e:
        logger.exception("Failed to create Chroma index.")
        raise e


def create_bm25_index(documents: list) -> BM25Retriever:
    """创建并保存 BM25 索引，同时返回内存中的检索器对象。"""
    try:
        os.makedirs(os.path.dirname(settings.BM25_INDEX_PATH), exist_ok=True)

        logger.info("Creating BM25 index...")
        bm25_index = BM25Retriever.from_documents(documents)

        with open(settings.BM25_INDEX_PATH, "wb") as f:
            pickle.dump(bm25_index, f)

        logger.info(f"BM25 index saved at {settings.BM25_INDEX_PATH}")
        return bm25_index
    except Exception as e:
        logger.exception("Failed to create BM25 index.")
        raise e


def create_cross_encoder_reranker(
    faiss_index: FAISS,
    bm25_index: BM25Retriever,
) -> ContextualCompressionRetriever:
    """
    构建 fallback ranker。

    这条链路只在 self-query 没有召回结果时使用，因此在离线索引阶段
    直接产出 pickle，运行时只需要加载即可。
    """
    logger.info("Creating cross encoder reranker...")

    faiss_retriever = faiss_index.as_retriever(
        search_type="similarity",
        search_kwargs={"k": settings.FAISS_TOP_K},
    )
    ensemble_retriever = EnsembleRetriever(
        retrievers=[faiss_retriever, bm25_index],
        weights=settings.RETRIEVER_WEIGHTS,
        top_k=settings.RETRIEVER_TOP_K,
    )

    model = HuggingFaceCrossEncoder(model_name=settings.CROSS_ENCODER_MODEL_NAME)
    compressor = CrossEncoderReranker(model=model, top_n=settings.COMPRESSOR_TOP_K)
    reranker = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=ensemble_retriever,
    )

    with open(settings.CROSS_ENCODER_RERANKER_PATH, "wb") as f:
        pickle.dump(reranker, f)
    logger.info(f"Cross encoder reranker saved at {settings.CROSS_ENCODER_RERANKER_PATH}")
    return reranker


def embedding_pipeline(n_samples: Optional[int] = None) -> None:
    """运行完整索引流程，产出在线推荐需要的全部离线资产。"""
    try:
        raw_path = get_raw_data_path()
        df = load_and_preprocess_data(n_samples, raw_path=raw_path)
        documents = generate_documents()
        embeddings = initialize_embeddings_model()

        faiss_index = create_faiss_index(embeddings, documents)
        bm25_index = create_bm25_index(documents)
        create_chroma_index(embeddings, documents)
        create_cross_encoder_reranker(faiss_index, bm25_index)

        logger.info("Embedding pipeline completed successfully.")
    except Exception as e:
        logger.exception("Failed to run embedding pipeline.")
        raise e


if __name__ == "__main__":
    embedding_pipeline()
