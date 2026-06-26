"""
购物车 API 路由（替代 localStorage）。

GET    /cart          — 获取购物车
POST   /cart          — 添加商品到购物车
DELETE /cart/{id}     — 移除购物车条目
DELETE /cart          — 清空购物车
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from loguru import logger

from src.api.middleware.auth import get_current_user, get_optional_user
from src.database import execute, fetchall, fetchval

router = APIRouter(prefix="/cart", tags=["Cart"])


class CartAddRequest(BaseModel):
    product_id: int
    selected_size: str | None = None
    quantity: int = 1


def _get_session_id(request: Request, user: dict | None) -> str | None:
    """从 cookie 或 header 获取会话 ID。"""
    # 尝试从 cookie 获取
    thread_id = request.cookies.get("thread_id")
    if thread_id:
        return thread_id
    # 尝试从 header
    x_session = request.headers.get("X-Session-Id")
    return x_session


async def _ensure_session(request: Request, user: dict | None) -> str:
    """
    确保有一个有效的 session_id：
    - 登录用户：查询或创建关联 session
    - 匿名用户：使用 cookie thread_id 或新建

    简化实现：匿名用 cookie thread_id，登录用户创建/复用 session。
    """
    from uuid import uuid4
    from src.database import insert_and_get_id

    session_id = _get_session_id(request, user)

    if user:
        # 登录用户：查找已有 session
        if session_id:
            # 把这个 session 关联到 user
            await execute(
                "UPDATE sessions SET user_id = %s WHERE id = %s AND user_id IS NULL",
                (user["id"], session_id),
            )
            return session_id

        # 查找用户是否有已有 session
        existing = await fetchval(
            "SELECT id FROM sessions WHERE user_id = %s AND is_active = 1 ORDER BY last_activity_at DESC LIMIT 1",
            (user["id"],),
        )
        if existing:
            return existing

        # 新建
        sid = str(uuid4())
        await execute(
            "INSERT INTO sessions (id, user_id, is_active) VALUES (%s, %s, 1)",
            (sid, user["id"]),
        )
        return sid

    # 匿名用户
    if not session_id:
        session_id = str(uuid4())
        await execute(
            "INSERT INTO sessions (id, is_active) VALUES (%s, 1)",
            (session_id,),
        )
    return session_id


@router.get("")
async def get_cart(request: Request, user: dict | None = Depends(get_optional_user)):
    """获取当前购物车内容。"""
    session_id = _get_session_id(request, user)
    if not session_id:
        return {"items": [], "count": 0}

    items = await fetchall(
        "SELECT ci.id, ci.product_id, ci.selected_size, ci.quantity, ci.added_at, "
        "p.product_name, p.brand, p.label, p.price, p.currency, p.image_url "
        "FROM cart_items ci "
        "JOIN products p ON ci.product_id = p.id "
        "WHERE ci.session_id = %s "
        "ORDER BY ci.added_at DESC",
        (session_id,),
    )
    for item in items:
        if item.get("added_at"):
            item["added_at"] = str(item["added_at"])

    return {"items": items, "count": len(items)}


@router.post("")
async def add_to_cart(
    body: CartAddRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """添加商品到购物车（自动去重）。"""
    session_id = await _ensure_session(request, user)

    # 检查商品是否存在且活跃
    product = await fetchval(
        "SELECT id FROM products WHERE id = %s AND is_active = 1",
        (body.product_id,),
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 去重：同一 session + 同一 product
    existing = await fetchval(
        "SELECT id FROM cart_items WHERE session_id = %s AND product_id = %s",
        (session_id, body.product_id),
    )
    if existing:
        await execute(
            "UPDATE cart_items SET quantity = quantity + %s WHERE id = %s",
            (body.quantity, existing),
        )
        return {"message": "Quantity updated", "cart_item_id": existing}

    from src.database import insert_and_get_id
    item_id = await insert_and_get_id(
        "INSERT INTO cart_items (session_id, product_id, selected_size, quantity) "
        "VALUES (%s, %s, %s, %s)",
        (session_id, body.product_id, body.selected_size, body.quantity),
    )
    return {"message": "Added to cart", "cart_item_id": item_id}


@router.delete("/{item_id}")
async def remove_from_cart(
    item_id: int,
    user: dict | None = Depends(get_optional_user),
):
    """移除购物车中的指定商品。"""
    await execute("DELETE FROM cart_items WHERE id = %s", (item_id,))
    return {"message": "Removed from cart"}


@router.delete("")
async def clear_cart(
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """清空购物车。"""
    session_id = _get_session_id(request, user)
    if session_id:
        await execute("DELETE FROM cart_items WHERE session_id = %s", (session_id,))
    return {"message": "Cart cleared"}
