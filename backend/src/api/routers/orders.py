"""
订单 API 路由。

POST /orders              — 创建订单（购物车结算）
GET  /orders/{id}         — 订单详情
POST /orders/{id}/cancel  — 取消订单
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from src.api.middleware.auth import get_current_user, get_optional_user
from src.database import execute, fetchall, fetchone, fetchval, insert_and_get_id

router = APIRouter(prefix="/orders", tags=["Orders"])


class CreateOrderRequest(BaseModel):
    session_id: str
    used_coupon_id: int | None = None


@router.post("")
async def create_order(
    body: CreateOrderRequest,
    user: dict | None = Depends(get_optional_user),
):
    """从购物车创建订单。"""
    user_id = user["id"] if user else None

    # 获取购物车
    cart_items = await fetchall(
        "SELECT ci.id AS cart_item_id, ci.product_id, ci.selected_size, ci.quantity, "
        "p.product_name, p.brand, p.price, p.currency "
        "FROM cart_items ci JOIN products p ON ci.product_id = p.id "
        "WHERE ci.session_id = %s",
        (body.session_id,),
    )
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # 计算总金额
    total = sum(item["price"] * item["quantity"] for item in cart_items)
    discount = 0.0

    # 优惠券抵扣
    if body.used_coupon_id:
        # 查找用户优惠券
        uc = await fetchone(
            "SELECT uc.*, c.discount_type, c.discount_value, c.min_order_amount, "
            "c.max_discount_amount "
            "FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id "
            "WHERE uc.id = %s AND (uc.user_id = %s OR uc.session_id = %s) "
            "AND uc.status = 'available' AND uc.expires_at > NOW()",
            (body.used_coupon_id, user_id, body.session_id),
        )
        if not uc:
            raise HTTPException(status_code=400, detail="Invalid or expired coupon")

        if total < uc["min_order_amount"]:
            raise HTTPException(
                status_code=400,
                detail=f"Order total {total:.2f} below minimum {uc['min_order_amount']:.2f}",
            )

        if uc["discount_type"] == "fixed":
            discount = uc["discount_value"]
        else:
            discount = total * (1 - uc["discount_value"])
            if uc["max_discount_amount"]:
                discount = min(discount, uc["max_discount_amount"])

        # 标记优惠券已使用
        await execute(
            "UPDATE user_coupons SET status = 'used', used_at = NOW() WHERE id = %s",
            (body.used_coupon_id,),
        )

    final = max(0, total - discount)

    # 创建订单
    order_no = f"MF{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:4].upper()}"
    order_id = await insert_and_get_id(
        "INSERT INTO orders (order_no, user_id, session_id, used_coupon_id, "
        "total_amount, discount_amount, final_amount, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')",
        (order_no, user_id, body.session_id, body.used_coupon_id,
         total, discount, final),
    )

    # 创建订单明细
    for item in cart_items:
        await execute(
            "INSERT INTO order_items (order_id, product_id, product_name_snap, "
            "price_snap, selected_size, quantity) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (order_id, item["product_id"], item["product_name"],
             item["price"], item["selected_size"], item["quantity"]),
        )

    # 清空购物车
    await execute("DELETE FROM cart_items WHERE session_id = %s", (body.session_id,))

    logger.info("[orders] Order %s created: total=%.2f, discount=%.2f, final=%.2f",
                order_no, total, discount, final)

    return {
        "order_id": order_id,
        "order_no": order_no,
        "total_amount": total,
        "discount_amount": discount,
        "final_amount": final,
        "status": "pending",
        "item_count": len(cart_items),
    }


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    user: dict | None = Depends(get_optional_user),
):
    """获取订单详情。"""
    user_id = user["id"] if user else None
    order = await fetchone(
        "SELECT * FROM orders WHERE id = %s AND (user_id = %s OR user_id IS NULL)",
        (order_id, user_id),
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for f in ("created_at", "paid_at", "updated_at"):
        if order.get(f):
            order[f] = str(order[f])

    items = await fetchall(
        "SELECT * FROM order_items WHERE order_id = %s",
        (order_id,),
    )

    return {"order": order, "items": items}


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    user: dict | None = Depends(get_optional_user),
):
    """取消订单（仅 pending 状态可取消）。"""
    user_id = user["id"] if user else None
    order = await fetchone(
        "SELECT * FROM orders WHERE id = %s AND (user_id = %s OR user_id IS NULL)",
        (order_id, user_id),
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending orders can be cancelled")

    await execute(
        "UPDATE orders SET status = 'cancelled', updated_at = NOW() WHERE id = %s",
        (order_id,),
    )

    # 返还优惠券
    if order["used_coupon_id"]:
        await execute(
            "UPDATE user_coupons SET status = 'available', used_at = NULL, "
            "used_order_id = NULL WHERE id = %s",
            (order["used_coupon_id"],),
        )

    return {"message": "Order cancelled", "order_id": order_id}
