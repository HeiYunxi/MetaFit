"""
金币 API 路由（替代 localStorage coins）。

GET   /coins              — 获取当前余额
POST  /coins/earn         — 赚取金币（签到/看广告等）
POST  /coins/spend        — 消费金币（Redeem 优惠券等）
POST  /coins/checkin      — 每日签到
GET   /coins/transactions — 流水记录
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from loguru import logger

from src.api.middleware.auth import get_current_user, get_optional_user
from src.database import execute, fetchall, fetchone, fetchval, insert_and_get_id

router = APIRouter(prefix="/coins", tags=["Coins"])

DAILY_REWARD = 10


class EarnRequest(BaseModel):
    amount: int
    reason: str
    reference_type: str | None = None
    reference_id: int | None = None


class SpendRequest(BaseModel):
    amount: int
    reason: str
    reference_type: str | None = None
    reference_id: int | None = None


async def _get_or_create_account(user: dict | None, session_id: str | None) -> dict:
    """获取或创建金币账户（优先 user_id，其次 session_id）。"""
    if user:
        account = await fetchone(
            "SELECT * FROM user_coins WHERE user_id = %s", (user["id"],)
        )
        if account:
            return account
        # 创建
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

    return {"id": 0, "balance": 0, "total_earned": 0, "total_spent": 0}


@router.get("")
async def get_balance(
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """获取当前用户金币余额。"""
    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    account = await _get_or_create_account(user, session_id)
    return {
        "balance": account["balance"],
        "total_earned": account["total_earned"],
        "total_spent": account["total_spent"],
    }


@router.post("/earn")
async def earn_coins(
    body: EarnRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """赚取金币。"""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    account = await _get_or_create_account(user, session_id)

    new_balance = account["balance"] + body.amount
    await execute(
        "UPDATE user_coins SET balance = %s, total_earned = total_earned + %s WHERE id = %s",
        (new_balance, body.amount, account["id"]),
    )

    # 记录流水
    await execute(
        "INSERT INTO coin_transactions (coin_account_id, amount, reason, reference_type, "
        "reference_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
        (account["id"], body.amount, body.reason, body.reference_type,
         body.reference_id, new_balance),
    )

    logger.info("[coins] User %s earned %d coins: %s", user["id"] if user else "anon", body.amount, body.reason)
    return {"balance": new_balance, "earned": body.amount}


@router.post("/spend")
async def spend_coins(
    body: SpendRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """消费金币。"""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    account = await _get_or_create_account(user, session_id)

    if account["balance"] < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    new_balance = account["balance"] - body.amount
    await execute(
        "UPDATE user_coins SET balance = %s, total_spent = total_spent + %s WHERE id = %s",
        (new_balance, body.amount, account["id"]),
    )

    await execute(
        "INSERT INTO coin_transactions (coin_account_id, amount, reason, reference_type, "
        "reference_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
        (account["id"], -body.amount, body.reason, body.reference_type,
         body.reference_id, new_balance),
    )

    return {"balance": new_balance, "spent": body.amount}


@router.post("/checkin")
async def daily_checkin(
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """每日签到，奖励 10 金币。简单策略：允许 24h 内多次调用但不叠加。"""
    session_id = request.cookies.get("thread_id") or request.headers.get("X-Session-Id")
    account = await _get_or_create_account(user, session_id)

    # 检查今天是否已签到
    from datetime import datetime, timedelta
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    today_txn = await fetchval(
        "SELECT COUNT(*) FROM coin_transactions "
        "WHERE coin_account_id = %s AND reason = 'Daily check-in' AND created_at >= %s",
        (account["id"], today_start),
    )
    if today_txn and today_txn > 0:
        return {"message": "Already checked in today", "balance": account["balance"]}

    new_balance = account["balance"] + DAILY_REWARD
    await execute(
        "UPDATE user_coins SET balance = %s, total_earned = total_earned + %s WHERE id = %s",
        (new_balance, DAILY_REWARD, account["id"]),
    )
    await execute(
        "INSERT INTO coin_transactions (coin_account_id, amount, reason, balance_after) "
        "VALUES (%s, %s, 'Daily check-in', %s)",
        (account["id"], DAILY_REWARD, new_balance),
    )

    return {"message": f"Check-in! +{DAILY_REWARD} coins", "balance": new_balance}
