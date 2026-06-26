"""
优惠券 API 路由。

GET   /coupons/available  — 可兑换的优惠券模板
POST  /coupons/redeem     — 使用金币兑换优惠券
GET   /coupons/my         — 我的优惠券列表
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from loguru import logger

from src.api.middleware.auth import get_current_user, get_optional_user
from src.database import execute, fetchall, fetchone, fetchval, insert_and_get_id

router = APIRouter(prefix="/coupons", tags=["Coupons"])


class RedeemRequest(BaseModel):
    coupon_template_id: int


async def _get_or_create_coin_account(user: dict | None, session_id: str | None) -> dict:
    """获取或创建金币账户。"""
    if user:
        account = await fetchone(
            "SELECT * FROM user_coins WHERE user_id = %s", (user["id"],)
        )
        if account:
            return account
        acct_id = await insert_and_get_id(
            "INSERT INTO user_coins (user_id, balance, total_earned, total_spent) "
            "VALUES (%s, 0, 0, 0)",
            (user["id"],),
        )
        return await fetchone("SELECT * FROM user_coins WHERE id = %s", (acct_id,))
    if session_id:
        account = await fetchone(
            "SELECT * FROM user_coins WHERE session_id = %s", (session_id,)
        )
        if account:
            return account
        acct_id = await insert_and_get_id(
            "INSERT INTO user_coins (session_id, balance, total_earned, total_spent) "
            "VALUES (%s, 0, 0, 0)",
            (session_id,),
        )
        return await fetchone("SELECT * FROM user_coins WHERE id = %s", (acct_id,))
    return {"id": 0, "balance": 0}


@router.get("/available")
async def get_available_coupons(
    user: dict | None = Depends(get_optional_user),
):
    """获取可兑换的优惠券模板列表。"""
    rows = await fetchall(
        "SELECT id, code, name, discount_type, discount_value, min_order_amount, "
        "max_discount_amount, per_user_limit, valid_from, valid_until "
        "FROM coupons WHERE is_active = 1 AND valid_until > NOW() "
        "ORDER BY min_order_amount ASC"
    )
    for r in rows:
        for f in ("valid_from", "valid_until"):
            if r.get(f):
                r[f] = str(r[f])
    return {"coupons": rows}


@router.post("/redeem")
async def redeem_coupon(
    body: RedeemRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """兑换优惠券（扣除金币）。"""
    # 验证优惠券模板存在
    template = await fetchone(
        "SELECT * FROM coupons WHERE id = %s AND is_active = 1 AND valid_until > NOW()",
        (body.coupon_template_id,),
    )
    if not template:
        raise HTTPException(status_code=404, detail="Coupon template not found or expired")

    user_id = user["id"] if user else None

    # 检查每人限领
    if template["per_user_limit"] > 0 and user_id:
        count = await fetchval(
            "SELECT COUNT(*) FROM user_coupons WHERE user_id = %s AND coupon_id = %s",
            (user_id, template["id"]),
        )
        if count >= template["per_user_limit"]:
            raise HTTPException(status_code=400, detail="You've reached the redemption limit for this coupon")

    # 获取金币账户并检查余额
    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    coin_acct = await _get_or_create_coin_account(user, session_id)

    # 根据优惠券价值计算金币消耗（简化：fixed 类型按 min_order_amount/10 算，percentage 按 max_discount 算）
    if template["discount_type"] == "fixed":
        cost = template["discount_value"]  # 1 coin = 1 yuan worth of discount
    else:
        cost = template.get("max_discount_amount") or 50

    cost = max(1, int(cost))  # 至少 1 金币

    if coin_acct["balance"] < cost:
        raise HTTPException(status_code=400, detail=f"Insufficient coins. Need {cost}, have {coin_acct['balance']}")

    # 扣除金币
    new_balance = coin_acct["balance"] - cost
    await execute(
        "UPDATE user_coins SET balance = %s, total_spent = total_spent + %s WHERE id = %s",
        (new_balance, cost, coin_acct["id"]),
    )
    await execute(
        "INSERT INTO coin_transactions (coin_account_id, amount, reason, reference_type, balance_after) "
        "VALUES (%s, %s, %s, %s, %s)",
        (coin_acct["id"], -cost, f"Redeem coupon: {template['name']}", "coupon", new_balance),
    )

    # 发放优惠券
    from datetime import datetime, timedelta
    uc_id = await insert_and_get_id(
        "INSERT INTO user_coupons (user_id, coupon_id, session_id, status, expires_at) "
        "VALUES (%s, %s, %s, 'available', %s)",
        (user_id, template["id"], session_id if not user_id else None,
         template["valid_until"]),
    )

    logger.info("[coupons] User %s redeemed coupon %s for %d coins", user_id or "anon", template["name"], cost)
    return {
        "message": f"Coupon '{template['name']}' redeemed for {cost} coins",
        "balance": new_balance,
        "user_coupon_id": uc_id,
    }


@router.get("/my")
async def get_my_coupons(
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """获取用户持有的优惠券。"""
    user_id = user["id"] if user else None
    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")

    if user_id:
        rows = await fetchall(
            "SELECT uc.id, uc.status, uc.acquired_at, uc.expires_at, "
            "c.name, c.code, c.discount_type, c.discount_value, "
            "c.min_order_amount, c.max_discount_amount "
            "FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id "
            "WHERE uc.user_id = %s AND uc.status = 'available' AND uc.expires_at > NOW() "
            "ORDER BY uc.expires_at ASC",
            (user_id,),
        )
    elif session_id:
        rows = await fetchall(
            "SELECT uc.id, uc.status, uc.acquired_at, uc.expires_at, "
            "c.name, c.code, c.discount_type, c.discount_value, "
            "c.min_order_amount, c.max_discount_amount "
            "FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id "
            "WHERE uc.session_id = %s AND uc.status = 'available' AND uc.expires_at > NOW() "
            "ORDER BY uc.expires_at ASC",
            (session_id,),
        )
    else:
        rows = []

    for r in rows:
        for f in ("acquired_at", "expires_at"):
            if r.get(f):
                r[f] = str(r[f])

    return {"coupons": rows}
