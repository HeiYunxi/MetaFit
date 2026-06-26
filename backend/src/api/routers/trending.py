"""
首页热点商品接口。

从 MySQL products 表挑选有图的活跃商品作为"热点"展示，
输出结构与 /products 列表一致（含 id），方便前端复用卡片与加入购物车。
"""

from fastapi import APIRouter, Query

from src.database import fetchall

router = APIRouter(prefix="/trending", tags=["Trending"])


@router.get("/", response_model=dict)
async def get_trending(limit: int = Query(default=8, ge=1, le=50)):
    """返回首页热点商品（按最新创建，取有图的活跃商品）。"""
    rows = await fetchall(
        "SELECT id, product_name, brand, label, price, currency, original_price, "
        "discount_percentage, image_url FROM products "
        "WHERE is_active = 1 AND image_url <> '' "
        "ORDER BY created_at DESC LIMIT %s",
        (limit,),
    )
    for r in rows:
        for k in ("price", "original_price", "discount_percentage"):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return {"count": len(rows), "products": rows}
