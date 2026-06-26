"""
认证业务逻辑：密码哈希、JWT 签发/验证、匿名会话桥接。

依赖于 database.py 进行 MySQL 操作。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from loguru import logger
from passlib.context import CryptContext

from src.config import settings
from src.database import execute, fetchone, fetchval

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── 密码工具 ────────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """bcrypt 哈希密码，cost=12。"""
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配。"""
    return _pwd_ctx.verify(plain, hashed)


# ── JWT 工具 ────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, role: str) -> str:
    """签发 Access Token（短有效期，15 分钟）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """签发 Refresh Token（长有效期，7 天）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT，失败抛出 jwt.PyJWTError。"""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "sub", "type"]},
    )


# ── 用户查询 ────────────────────────────────────────────────────────────────────

async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    return await fetchone(
        "SELECT id, username, email, avatar_url, gender, body_measurements, "
        "preferred_language, role, is_active, created_at "
        "FROM users WHERE id = %s",
        (user_id,),
    )


async def get_user_by_username(username: str) -> dict[str, Any] | None:
    return await fetchone(
        "SELECT * FROM users WHERE username = %s",
        (username,),
    )


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    return await fetchone(
        "SELECT * FROM users WHERE email = %s",
        (email,),
    )


# ── 注册 ────────────────────────────────────────────────────────────────────────

async def register_user_full(
    username: str,
    email: str,
    password: str,
    gender: str = "prefer_not_to_say",
    body_measurements: dict | None = None,
    role: str = "user",
) -> dict[str, Any] | None:
    """注册用户并返回完整用户对象。"""
    import json
    from src.database import insert_and_get_id

    # 仅允许自助注册为普通用户或商家，杜绝越权注册 admin
    if role not in ("user", "merchant"):
        role = "user"

    existing = await fetchval(
        "SELECT id FROM users WHERE username = %s OR email = %s",
        (username, email),
    )
    if existing:
        raise ValueError("Username or email already exists")

    password_hash = hash_password(password)
    measurements_json = json.dumps(body_measurements) if body_measurements else None

    user_id = await insert_and_get_id(
        "INSERT INTO users (username, email, password_hash, gender, body_measurements, role) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (username, email, password_hash, gender, measurements_json, role),
    )

    return await get_user_by_id(user_id)


# ── 登录 ────────────────────────────────────────────────────────────────────────

async def authenticate_user(login: str, password: str) -> dict[str, Any] | None:
    """
    验证用户凭据。login 可以是 username 或 email。

    Returns:
        用户字典（不含 password_hash），失败返回 None
    """
    user = await fetchone(
        "SELECT * FROM users WHERE username = %s OR email = %s",
        (login, login),
    )
    if not user:
        return None
    if not user.get("is_active", 1):
        return None
    if not verify_password(password, user["password_hash"] or ""):
        return None

    # 不返回密码哈希
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "avatar_url": user["avatar_url"],
        "gender": user["gender"],
        "body_measurements": user["body_measurements"],
        "preferred_language": user["preferred_language"],
        "role": user["role"],
        "is_active": user["is_active"],
        "created_at": user["created_at"],
    }


# ── 匿名会话桥接 ───────────────────────────────────────────────────────────────

async def bridge_anonymous_session(
    user_id: int,
    session_id: str | None,
) -> None:
    """
    登录后将匿名会话数据迁移到登录用户。

    1. 关联 sessions 到 user_id
    2. 合并购物车（匿名 session 的 cart_items → 用户关联）
    3. 迁移金币（取余额较大者）
    """
    if not session_id:
        return

    try:
        # 1. 更新 session 的 user_id
        await execute(
            "UPDATE sessions SET user_id = %s WHERE id = %s AND user_id IS NULL",
            (user_id, session_id),
        )

        # 2. 获取匿名购物车商品
        anon_cart = await fetchall(
            "SELECT product_id, selected_size FROM cart_items WHERE session_id = %s",
            (session_id,),
        )

        # 3. 为登录用户创建/合并购物车条目
        for item in anon_cart:
            # 获取或创建 session-to-user 的购物车（先查 user 的 sessions）
            user_sessions = await fetchall(
                "SELECT id FROM sessions WHERE user_id = %s AND is_active = 1 LIMIT 1",
                (user_id,),
            )
            target_session_id = user_sessions[0]["id"] if user_sessions else session_id

            existing = await fetchval(
                "SELECT id FROM cart_items WHERE session_id = %s AND product_id = %s",
                (target_session_id, item["product_id"]),
            )
            if not existing:
                await execute(
                    "INSERT INTO cart_items (session_id, product_id, selected_size) "
                    "VALUES (%s, %s, %s)",
                    (target_session_id, item["product_id"], item["selected_size"]),
                )

        # 4. 迁移金币（取余额较大者）
        anon_coins = await fetchone(
            "SELECT * FROM user_coins WHERE session_id = %s",
            (session_id,),
        )
        if anon_coins:
            user_coins = await fetchone(
                "SELECT * FROM user_coins WHERE user_id = %s",
                (user_id,),
            )
            if user_coins:
                # 合并：取最大值
                merged_balance = max(
                    anon_coins["balance"], user_coins["balance"]
                )
                merged_earned = anon_coins["total_earned"] + user_coins["total_earned"]
                merged_spent = anon_coins["total_spent"] + user_coins["total_spent"]
                await execute(
                    "UPDATE user_coins SET balance = %s, total_earned = %s, total_spent = %s "
                    "WHERE user_id = %s",
                    (merged_balance, merged_earned, merged_spent, user_id),
                )
                # 删除匿名金币记录
                await execute(
                    "DELETE FROM user_coins WHERE id = %s",
                    (anon_coins["id"],),
                )
            else:
                # 直接迁移
                await execute(
                    "UPDATE user_coins SET user_id = %s, session_id = NULL "
                    "WHERE id = %s",
                    (user_id, anon_coins["id"]),
                )

        logger.info("[auth] Bridged anonymous session %s → user %s", session_id, user_id)

    except Exception as exc:
        logger.warning("[auth] Session bridge failed (non-fatal): %s", exc)
