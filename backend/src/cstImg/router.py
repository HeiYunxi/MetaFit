"""
虚拟试穿接口路由（POST /try-on）。

接收用户上传的全身照和推荐商品图 URL，
转发给 service 层调用 LaoZhang 图改图模型生成试穿效果图。
"""

import base64
import binascii
import hashlib
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from loguru import logger

from src.api.middleware.auth import get_optional_user
from src.api.session_utils import ensure_session
from src.config import settings
from src.cstImg.schemas import TryOnResponse
from src.cstImg.service import run_try_on
from src.database import execute

router = APIRouter(prefix="/try-on", tags=["TryOn"])


def _save_tryon_image(session_id: str, result) -> str | None:
    """把模型返回的 base64 结果图落地成本地文件，返回可访问 URL（/uploads/tryon/...）。

    模型（Nano Banana）只回传 base64，不落地的话历史记录里就没有图片可显示。
    """
    raw = getattr(result, "tryon_image_base64", None)
    if not raw:
        return None
    try:
        # 兼容 data:image/png;base64,xxx 与纯 base64
        ext = "png"
        m = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64,(.*)", raw, re.DOTALL)
        if m:
            ext = m.group(1).lower()
            if ext in ("jpeg", "jpg"):
                ext = "jpg"
            raw = m.group(2)
        img_bytes = base64.b64decode(raw, validate=False)
        if not img_bytes:
            return None
        out_dir = Path(settings.DOWNLOAD_DIR) / "tryon" / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.{ext}"
        (out_dir / fname).write_bytes(img_bytes)
        return f"/uploads/tryon/{session_id}/{fname}"
    except (binascii.Error, ValueError, OSError) as exc:
        logger.warning("[try-on] save result image failed (non-fatal): %s", exc)
        return None


async def _persist_tryon(
    request: Request,
    user: dict | None,
    content: bytes,
    product_id: int | None,
    product_image_url: str,
    result,
) -> None:
    """尽力把一次试穿写入 tryon_records（失败不影响返回结果）。"""
    try:
        session_id = await ensure_session(request, user)
        person_hash = hashlib.sha256(content).hexdigest()
        success = bool(getattr(result, "success", False))
        result_b64 = getattr(result, "tryon_image_base64", None)
        # 模型多数情况下只回 base64：成功时落地成本地文件，让历史能展示效果图
        result_url = getattr(result, "tryon_image_url", None)
        if success and not result_url:
            result_url = _save_tryon_image(session_id, result)
        error_msg = None if success else (getattr(result, "message", None) or "")
        await execute(
            "INSERT INTO tryon_records (session_id, product_id, person_image_hash, "
            "product_image_url, result_image_base64, result_image_url, success, error_message) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (session_id, product_id, person_hash, product_image_url[:1024],
             result_b64, (result_url[:1024] if result_url else None),
             1 if success else 0, (error_msg[:512] if error_msg else None)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[try-on] persist record failed (non-fatal): %s", exc)

# 允许的图片格式（用于上传前拦截非法类型）
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
# 上传大小上限（MB）。超出则在路由层返回 400，不进入 service。
MAX_FILE_SIZE_MB = 4.0


@router.post("/", response_model=TryOnResponse)
async def try_on(
    request: Request,
    person_image: UploadFile = File(..., description="Full-body photo of the person"),
    product_image_url: str = Form(..., description="Garment image URL from recommender"),
    product_name: str = Form("", description="Product name (optional)"),
    brand: str = Form("", description="Brand (optional)"),
    label: str = Form("", description="Category/label (optional)"),
    description: str = Form("", description="Product description (optional)"),
    product_id: int | None = Form(None, description="DB product id (optional, for history)"),
    user: dict | None = Depends(get_optional_user),
):
    """
    生成虚拟试穿图。

    将用户上传的全身照与推荐结果中的服饰图合成，返回试穿效果图（URL 或 base64）。

    - **person_image**: 用户全身照（PNG/JPEG/WebP，最大 4MB）
    - **product_image_url**: 来自 `/recommend` 返回的 `image_url`
    - **product_name / brand / label / description**: 可选商品上下文，帮助模型理解服装特征
    """
    # 先校验图片格式，非法类型早返回，不消耗后端资源
    if not person_image.content_type or person_image.content_type.lower() not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # 预读 body 检查文件大小；读完后需 seek(0) 才能让 service 层再次读取
    content = await person_image.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Max size: {MAX_FILE_SIZE_MB}MB",
        )

    await person_image.seek(0)

    result = await run_try_on(
        person_image=person_image.file,
        person_filename=person_image.filename or "image.png",
        product_image_url=product_image_url.strip(),
        product_name=product_name.strip() or "",
        brand=brand.strip() or "",
        label=label.strip() or "",
        description=description.strip() or "",
    )

    await _persist_tryon(
        request, user, content, product_id, product_image_url.strip(), result
    )

    return result
