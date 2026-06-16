"""
姿势归一化（pose normalization）—— 把任意全身照重绘为 T-pose。

Tripo3D 自动 rig 对输入图要求严格（T-pose / A-pose 全身正面照）。
试穿结果图多为自然站姿，在 mesh 阶段前先做图改图重摆 pose，
可显著提升 rig / animation 成功率。
"""

import asyncio
from typing import Any

from loguru import logger

from src.cstImg.image_utils import download_image, image_to_base64
from src.cstImg.laozhang_client import LaoZhangImageClient


def _as_data_uri(b64: str, mime: str = "image/png") -> str:
    """Ensure value is a data URI for LaoZhang / Tripo consumers."""
    if b64.startswith("data:"):
        return b64
    return f"data:{mime};base64,{b64}"


async def normalize_to_tpose(
    image_url: str | None = None,
    image_base64: str | None = None,
) -> dict[str, Any]:
    """
    把单张人物全身照转成 T-pose，结果返回 base64 data URI。

    Returns:
        { success, image_base64, message }
    """
    if not image_url and not image_base64:
        return {
            "success": False,
            "image_base64": None,
            "message": "Provide either image_url or image_base64.",
        }

    src_b64 = image_base64
    if src_b64:
        src_b64 = _as_data_uri(src_b64)
    else:
        try:
            raw = await asyncio.to_thread(download_image, image_url)
            src_b64 = image_to_base64(raw, mime_type="image/png")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("[pose_normalize] failed to fetch image: %s", exc)
            return {
                "success": False,
                "image_base64": None,
                "message": f"failed to download source image: {exc}",
            }

    client = LaoZhangImageClient()
    result = await asyncio.to_thread(client.convert_to_tpose, src_b64)
    return result
