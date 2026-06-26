"""
用户中心路由：个人资料、历史记录。

GET   /users/me                      — 当前用户完整资料
PATCH /users/me                      — 更新个人资料
PATCH /users/me/measurements          — 更新身体尺码
GET   /users/me/history/recommendations — 推荐对话历史
GET   /users/me/history/tryons        — 虚拟试穿历史
GET   /users/me/history/3dmodels      — 3D 模型生成历史
GET   /users/me/orders                — 订单列表
GET   /users/me/orders/{id}           — 订单详情
GET   /users/me/coins/transactions    — 金币流水
GET   /users/me/coupons               — 我的优惠券
"""

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from loguru import logger

from src.api.middleware.auth import get_current_user
from src.config import settings
from src.database import execute, fetchall, fetchone, fetchval

router = APIRouter(prefix="/users", tags=["Users"])


# ── Request Models ───────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[str] = None
    preferred_language: Optional[str] = None


class MeasurementsUpdate(BaseModel):
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    usual_size: Optional[str] = None
    shoulder_width_cm: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None


# ── Profile Routes ───────────────────────────────────────────────────────────────

@router.get("/me")
async def get_profile(user: dict = Depends(get_current_user)):
    """获取当前用户完整资料（含身体尺码）。"""
    full = await fetchone(
        "SELECT id, username, email, avatar_url, gender, body_measurements, "
        "preferred_language, role, is_active, created_at, updated_at "
        "FROM users WHERE id = %s",
        (user["id"],),
    )
    if not full:
        raise HTTPException(status_code=404, detail="User not found")
    # 序列化 datetime
    if full.get("created_at"):
        full["created_at"] = str(full["created_at"])
    if full.get("updated_at"):
        full["updated_at"] = str(full["updated_at"])
    return {"user": full}


@router.patch("/me")
async def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    """更新个人资料（仅更新非空字段）。"""
    updates = []
    args = []

    for field in ("username", "email", "avatar_url", "gender", "preferred_language"):
        val = getattr(body, field, None)
        if val is not None:
            # 检查 username/email 唯一性
            if field in ("username", "email"):
                existing = await fetchval(
                    f"SELECT id FROM users WHERE {field} = %s AND id != %s",
                    (val, user["id"]),
                )
                if existing:
                    raise HTTPException(status_code=409, detail=f"{field} already taken")

            updates.append(f"{field} = %s")
            args.append(val)

    if not updates:
        return {"message": "No changes", "user": user}

    args.append(user["id"])
    await execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
        tuple(args),
    )

    # 返回更新后的用户
    updated = await fetchone(
        "SELECT id, username, email, avatar_url, gender, body_measurements, "
        "preferred_language, role FROM users WHERE id = %s",
        (user["id"],),
    )
    return {"message": "Profile updated", "user": updated}


@router.patch("/me/measurements")
async def update_measurements(
    body: MeasurementsUpdate,
    user: dict = Depends(get_current_user),
):
    """更新身体尺码。自动合并到已有 JSON。"""
    # 获取当前 measurements
    current_raw = await fetchval(
        "SELECT body_measurements FROM users WHERE id = %s",
        (user["id"],),
    )

    if current_raw and isinstance(current_raw, str):
        current = json.loads(current_raw)
    elif isinstance(current_raw, dict):
        current = current_raw
    else:
        current = {}

    # 合并非空字段
    for field in MeasurementsUpdate.model_fields:
        val = getattr(body, field, None)
        if val is not None:
            current[field] = val

    await execute(
        "UPDATE users SET body_measurements = %s WHERE id = %s",
        (json.dumps(current), user["id"]),
    )

    return {"message": "Measurements updated", "body_measurements": current}


@router.post("/me/photo")
async def upload_body_photo(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传/更新本人默认全身照，URL 写入 body_measurements.body_photo_url。"""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP supported")

    content = await file.read()
    if len(content) > 8 * 1024 * 1024:  # 8MB
        raise HTTPException(status_code=400, detail="File too large (max 8MB)")

    upload_dir = Path(settings.DOWNLOAD_DIR) / "users" / str(user["id"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(upload_dir / filename, "wb") as f:
        f.write(content)

    url = f"/uploads/users/{user['id']}/{filename}"

    # 合并进 body_measurements JSON
    current_raw = await fetchval(
        "SELECT body_measurements FROM users WHERE id = %s", (user["id"],)
    )
    if current_raw and isinstance(current_raw, str):
        current = json.loads(current_raw)
    elif isinstance(current_raw, dict):
        current = current_raw
    else:
        current = {}
    current["body_photo_url"] = url
    await execute(
        "UPDATE users SET body_measurements = %s WHERE id = %s",
        (json.dumps(current), user["id"]),
    )

    logger.info("[users] User %s uploaded body photo: %s", user["id"], url)
    return {"message": "Body photo updated", "body_photo_url": url}


# ── History Routes ───────────────────────────────────────────────────────────────

@router.get("/me/history/recommendations")
async def get_recommendation_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """获取用户的推荐对话历史（分页）。"""
    # 用户拥有的 sessions
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM conversations c "
        "JOIN sessions s ON c.session_id = s.id "
        "WHERE s.user_id = %s",
        (user["id"],),
    )

    rows = await fetchall(
        "SELECT c.id, c.session_id, c.step, c.created_at, "
        "c.graph_state->>'$.query' AS query "
        "FROM conversations c "
        "JOIN sessions s ON c.session_id = s.id "
        "WHERE s.user_id = %s "
        "ORDER BY c.created_at DESC "
        "LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    # 序列化
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


@router.get("/me/history/tryons")
async def get_tryon_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """获取虚拟试穿历史（分页）。"""
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM tryon_records tr "
        "JOIN sessions s ON tr.session_id = s.id "
        "WHERE s.user_id = %s",
        (user["id"],),
    )

    rows = await fetchall(
        "SELECT tr.id, tr.product_id, tr.product_image_url, tr.result_image_url, "
        "tr.result_image_base64, tr.success, tr.created_at, p.product_name, p.brand "
        "FROM tryon_records tr "
        "JOIN sessions s ON tr.session_id = s.id "
        "LEFT JOIN products p ON tr.product_id = p.id "
        "WHERE s.user_id = %s "
        "ORDER BY tr.created_at DESC "
        "LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


@router.get("/me/history/3dmodels")
async def get_3dmodel_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """获取 3D 模型生成历史。"""
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM img2model_tasks t "
        "JOIN sessions s ON t.session_id = s.id "
        "WHERE s.user_id = %s",
        (user["id"],),
    )

    rows = await fetchall(
        "SELECT t.id, t.session_id, t.product_id, t.status, t.progress, "
        "t.mesh_glb_url, t.rig_glb_url, t.anim_glb_url, t.animation_preset, "
        "t.error_message, t.created_at, p.product_name, p.image_url "
        "FROM img2model_tasks t "
        "JOIN sessions s ON t.session_id = s.id "
        "LEFT JOIN products p ON t.product_id = p.id "
        "WHERE s.user_id = %s "
        "ORDER BY t.created_at DESC "
        "LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


@router.get("/me/history/messages")
async def get_session_messages(
    session_id: str = Query(..., description="会话 ID（thread_id）"),
    user: dict = Depends(get_current_user),
):
    """获取某会话的对话消息（须属于当前用户）。供从生成历史跳回试衣间复现交流记录。"""
    owns = await fetchval(
        "SELECT id FROM sessions WHERE id = %s AND user_id = %s",
        (session_id, user["id"]),
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await fetchall(
        "SELECT role, content, created_at FROM messages "
        "WHERE session_id = %s ORDER BY created_at ASC, id ASC",
        (session_id,),
    )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
    return {"session_id": session_id, "items": rows}


@router.get("/me/history/browse")
async def get_browse_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
    user: dict = Depends(get_current_user),
):
    """获取浏览历史（最近浏览的商品，去重，最近优先）。"""
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM browse_history WHERE user_id = %s",
        (user["id"],),
    )
    rows = await fetchall(
        "SELECT bh.product_id, bh.viewed_at, p.product_name, p.brand, p.label, "
        "p.price, p.currency, p.image_url "
        "FROM browse_history bh JOIN products p ON bh.product_id = p.id "
        "WHERE bh.user_id = %s AND p.is_active = 1 "
        "ORDER BY bh.viewed_at DESC LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    for r in rows:
        if r.get("viewed_at"):
            r["viewed_at"] = str(r["viewed_at"])
        if r.get("price") is not None:
            r["price"] = float(r["price"])

    return {"total": total or 0, "page": page, "page_size": page_size, "items": rows}


# ── Orders ───────────────────────────────────────────────────────────────────────

@router.get("/me/orders")
async def get_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """获取用户订单列表。"""
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM orders WHERE user_id = %s",
        (user["id"],),
    )

    rows = await fetchall(
        "SELECT id, order_no, total_amount, discount_amount, final_amount, "
        "status, paid_at, created_at "
        "FROM orders WHERE user_id = %s "
        "ORDER BY created_at DESC "
        "LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    for r in rows:
        for f in ("created_at", "paid_at", "updated_at"):
            if r.get(f):
                r[f] = str(r[f])

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


@router.get("/me/orders/{order_id}")
async def get_order_detail(
    order_id: int,
    user: dict = Depends(get_current_user),
):
    """获取订单详情（含商品明细）。"""
    order = await fetchone(
        "SELECT id, order_no, user_id, used_coupon_id, total_amount, "
        "discount_amount, final_amount, status, paid_at, created_at, updated_at "
        "FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user["id"]),
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for f in ("created_at", "paid_at", "updated_at"):
        if order.get(f):
            order[f] = str(order[f])

    items = await fetchall(
        "SELECT oi.id, oi.product_id, oi.product_name_snap, oi.price_snap, "
        "oi.selected_size, oi.quantity "
        "FROM order_items oi WHERE oi.order_id = %s",
        (order_id,),
    )

    return {"order": order, "items": items}


# ── Coins ────────────────────────────────────────────────────────────────────────

@router.get("/me/coins/transactions")
async def get_coin_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """获取金币流水。"""
    # 先获取用户的金币账户
    account = await fetchone(
        "SELECT id, balance, total_earned, total_spent FROM user_coins WHERE user_id = %s",
        (user["id"],),
    )

    if not account:
        return {
            "balance": 0,
            "total_earned": 0,
            "total_spent": 0,
            "transactions": [],
        }

    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(*) FROM coin_transactions WHERE coin_account_id = %s",
        (account["id"],),
    )

    txs = await fetchall(
        "SELECT id, amount, reason, reference_type, balance_after, created_at "
        "FROM coin_transactions WHERE coin_account_id = %s "
        "ORDER BY created_at DESC "
        "LIMIT %s OFFSET %s",
        (account["id"], page_size, offset),
    )
    for tx in txs:
        if tx.get("created_at"):
            tx["created_at"] = str(tx["created_at"])

    return {
        "balance": account["balance"],
        "total_earned": account["total_earned"],
        "total_spent": account["total_spent"],
        "total_transactions": total,
        "page": page,
        "page_size": page_size,
        "transactions": txs,
    }


# ── Coupons ──────────────────────────────────────────────────────────────────────

@router.get("/me/coupons")
async def get_my_coupons(user: dict = Depends(get_current_user)):
    """获取用户持有的所有有效优惠券。"""
    rows = await fetchall(
        "SELECT uc.id, uc.status, uc.acquired_at, uc.expires_at, "
        "c.name, c.code, c.discount_type, c.discount_value, "
        "c.min_order_amount, c.max_discount_amount "
        "FROM user_coupons uc "
        "JOIN coupons c ON uc.coupon_id = c.id "
        "WHERE uc.user_id = %s AND uc.status = 'available' "
        "ORDER BY uc.expires_at ASC",
        (user["id"],),
    )
    for r in rows:
        for f in ("acquired_at", "expires_at"):
            if r.get(f):
                r[f] = str(r[f])

    return {"coupons": rows}
