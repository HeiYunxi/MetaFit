"""
会话工具：确保存在一条 sessions 记录，并在用户登录时回填 user_id。

试穿 / 图生3D / 浏览历史等需要把记录挂到 session 上，
而历史查询又通过 sessions.user_id 反查用户，因此统一在这里维护。
"""

from uuid import uuid4

from fastapi import Request

from src.database import execute, fetchval


async def ensure_session(request: Request, user: dict | None) -> str:
    """返回一个有效的 session_id（不存在则创建），登录用户会回填 user_id。"""
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
