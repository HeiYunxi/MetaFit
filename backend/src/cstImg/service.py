"""
虚拟试穿服务编排层。

负责把用户上传的人像图和推荐结果里的服饰图整理成模型可接受的输入，
并调用 LaoZhang 的图改图接口生成试穿结果。
"""

from typing import BinaryIO

from loguru import logger

from src.cstImg.image_utils import (
    download_image,
    get_image_mime_from_filename,
    image_to_base64,
    read_upload_to_bytes,
    validate_image_size,
)
from src.cstImg.laozhang_client import LaoZhangImageClient
from src.cstImg.schemas import TryOnResponse
from src.util.image_helpers import prepare_image_for_model_upload


MODEL_UPLOAD_MAX_SIZE_MB = 0.5


def _metadata_contains_chinese(*fields: str) -> bool:
    """True if any non-empty metadata field contains CJK characters."""
    for text in fields:
        if text and any("\u4e00" <= ch <= "\u9fff" for ch in text):
            return True
    return False


def _build_tryon_prompt_en(parts: list[str]) -> str:
    return (
        "The first image is a full-body photo of a person. "
        "The second image is a garment/product photo. "
        f"Product context: {'; '.join(parts)}. "
        "Generate a realistic virtual try-on: dress the person in the garment. "
        "Keep face, pose, body unchanged. Preserve garment color and style. "
        "Output natural, high-quality try-on result."
    )


def _build_tryon_prompt_zh(parts: list[str]) -> str:
    return (
        "第一张图是人物全身照，第二张图是服装商品图。"
        f"商品信息：{'；'.join(parts)}。"
        "请生成一张真实的虚拟试穿图：将第二张图中的服装穿在第一张图的人物身上。"
        "保持人物的面部、身份、姿势和身材不变。"
        "保留服装的颜色、款式和面料细节。"
        "输出自然、高质量的试穿效果图。"
    )


def build_tryon_prompt(
    product_name: str = "",
    brand: str = "",
    label: str = "",
    description: str = "",
) -> str:
    """Build a product-aware try-on prompt in Chinese or English based on metadata language."""
    use_zh = _metadata_contains_chinese(
        product_name, brand, label, description[:200] if description else ""
    )

    parts: list[str] = []
    if product_name:
        parts.append(
            f"服装：{product_name}" if use_zh else f"Garment: {product_name}"
        )
    if brand:
        parts.append(f"品牌：{brand}" if use_zh else f"Brand: {brand}")
    if label:
        parts.append(f"品类：{label}" if use_zh else f"Category: {label}")
    if description:
        excerpt = description[:200]
        parts.append(f"详情：{excerpt}" if use_zh else f"Details: {excerpt}")

    if not parts:
        return ""

    return _build_tryon_prompt_zh(parts) if use_zh else _build_tryon_prompt_en(parts)


async def run_try_on(
    person_image: BinaryIO,
    person_filename: str,
    product_image_url: str,
    product_name: str = "",
    brand: str = "",
    label: str = "",
    description: str = "",
) -> TryOnResponse:
    """
    执行完整的试穿流程。

    Args:
        person_image: Uploaded person photo file object
        person_filename: Original filename (for MIME detection)
        product_image_url: URL of the garment image from recommender
        product_name: Optional product name for prompt
        brand: Optional brand for prompt
        label: Optional category for prompt
        description: Optional description for prompt

    Returns:
        TryOnResponse with result or error
    """
    try:
        person_bytes = read_upload_to_bytes(person_image)
        validate_image_size(person_bytes)
        # 上传给图像模型前统一压缩，避免用户原图过大导致请求失败或成本过高。
        person_bytes, person_mime = prepare_image_for_model_upload(
            person_bytes,
            mime_type=get_image_mime_from_filename(person_filename),
            max_size_mb=MODEL_UPLOAD_MAX_SIZE_MB,
        )

        garment_bytes = download_image(product_image_url)
        # 商品图同样在发送给模型前压缩，保证人物图和服饰图走同一输入约束。
        garment_bytes, garment_mime = prepare_image_for_model_upload(
            garment_bytes,
            max_size_mb=MODEL_UPLOAD_MAX_SIZE_MB,
        )

        person_b64 = image_to_base64(person_bytes, person_mime)
        garment_b64 = image_to_base64(garment_bytes, garment_mime)

        custom_prompt = build_tryon_prompt(
            product_name=product_name,
            brand=brand,
            label=label,
            description=description,
        )

        client = LaoZhangImageClient()
        # No metadata → English default; metadata present → product-aware prompt
        # in Chinese or English according to metadata language.
        result = client.virtual_try_on(
            person_image_base64=person_b64,
            garment_image_base64=garment_b64,
            prompt=custom_prompt if custom_prompt else None,
            use_chinese_prompt=False,
        )

        return TryOnResponse(
            success=result["success"],
            tryon_image_url=result.get("tryon_image_url"),
            tryon_image_base64=result.get("tryon_image_base64"),
            product_image_url=product_image_url,
            message=result.get("message", ""),
        )

    except ValueError as e:
        logger.warning("Try-on validation error: %s", e)
        return TryOnResponse(
            success=False,
            tryon_image_url=None,
            tryon_image_base64=None,
            product_image_url=product_image_url,
            message=str(e),
        )
    except Exception as e:
        logger.exception("Try-on pipeline error: %s", e)
        return TryOnResponse(
            success=False,
            tryon_image_url=None,
            tryon_image_base64=None,
            product_image_url=product_image_url,
            message=str(e),
        )
