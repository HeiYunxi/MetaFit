"""
面向消费者的公开商品目录接口（Grid 商品列表 / 详情 / 浏览历史记录）。

GET  /products             — 商品列表（搜索 q + 分类 category + 品牌 brand + 排序 + 分页）
GET  /products/categories  — 分类列表（含数量，用于筛选）
GET  /products/{id}        — 商品详情（含尺码 + 同类推荐）
POST /products/{id}/view   — 记录浏览历史（匿名/登录均可）
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger

from src.api.middleware.auth import get_optional_user
from src.database import execute, fetchall, fetchone, fetchval

router = APIRouter(prefix="/products", tags=["Catalog"])

_SORTS = {
    "newest": "created_at DESC",
    "price_asc": "price ASC",
    "price_desc": "price DESC",
    "name": "product_name ASC",
}


def _clean(p: dict) -> dict:
    """统一序列化：Decimal→float，datetime→str。"""
    for k in ("price", "original_price", "discount_percentage"):
        if p.get(k) is not None:
            p[k] = float(p[k])
    for k in ("created_at", "updated_at"):
        if p.get(k) is not None:
            p[k] = str(p[k])
    return p


@router.get("")
async def list_products(
    q: str = Query(default="", description="搜索关键词"),
    category: str = Query(default="", description="品类 label"),
    brand: str = Query(default=""),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
):
    """商品列表（仅返回 is_active=1 且有图的商品）。"""
    conditions = ["is_active = 1", "image_url <> ''"]
    args: list = []

    if q:
        conditions.append("(product_name LIKE %s OR brand LIKE %s OR description LIKE %s)")
        like = f"%{q}%"
        args.extend([like, like, like])
    if category:
        conditions.append("label = %s")
        args.append(category)
    if brand:
        conditions.append("brand = %s")
        args.append(brand)

    where = " AND ".join(conditions)
    order = _SORTS.get(sort, _SORTS["newest"])
    offset = (page - 1) * page_size

    total = await fetchval(f"SELECT COUNT(*) FROM products WHERE {where}", tuple(args))
    rows = await fetchall(
        f"SELECT id, product_name, brand, label, price, currency, original_price, "
        f"discount_percentage, image_url FROM products WHERE {where} "
        f"ORDER BY {order} LIMIT %s OFFSET %s",
        tuple(args + [page_size, offset]),
    )
    items = [_clean(r) for r in rows]
    return {
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/categories")
async def list_categories():
    """返回有商品的分类及其数量。"""
    rows = await fetchall(
        "SELECT label AS name, COUNT(*) AS count FROM products "
        "WHERE is_active = 1 AND label <> '' GROUP BY label ORDER BY count DESC"
    )
    return {"categories": rows}


@router.get("/{product_id}")
async def get_product(product_id: int):
    """商品详情（含尺码与同类推荐）。"""
    product = await fetchone(
        "SELECT id, product_name, brand, label, description, price, currency, "
        "original_price, discount_percentage, image_url, product_url, "
        "composition_outer, composition_lining, washing_instructions, model_info, "
        "created_at FROM products WHERE id = %s AND is_active = 1",
        (product_id,),
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    _clean(product)

    sizes = await fetchall(
        "SELECT size_label, size_category, stock_status FROM product_sizes "
        "WHERE product_id = %s ORDER BY id ASC",
        (product_id,),
    )

    similar = await fetchall(
        "SELECT id, product_name, brand, price, currency, image_url FROM products "
        "WHERE is_active = 1 AND image_url <> '' AND label = %s AND id <> %s "
        "ORDER BY RAND() LIMIT 6",
        (product["label"], product_id),
    )
    similar = [_clean(s) for s in similar]

    return {"product": product, "sizes": sizes, "similar": similar}


async def _ensure_session(request: Request, user: dict | None) -> str:
    """确保存在一个 sessions 记录（满足 browse_history 外键）。"""
    sid = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    if sid:
        exists = await fetchval("SELECT id FROM sessions WHERE id = %s", (sid,))
        if exists:
            if user:
                await execute(
                    "UPDATE sessions SET user_id = %s WHERE id = %s AND user_id IS NULL",
                    (user["id"], sid),
                )
            return sid
    sid = sid or str(uuid4())
    await execute(
        "INSERT INTO sessions (id, user_id, is_active) VALUES (%s, %s, 1) "
        "ON DUPLICATE KEY UPDATE last_activity_at = CURRENT_TIMESTAMP",
        (sid, user["id"] if user else None),
    )
    return sid


@router.post("/{product_id}/view")
async def record_view(
    product_id: int,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """记录一次商品浏览（去重，最近浏览刷新到顶部）。"""
    exists = await fetchval(
        "SELECT id FROM products WHERE id = %s AND is_active = 1", (product_id,)
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Product not found")

    session_id = await _ensure_session(request, user)
    await execute(
        "INSERT INTO browse_history (session_id, user_id, product_id) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE viewed_at = CURRENT_TIMESTAMP, "
        "user_id = COALESCE(VALUES(user_id), user_id)",
        (session_id, user["id"] if user else None, product_id),
    )
    return {"ok": True}
