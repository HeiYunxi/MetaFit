"""
项目全局配置。

通过 pydantic-settings 从 .env 文件读取，未配置时使用默认值。
所有路径在启动时自动创建（data/、indexes/、logs/、download/）。

快速上手：复制 .env.example 为 .env 并填写以下关键 Key：
  LAOZHANG_GPT_API_KEY   — 用于推荐对话、topic 判断、query 改写
  LAOZHANG_IMAGE_API_KEY — 用于虚拟试穿（图生图）
  TRIPO_API_KEY          — 用于图生 3D
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """项目运行时配置，字段对应 .env 同名变量（大写）。"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="allow",
    )

    # ── 路径（backend/ 为后端根目录，.env 在项目根目录） ───────────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    INDEX_DIR: Path = DATA_DIR / "indexes"

    # ── 数据集（Farfetch.com 本地 CSV） ──────────────────────────────────────
    RAW_DATA_PATH: str = str(DATA_DIR / "FashionDataset.csv")
    PROCESSED_DATA_PATH: str = str(DATA_DIR / "processed_data.csv")

    # ── 向量嵌入模型（本地运行，无需 API Key） ─────────────────────────────────
    EMBEDDINGS_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Fallback ranker 使用的 cross-encoder 重排序模型
    CROSS_ENCODER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── LLM（legacy，推荐链路实际使用 LAOZHANG_GPT_MODEL） ────────────────────
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0
    LLM_MAX_TOKENS: int = 500

    # ── 离线索引路径 ───────────────────────────────────────────────────────────
    FAISS_INDEX_PATH: str = str(INDEX_DIR / "faiss_index.faiss")
    BM25_INDEX_PATH: str = str(INDEX_DIR / "bm25_index.pkl")
    CROSS_ENCODER_RERANKER_PATH: str = str(INDEX_DIR / "cross_encoder_reranker.pkl")
    CHROMA_INDEX_PATH: str = str(INDEX_DIR / "chroma_index")

    # ── 检索超参数 ─────────────────────────────────────────────────────────────
    FAISS_TOP_K: int = 3           # FAISS 向量检索返回条数
    BM25_TOP_K: int = 3            # BM25 关键词检索返回条数
    RETRIEVER_TOP_K: int = 5       # 集成检索器最终返回条数
    RETRIEVER_WEIGHTS: list[float] = [0.5, 0.5]  # FAISS : BM25 权重比
    COMPRESSOR_TOP_K: int = 2      # cross-encoder 重排后保留条数

    # ── 老张 GPT API（推荐对话 / topic 判断 / query 改写） ────────────────────
    OPENAI_API_KEY: SecretStr | None = None  # 标准 OpenAI Key（通常不用配置）
    LAOZHANG_GPT_API_KEY: SecretStr = SecretStr(
        os.environ.get("LAOZHANG_GPT_API_KEY", "")
    )
    LAOZHANG_GPT_BASE_URL: str = os.environ.get(
        "LAOZHANG_GPT_BASE_URL", "https://api.laozhang.ai/v1"
    )
    LAOZHANG_GPT_MODEL: str = os.environ.get("LAOZHANG_GPT_MODEL", "gpt-4o")

    # ── 老张 图像 API（虚拟试穿，cstImg 模块） ────────────────────────────────
    # 若未单独配置图像 Key，则复用 GPT Key（两者通常相同）
    LAOZHANG_IMAGE_API_KEY: SecretStr = SecretStr(
        os.environ.get("LAOZHANG_IMAGE_API_KEY", "")
        or os.environ.get("LAOZHANG_GPT_API_KEY", "")
    )
    LAOZHANG_IMAGE_BASE_URL: str = os.environ.get(
        "LAOZHANG_IMAGE_BASE_URL", "https://api.laozhang.ai/v1"
    )
    LAOZHANG_IMAGE_MODEL: str = os.environ.get(
        "LAOZHANG_IMAGE_MODEL", "gemini-2.5-flash-image"
    )

    # ── Tripo3D（图生 3D，img2model 模块） ────────────────────────────────────
    FAL_KEY: SecretStr = SecretStr(os.environ.get("FAL_KEY", ""))  # 暂未使用
    TRIPO_API_KEY: SecretStr = SecretStr(os.environ.get("TRIPO_API_KEY", ""))
    # 生成的 GLB 文件保存目录，供 /download/{filename} 接口提供下载
    DOWNLOAD_DIR: str = str(BASE_DIR / "download")

    # ── 日志 ──────────────────────────────────────────────────────────────────
    LOGGING_LEVEL: str = "INFO"
    LOGGING_FILE: str = str(BASE_DIR / "logs" / "preprocessing.log")

    # ── 预热：确保关键目录在程序启动时就存在 ─────────────────────────────────
    # （data_loader / embedding 等脚本也会自己 makedirs，这里只是兜底）
    GUARDRAIL_SETTINGS_DIR: str = str(BASE_DIR / "src" / "core" / "guardrail")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.INDEX_DIR, exist_ok=True)
        os.makedirs(self.BASE_DIR / "logs", exist_ok=True)
        os.makedirs(self.BASE_DIR / "download", exist_ok=True)


settings = Settings()
