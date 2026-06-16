"""
首页热点商品接口。

职责：
- 从离线已处理的数据集（processed_data.csv）挑出前 N 个有图商品，作为首页“热点”展示。
- 输出字段结构与 /recommend 完全一致（复用 normalize_products），
  这样前端 render_products 无需任何改动即可消费。

热点规则（与产品确认）：固定取数据集前 N 个有图（image_url 非空）的商品，
顺序稳定、可复现，不依赖销量/热度字段（数据集没有该字段）。

数据只读，不触碰推荐链路 / 索引 / 试穿 / 图生 3D。
"""

import pandas as pd
from fastapi import APIRouter, Query
from loguru import logger

from src.api.routers.recommender import normalize_products
from src.config import settings

router = APIRouter(prefix="/trending", tags=["Trending"])

# CSV 列名 → 应用层 snake_case 字段名。
# 与 src/indexing/embedding.py 的列名约定保持一致；在此本地定义一份，
# 避免引入对 indexing 模块（含重型依赖）的运行时依赖。
_COLUMN_TO_FIELD = {
    "Product URL": "product_url",
    "Brand": "brand",
    "Product Name": "product_name",
    "Price": "price",
    "Currency": "currency",
    "Original Price": "original_price",
    "Discount Percentage": "discount_percentage",
    "Image URL": "image_url",
    "Available Sizes": "available_sizes",
    "Label": "label",
    "Description": "description",
    "Composition Outer": "composition_outer",
    "Composition Lining": "composition_lining",
    "Washing Instructions": "washing_instructions",
    "Model Info": "model_info",
    "Farfetch ID": "farfetch_id",
    "Brand Style ID": "brand_style_id",
}

# 模块级缓存：首次请求时读盘并 normalize，后续请求直接复用。
_trending_cache: list[dict] | None = None


def _load_trending_items() -> list[dict]:
    """
    读取 processed_data.csv，过滤出有图商品，统一成与 /recommend 一致的结构。

    结果缓存在模块级变量中，避免每次请求都读盘。
    数据集缺失时返回空列表（不抛 5xx），与 download 路由的空目录处理风格一致。
    """
    global _trending_cache
    if _trending_cache is not None:
        return _trending_cache

    try:
        df = pd.read_csv(settings.PROCESSED_DATA_PATH)
    except FileNotFoundError:
        logger.warning(
            f"[trending] processed data not found at {settings.PROCESSED_DATA_PATH}; "
            "returning empty trending list."
        )
        _trending_cache = []
        return _trending_cache
    except Exception as e:  # 读取异常也降级为空列表，保证接口不 5xx
        logger.error(f"[trending] failed to load processed data: {e}")
        _trending_cache = []
        return _trending_cache

    # 把 NaN 统一成 None，再按列名映射成 snake_case 字段。
    df = df.where(pd.notnull(df), None)
    rename_map = {col: _COLUMN_TO_FIELD[col] for col in df.columns if col in _COLUMN_TO_FIELD}
    df = df.rename(columns=rename_map)

    raw_items = df.to_dict(orient="records")

    # 只保留有图商品（image_url 非空）：首页卡片必须能渲染图片。
    with_image = [
        item for item in raw_items
        if (item.get("image_url") or "").strip()
    ]

    # 复用推荐链路同款字段规范化，保证结构完全一致。
    _trending_cache = normalize_products(with_image)
    logger.info(f"[trending] loaded {len(_trending_cache)} items with image.")
    return _trending_cache


@router.get("/", response_model=dict)
def get_trending(limit: int = Query(default=8, ge=1, le=50)):
    """
    返回首页热点商品。

    Args:
        limit: 返回条数，默认 8，范围 [1, 50]。

    Returns:
        {"count": <实际返回条数>, "products": [<与 /recommend 同结构的商品>...]}
    """
    items = _load_trending_items()
    selected = items[:limit]
    return {"count": len(selected), "products": selected}
