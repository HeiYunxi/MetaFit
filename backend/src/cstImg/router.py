"""
虚拟试穿接口路由（POST /try-on）。

接收用户上传的全身照和推荐商品图 URL，
转发给 service 层调用 LaoZhang 图改图模型生成试穿效果图。
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.cstImg.schemas import TryOnResponse
from src.cstImg.service import run_try_on

router = APIRouter(prefix="/try-on", tags=["TryOn"])

# 允许的图片格式（用于上传前拦截非法类型）
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
# 上传大小上限（MB）。超出则在路由层返回 400，不进入 service。
MAX_FILE_SIZE_MB = 4.0


@router.post("/", response_model=TryOnResponse)
async def try_on(
    person_image: UploadFile = File(..., description="Full-body photo of the person"),
    product_image_url: str = Form(..., description="Garment image URL from recommender"),
    product_name: str = Form("", description="Product name (optional)"),
    brand: str = Form("", description="Brand (optional)"),
    label: str = Form("", description="Category/label (optional)"),
    description: str = Form("", description="Product description (optional)"),
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

    return result
