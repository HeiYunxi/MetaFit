"""
数据集本地校验模块。

检查 Farfetch 本地 CSV 数据文件是否存在，若缺失则给出明确指引。
数据来源：Farfetch.com 时尚商品数据（本地 CSV）。
"""

import os
import sys

from loguru import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings


def check_data_exists() -> bool:
    """检查本地数据文件是否存在。"""
    if os.path.exists(settings.RAW_DATA_PATH):
        logger.info(f"Dataset found at {settings.RAW_DATA_PATH}")
        return True
    logger.error(
        f"Dataset not found at {settings.RAW_DATA_PATH}. "
        "Please place FashionDataset.csv (Farfetch data) in backend/data/ before building indexes."
    )
    return False


if __name__ == "__main__":
    check_data_exists()
