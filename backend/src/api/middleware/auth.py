"""
认证中间件：提供 FastAPI 依赖注入。

- get_current_user: 强制鉴权，失败返回 401
- get_optional_user: 可选鉴权，无 token 时返回 None
- require_role: 角色权限检查工厂
"""

from typing import Optional

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from src.config import settings
from src.services.auth_service import decode_token, get_user_by_id


async def _extract_access_token(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> str | None:
    """从 Authorization header 或 Cookie 中提取 access token。"""
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if access_token:
        return access_token
    return None


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> dict:
    """
    强制鉴权依赖：从请求中提取 JWT 并返回当前用户。

    用法：
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            ...
    """
    token = await _extract_access_token(request, authorization, access_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first.",
        )

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Please refresh or login again.",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token required.",
        )

    user_id = int(payload["sub"])
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user


async def get_optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> dict | None:
    """
    可选鉴权依赖：有 token 时返回用户，无 token 时返回 None。

    用法：
        @router.get("/public")
        async def public_route(user: dict | None = Depends(get_optional_user)):
            if user: ...
    """
    token = await _extract_access_token(request, authorization, access_token)
    if not token:
        return None

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
        user = await get_user_by_id(user_id)
        if user and user.get("is_active"):
            return user
        return None
    except jwt.PyJWTError:
        return None


def require_role(*roles: str):
    """
    角色权限检查工厂。

    用法：
        @router.get("/merchant/products")
        async def products(user: dict = Depends(require_role("merchant", "admin"))):
            ...
    """
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "user")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {'/'.join(roles)}, got: {user_role}",
            )
        return user

    return role_checker
