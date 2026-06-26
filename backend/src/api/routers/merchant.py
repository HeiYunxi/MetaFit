"""
商家管理路由（需要 merchant/admin 角色）。

GET    /merchant/profile               — 获取商家资料
PATCH  /merchant/profile               — 更新商家资料
GET    /merchant/products              — 我的商品列表
GET    /merchant/products/{id}         — 商品详情
POST   /merchant/products              — 创建商品
PUT    /merchant/products/{id}         — 更新商品
DELETE /merchant/products/{id}         — 下架商品
POST   /merchant/products/{id}/sizes   — 管理尺码
POST   /merchant/products/reindex      — 触发全量索引重建
GET    /merchant/products/reindex/status — 重建状态
POST   /merchant/upload/image          — 上传商品图片
GET    /merchant/orders                — 本店商品订单
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from loguru import logger
from pydantic import BaseModel

from src.api.middleware.auth import get_current_user, require_role
from src.config import settings
from src.database import execute, fetchall, fetchone, fetchval, insert_and_get_id

router = APIRouter(prefix="/merchant", tags=["Merchant"])

# 全量重建后台任务状态（单进程内只允许一个重建任务）
_reindex_running = False
_reindex_log_id: int | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _generate_page_content(product: dict, sizes: list[str] | None = None) -> str:
    """生成 RAG 检索文本（与 embedding.py 逻辑一致）。"""
    parts = [product["product_name"]]
    if product.get("brand"):
        parts.append(f"Brand: {product['brand']}")
    if product.get("label"):
        parts.append(f"Category: {product['label']}")
    if product.get("description"):
        parts.append(product["description"])
    if product.get("composition_outer"):
        parts.append(f"Outer: {product['composition_outer']}")
    if product.get("composition_lining"):
        parts.append(f"Lining: {product['composition_lining']}")
    if product.get("washing_instructions"):
        parts.append(f"Care: {product['washing_instructions']}")
    if sizes:
        parts.append(f"Sizes: {', '.join(sizes)}")
    return ". ".join(parts)


async def _fetch_product_for_index(product_id: int) -> dict | None:
    """读取带聚合尺码的商品行，供向量索引增量写入。"""
    return await fetchone(
        "SELECT p.*, GROUP_CONCAT(ps.size_label) AS sizes "
        "FROM products p "
        "LEFT JOIN product_sizes ps ON p.id = ps.product_id "
        "WHERE p.id = %s AND p.is_active = 1 "
        "GROUP BY p.id",
        (product_id,),
    )


async def _index_product_chroma(product_id: int) -> bool:
    """新品/更新后增量写入 Chroma（self-query 主链路准实时可见）。"""
    row = await _fetch_product_for_index(product_id)
    if not row:
        return False
    from src.services.vector_index_service import add_single_document

    ok = await add_single_document(row)
    if ok:
        from src.services.vector_index_service import _reset_recommender_caches
        _reset_recommender_caches()
    return ok


# ── Models ──────────────────────────────────────────────────────────────────────

class MerchantProfileUpdate(BaseModel):
    store_name: str | None = None
    store_description: str | None = None
    contact_phone: str | None = None


class ProductCreate(BaseModel):
    product_name: str
    brand: str = ""
    label: str = ""
    description: str = ""
    price: float = 0.0
    currency: str = "CNY"
    original_price: float | None = None
    image_url: str = ""
    composition_outer: str = ""
    composition_lining: str = ""
    washing_instructions: str = ""
    model_info: str = ""
    sizes: list[dict] | None = None  # [{size_label, stock_status}]


class ProductUpdate(BaseModel):
    product_name: str | None = None
    brand: str | None = None
    label: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    original_price: float | None = None
    image_url: str | None = None
    composition_outer: str | None = None
    composition_lining: str | None = None
    washing_instructions: str | None = None
    model_info: str | None = None
    is_active: int | None = None


class SizeEntry(BaseModel):
    size_label: str
    size_category: str = "letter"
    stock_status: str = "unknown"


# ── Profile ─────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(user: dict = Depends(require_role("merchant", "admin"))):
    """获取商家资料（含店铺统计）。"""
    product_count = await fetchval(
        "SELECT COUNT(*) FROM products WHERE merchant_id = %s AND is_active = 1",
        (user["id"],),
    )
    total_orders = await fetchval(
        "SELECT COUNT(*) FROM orders o "
        "JOIN order_items oi ON o.id = oi.order_id "
        "JOIN products p ON oi.product_id = p.id "
        "WHERE p.merchant_id = %s",
        (user["id"],),
    )
    return {
        "merchant_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "product_count": product_count,
        "total_orders": total_orders,
    }


# ── Product CRUD ────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    label: str = Query(default=""),
    is_active: int | None = None,
    user: dict = Depends(require_role("merchant", "admin")),
):
    """获取商家的商品列表（分页+筛选）。"""
    conditions = ["merchant_id = %s"]
    args = [user["id"]]

    if search:
        conditions.append("(product_name LIKE %s OR brand LIKE %s)")
        args.extend([f"%{search}%", f"%{search}%"])
    if label:
        conditions.append("label = %s")
        args.append(label)
    if is_active is not None:
        conditions.append("is_active = %s")
        args.append(is_active)

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    total = await fetchval(
        f"SELECT COUNT(*) FROM products WHERE {where}", tuple(args),
    )
    rows = await fetchall(
        f"SELECT id, product_name, brand, label, price, currency, image_url, "
        f"is_active, created_at FROM products WHERE {where} "
        f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(args + [page_size, offset]),
    )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/products/{product_id}")
async def get_product(
    product_id: int,
    user: dict = Depends(require_role("merchant", "admin")),
):
    """获取商品详情（含尺码信息）。"""
    product = await fetchone(
        "SELECT * FROM products WHERE id = %s AND merchant_id = %s",
        (product_id, user["id"]),
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for f in ("created_at", "updated_at"):
        if product.get(f):
            product[f] = str(product[f])

    sizes = await fetchall(
        "SELECT id, size_label, size_category, stock_status FROM product_sizes "
        "WHERE product_id = %s ORDER BY id ASC",
        (product_id,),
    )

    return {"product": product, "sizes": sizes}


@router.post("/products")
async def create_product(
    body: ProductCreate,
    user: dict = Depends(require_role("merchant", "admin")),
):
    """创建商品（会自动生成 page_content 并写入向量索引）。"""
    # 生成 page_content
    sizes_labels = [s["size_label"] for s in (body.sizes or [])]
    product_data = {
        "product_name": body.product_name,
        "brand": body.brand,
        "label": body.label,
        "description": body.description,
        "composition_outer": body.composition_outer,
        "composition_lining": body.composition_lining,
        "washing_instructions": body.washing_instructions,
    }
    page_content = _generate_page_content(product_data, sizes_labels)

    product_id = await insert_and_get_id(
        "INSERT INTO products (merchant_id, product_name, brand, label, description, "
        "price, currency, original_price, image_url, composition_outer, "
        "composition_lining, washing_instructions, model_info, page_content) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (user["id"], body.product_name, body.brand, body.label, body.description,
         body.price, body.currency, body.original_price, body.image_url,
         body.composition_outer, body.composition_lining, body.washing_instructions,
         body.model_info, page_content),
    )

    # 插入尺码
    if body.sizes:
        for s in body.sizes:
            await execute(
                "INSERT INTO product_sizes (product_id, size_label, size_category, stock_status) "
                "VALUES (%s, %s, %s, %s)",
                (product_id, s["size_label"],
                 s.get("size_category", "letter"),
                 s.get("stock_status", "unknown")),
            )

    # 增量写入 Chroma，使 self-query 主链路准实时可检索新品
    indexed = await _index_product_chroma(product_id)
    await _log_reindex("single", user["id"], product_id, status="done" if indexed else "failed")

    logger.info(
        "[merchant] Product %d created by user %d: %s (chroma_indexed=%s)",
        product_id, user["id"], body.product_name, indexed,
    )
    return {"message": "Product created", "product_id": product_id, "chroma_indexed": indexed}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    body: ProductUpdate,
    user: dict = Depends(require_role("merchant", "admin")),
):
    """更新商品。"""
    # 验证所有权
    existing = await fetchone(
        "SELECT * FROM products WHERE id = %s AND merchant_id = %s",
        (product_id, user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    updates = []
    args = []
    for field in ProductUpdate.model_fields:
        val = getattr(body, field, None)
        if val is not None:
            updates.append(f"{field} = %s")
            args.append(val)

    if updates:
        # 如果更新了名称/描述/材质，重建 page_content
        if any(f in ProductUpdate.model_fields_set for f in
               ("product_name", "description", "composition_outer",
                "composition_lining", "washing_instructions")):
            updated_data = {**existing}
            for field in ProductUpdate.model_fields_set:
                val = getattr(body, field)
                if val is not None:
                    updated_data[field] = val
            # 获取尺码
            sizes = await fetchall(
                "SELECT size_label FROM product_sizes WHERE product_id = %s",
                (product_id,),
            )
            size_labels = [s["size_label"] for s in sizes]
            page_content = _generate_page_content(updated_data, size_labels)
            updates.append("page_content = %s")
            args.append(page_content)

        args.append(product_id)
        await execute(
            f"UPDATE products SET {', '.join(updates)} WHERE id = %s",
            tuple(args),
        )
        await _index_product_chroma(product_id)

    return {"message": "Product updated"}


@router.delete("/products/{product_id}")
async def deactivate_product(
    product_id: int,
    user: dict = Depends(require_role("merchant", "admin")),
):
    """下架商品（软删除）。"""
    existing = await fetchval(
        "SELECT id FROM products WHERE id = %s AND merchant_id = %s",
        (product_id, user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    await execute(
        "UPDATE products SET is_active = 0, updated_at = NOW() WHERE id = %s",
        (product_id,),
    )

    await _log_reindex("single", user["id"], product_id)
    return {"message": "Product deactivated"}


@router.post("/products/{product_id}/sizes")
async def update_product_sizes(
    product_id: int,
    sizes: list[SizeEntry],
    user: dict = Depends(require_role("merchant", "admin")),
):
    """替换商品尺码（全量替换）。"""
    existing = await fetchval(
        "SELECT id FROM products WHERE id = %s AND merchant_id = %s",
        (product_id, user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    # 删除旧尺码
    await execute("DELETE FROM product_sizes WHERE product_id = %s", (product_id,))

    # 插入新尺码
    for s in sizes:
        await execute(
            "INSERT INTO product_sizes (product_id, size_label, size_category, stock_status) "
            "VALUES (%s, %s, %s, %s)",
            (product_id, s.size_label, s.size_category, s.stock_status),
        )

    # 更新 page_content 中的尺码信息
    size_labels = [s.size_label for s in sizes]
    product = await fetchone(
        "SELECT * FROM products WHERE id = %s", (product_id,)
    )
    updated_data = {**product, "product_name": product["product_name"]}
    page_content = _generate_page_content(updated_data, size_labels)
    await execute(
        "UPDATE products SET page_content = %s WHERE id = %s",
        (page_content, product_id),
    )

    await _index_product_chroma(product_id)
    return {"message": f"Sizes updated ({len(sizes)} entries)"}


# ── Index Rebuild ───────────────────────────────────────────────────────────────

async def _log_reindex(
    rebuild_type: str,
    triggered_by: int | None = None,
    product_id: int | None = None,
    status: str = "running",
) -> int:
    """记录索引重建日志，返回 log id。"""
    return await insert_and_get_id(
        "INSERT INTO index_rebuild_log (triggered_by, rebuild_type, product_id, status) "
        "VALUES (%s, %s, %s, %s)",
        (triggered_by, rebuild_type, product_id, status),
    )


async def _run_full_reindex_task(log_id: int) -> None:
    """后台全量重建：在线程池执行，不阻塞 API 主循环。"""
    global _reindex_running, _reindex_log_id
    import time

    start = time.time()
    try:
        products = await fetchall(
            "SELECT p.*, GROUP_CONCAT(ps.size_label) AS sizes "
            "FROM products p "
            "LEFT JOIN product_sizes ps ON p.id = ps.product_id "
            "WHERE p.is_active = 1 "
            "GROUP BY p.id"
        )
        if not products:
            await execute(
                "UPDATE index_rebuild_log SET status='done', doc_count=0, elapsed_ms=0 WHERE id=%s",
                (log_id,),
            )
            return

        from src.services.vector_index_service import rebuild_indexes_from_db

        doc_count = await rebuild_indexes_from_db(products)
        elapsed = int((time.time() - start) * 1000)
        await execute(
            "UPDATE index_rebuild_log SET status='done', doc_count=%s, elapsed_ms=%s WHERE id=%s",
            (doc_count, elapsed, log_id),
        )
        logger.info("[merchant] Full reindex completed: %d docs in %dms", doc_count, elapsed)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.exception("[merchant] Reindex failed: %s", e)
        await execute(
            "UPDATE index_rebuild_log SET status='failed', error_message=%s, elapsed_ms=%s WHERE id=%s",
            (str(e)[:1024], elapsed, log_id),
        )
    finally:
        _reindex_running = False
        _reindex_log_id = None


@router.post("/products/reindex")
async def trigger_reindex(user: dict = Depends(require_role("merchant", "admin"))):
    """
    触发全量索引重建（后台异步执行，立即返回）。
    从 MySQL products 表读取所有活跃商品，重建 FAISS / BM25 / Chroma / cross-encoder。
    进度见 GET /merchant/products/reindex/status。
    """
    global _reindex_running, _reindex_log_id

    if _reindex_running:
        return {
            "message": "Rebuild already in progress",
            "log_id": _reindex_log_id,
            "status": "running",
        }

    log_id = await _log_reindex("full", user["id"])
    _reindex_running = True
    _reindex_log_id = log_id
    asyncio.create_task(_run_full_reindex_task(log_id))
    logger.info("[merchant] Full reindex started in background (log_id=%d)", log_id)
    return {"message": "Rebuild started", "log_id": log_id, "status": "running"}


@router.get("/products/reindex/status")
async def get_reindex_status(user: dict = Depends(require_role("merchant", "admin"))):
    """查询最近一次索引重建记录。"""
    last = await fetchone(
        "SELECT * FROM index_rebuild_log ORDER BY created_at DESC LIMIT 1"
    )
    if last and last.get("created_at"):
        last["created_at"] = str(last["created_at"])
    return {"last_rebuild": last}


# ── Image Upload ────────────────────────────────────────────────────────────────

@router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("merchant", "admin")),
):
    """上传商品图片，返回 URL。"""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP supported")

    # 保存到 backend/download/products/{merchant_id}/
    upload_dir = Path(settings.DOWNLOAD_DIR) / "products" / str(user["id"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = upload_dir / filename

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    with open(filepath, "wb") as f:
        f.write(content)

    # 返回相对 URL
    url = f"/assets/products/{user['id']}/{filename}"

    # 确保 StaticFiles 能访问
    assets_dir = Path(settings.DOWNLOAD_DIR)
    logger.info("[merchant] Image uploaded: %s", url)

    return {"url": url, "filename": filename}


# ── Orders ──────────────────────────────────────────────────────────────────────

@router.get("/orders")
async def get_merchant_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(require_role("merchant", "admin")),
):
    """获取本店商品关联的订单。"""
    offset = (page - 1) * page_size
    total = await fetchval(
        "SELECT COUNT(DISTINCT o.id) FROM orders o "
        "JOIN order_items oi ON o.id = oi.order_id "
        "JOIN products p ON oi.product_id = p.id "
        "WHERE p.merchant_id = %s",
        (user["id"],),
    )

    rows = await fetchall(
        "SELECT DISTINCT o.id, o.order_no, o.total_amount, o.final_amount, "
        "o.status, o.created_at "
        "FROM orders o "
        "JOIN order_items oi ON o.id = oi.order_id "
        "JOIN products p ON oi.product_id = p.id "
        "WHERE p.merchant_id = %s "
        "ORDER BY o.created_at DESC "
        "LIMIT %s OFFSET %s",
        (user["id"], page_size, offset),
    )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return {"total": total, "page": page, "page_size": page_size, "items": rows}
