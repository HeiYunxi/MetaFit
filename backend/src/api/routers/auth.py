"""
认证接口路由：注册、登录、刷新 Token、登出、当前用户。

POST /auth/register  — 注册
POST /auth/login     — 登录
POST /auth/refresh   — 刷新 access token
POST /auth/logout    — 登出
GET  /auth/me        — 当前登录用户信息
"""

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from loguru import logger

from src.api.middleware.auth import get_current_user
from src.services.auth_service import (
    authenticate_user,
    bridge_anonymous_session,
    create_access_token,
    create_refresh_token,
    decode_token,
    register_user_full,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request / Response Models ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    gender: str = "prefer_not_to_say"
    body_measurements: dict | None = None
    role: str = "user"  # 仅允许 user / merchant，后端会强制校验


class LoginRequest(BaseModel):
    login: str  # username or email
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ── Routes ───────────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(body: RegisterRequest, response: Response):
    """注册新用户，自动签发双 Token。"""
    # 基本校验
    if len(body.username) < 3 or len(body.username) > 64:
        raise HTTPException(status_code=400, detail="Username must be 3-64 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        user = await register_user_full(
            username=body.username,
            email=body.email,
            password=body.password,
            gender=body.gender,
            body_measurements=body.body_measurements,
            role=body.role if body.role in ("user", "merchant") else "user",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    access_token = create_access_token(user["id"], user["role"])
    refresh_token = create_refresh_token(user["id"])

    _set_refresh_cookie(response, refresh_token)

    return AuthResponse(
        access_token=access_token,
        user=_public_user(user),
    )


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    thread_id: str | None = Cookie(default=None),
):
    """登录并签发双 Token。自动桥接匿名会话。"""
    if not body.login or not body.password:
        raise HTTPException(status_code=400, detail="login and password are required")

    user = await authenticate_user(body.login, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 签发 token
    access_token = create_access_token(user["id"], user["role"])
    refresh_token = create_refresh_token(user["id"])

    _set_refresh_cookie(response, refresh_token)

    # 桥接匿名会话
    session_id = x_session_id or thread_id
    if session_id:
        await bridge_anonymous_session(user["id"], session_id)

    logger.info("[auth] User %s logged in, session bridge: %s", user["username"], session_id)

    return AuthResponse(
        access_token=access_token,
        user=_public_user(user),
    )


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
):
    """使用 refresh token 换取新的 access token。"""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token in cookie")

    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = int(payload["sub"])

    # 查询用户确保仍然活跃
    from src.services.auth_service import get_user_by_id
    user = await get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account deactivated or not found")

    # 签发新 token
    new_access = create_access_token(user_id, user["role"])
    new_refresh = create_refresh_token(user_id)
    _set_refresh_cookie(response, new_refresh)

    return {
        "access_token": new_access,
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/logout")
async def logout(response: Response):
    """登出：清除 refresh token cookie。"""
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
        secure=False,
        httponly=True,
        samesite="strict",
    )
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """返回当前登录用户信息（需要 Bearer Token）。"""
    return {"user": _public_user(user)}


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _public_user(user: dict) -> dict:
    """从用户字典中提取可公开返回的字段。"""
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "avatar_url": user.get("avatar_url"),
        "gender": user.get("gender"),
        "body_measurements": user.get("body_measurements"),
        "preferred_language": user.get("preferred_language"),
        "role": user.get("role"),
        "created_at": str(user.get("created_at", "")),
    }


def _set_refresh_cookie(response: Response, token: str) -> None:
    """设置 refresh token 到 HttpOnly Cookie。"""
    response.set_cookie(
        key="refresh_token",
        value=token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,  # 7 天
        path="/auth",
        httponly=True,
        secure=False,  # 开发环境不强制 HTTPS
        samesite="strict",
    )


from src.config import settings
