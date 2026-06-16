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


def build_tryon_prompt(
    product_name: str = "",
    brand: str = "",
    label: str = "",
    description: str = "",
) -> str:
    """Build an enhanced prompt with product context."""
    parts = []
    if product_name:
        parts.append(f"Garment: {product_name}")
    if brand:
        parts.append(f"Brand: {brand}")
    if label:
        parts.append(f"Category: {label}")
    if description:
        parts.append(f"Details: {description[:200]}")

    if not parts:
        return ""

    return (
        "The first image is a full-body photo of a person. "
        "The second image is a garment/product photo. "
        f"Product context: {'; '.join(parts)}. "
        "Generate a realistic virtual try-on: dress the person in the garment. "
        "Keep face, pose, body unchanged. Preserve garment color and style. "
        "Output natural, high-quality try-on result."
    )


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
        result = client.virtual_try_on(
            person_image_base64=person_b64,
            garment_image_base64=garment_b64,
            prompt=custom_prompt if custom_prompt else None,
            use_chinese_prompt=True,
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
