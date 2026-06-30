"""Client for LaoZhang Nano Banana 图改图 API (gemini-2.5-flash-image).

Ref: https://docs.laozhang.ai/api-capabilities/nano-banana-image-edit
"""

import re
from typing import Any

from openai import OpenAI
from loguru import logger

from src.config import settings


# 默认提示词只描述试穿任务本身，业务侧额外商品信息会在 service 层拼到 prompt 里。
DEFAULT_TRYON_PROMPT = (
    "The first image is a full-body photo of a person. "
    "The second image is a garment/product photo. "
    "Generate a realistic virtual try-on image: dress the person in the garment from the second image. "
    "Keep the person's face, identity, pose, and body proportions unchanged. "
    "Preserve the garment's color, style, and fabric details. "
    "Output a natural, high-quality try-on result."
)

DEFAULT_TRYON_PROMPT_ZH = (
    "第一张图是人物全身照，第二张图是服装商品图。"
    "请生成一张真实的虚拟试穿图：将第二张图中的服装穿在第一张图的人物身上。"
    "保持人物的面部、身份、姿势和身材不变。"
    "保留服装的颜色、款式和面料细节。"
    "输出自然、高质量的试穿效果图。"
)


# 用于把任意姿势的全身照标准化成 T-pose / A-pose，给 Tripo3D 自动绑骨做预处理。
DEFAULT_TPOSE_PROMPT = (
    "Redraw the person in this image standing in a neutral T-pose: "
    "feet shoulder-width apart, both arms straight out to the sides parallel to the ground, "
    "facing the camera directly, looking forward. "
    "Keep the person's face, identity, body proportions, clothing color and style unchanged. "
    "Use a clean plain background. The character must be visible full-body, head to toe, centered in the frame. "
    "Output a photorealistic image with no text, no watermark, no extra people."
)

DEFAULT_TPOSE_PROMPT_ZH = (
    "请把图中的人物重画为标准 T-pose 站姿：双脚与肩同宽站立，"
    "双臂平举水平张开与地面平行，正面朝向镜头，目视前方。"
    "保留人物的面部、身份、身材比例、服装颜色和款式不变。"
    "背景使用干净的纯色。人物必须为全身可见（从头到脚），居中构图。"
    "输出真实照片质感，画面中不要有任何文字、水印或其他人。"
)


def _extract_base64_from_content(text: str) -> str | None:
    """Extract base64 image from Nano Banana API response.

    Nano Banana returns Base64 in content, formats:
    - data:image/png;base64,XXXX
    - raw base64 string (long)
    """
    # 先匹配标准 data URI；如果服务端只回原始 base64，再走下面的兜底分支。
    match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", text)
    if match:
        return match.group(1)
    # Fallback: long base64-like string
    match = re.search(r"([A-Za-z0-9+/=]{200,})", text)
    if match:
        return match.group(1)
    return None


class LaoZhangImageClient:
    """Client for LaoZhang Nano Banana 图改图 API (gemini-2.5-flash-image).

    Returns Base64 image data, not URL. $0.025/request.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.LAOZHANG_IMAGE_API_KEY.get_secret_value()
        self.base_url = base_url or settings.LAOZHANG_IMAGE_BASE_URL
        self.model = model or settings.LAOZHANG_IMAGE_MODEL

    def _get_client(self) -> OpenAI:
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def virtual_try_on(
        self,
        person_image_base64: str,
        garment_image_base64: str,
        prompt: str | None = None,
        use_chinese_prompt: bool = False,
    ) -> dict[str, Any]:
        """
        Call LaoZhang Nano Banana 图改图 API for virtual try-on.

        Args:
            person_image_base64: Base64 data URL of person full-body photo
            garment_image_base64: Base64 data URL of garment product image
            prompt: Optional custom prompt
            use_chinese_prompt: When prompt is None, use DEFAULT_TRYON_PROMPT_ZH if True,
                else DEFAULT_TRYON_PROMPT (English). Ignored when prompt is provided.

        Returns:
            dict with keys: success, tryon_image_url, tryon_image_base64, message
            Nano Banana returns Base64; tryon_image_base64 is set, tryon_image_url may be None.
        """
        prompt = prompt or (DEFAULT_TRYON_PROMPT_ZH if use_chinese_prompt else DEFAULT_TRYON_PROMPT)

        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": person_image_base64}},
            {"type": "image_url", "image_url": {"url": garment_image_base64}},
        ]

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content}],
                stream=False,
            )
            text = response.choices[0].message.content or ""

            # Nano Banana 常把图片直接塞进文本内容，因此需要先从 content 里抠 base64。
            base64_data = _extract_base64_from_content(text)
            if base64_data:
                return {
                    "success": True,
                    "tryon_image_url": None,
                    "tryon_image_base64": base64_data,
                    "message": "Virtual try-on generated successfully.",
                }

            # Fallback: check for image URL (some models may return URL)
            url_match = re.search(r"!\[.*?\]\((https?://[^)]+)\)", text)
            if url_match:
                return {
                    "success": True,
                    "tryon_image_url": url_match.group(1),
                    "tryon_image_base64": None,
                    "message": "Virtual try-on generated successfully.",
                }
            url_match = re.search(r"(https?://[^\s\)]+\.(?:png|jpg|jpeg|webp))", text, re.IGNORECASE)
            if url_match:
                return {
                    "success": True,
                    "tryon_image_url": url_match.group(1).rstrip(".,)"),
                    "tryon_image_base64": None,
                    "message": "Virtual try-on generated successfully.",
                }

            logger.warning("No image data found in API response. Raw content: %s", text[:500])
            return {
                "success": False,
                "tryon_image_url": None,
                "tryon_image_base64": None,
                "message": f"No image in response. Content: {text[:200]}",
            }

        except Exception as e:
            logger.exception("LaoZhang try-on API error: %s", e)
            return {
                "success": False,
                "tryon_image_url": None,
                "tryon_image_base64": None,
                "message": str(e),
            }

    def convert_to_tpose(
        self,
        person_image_base64: str,
        prompt: str | None = None,
        use_chinese_prompt: bool = False,
    ) -> dict[str, Any]:
        """
        把任意姿势的全身照重绘为标准 T-pose，给 Tripo3D 自动绑骨做预处理。

        Returns:
            dict with keys: success, image_base64 (data:image/...;base64,...), message
        """
        prompt = prompt or (DEFAULT_TPOSE_PROMPT_ZH if use_chinese_prompt else DEFAULT_TPOSE_PROMPT)

        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": person_image_base64}},
        ]

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content}],
                stream=False,
            )
            text = response.choices[0].message.content or ""

            base64_data = _extract_base64_from_content(text)
            if base64_data:
                return {
                    "success": True,
                    "image_base64": f"data:image/png;base64,{base64_data}",
                    "message": "T-pose normalization succeeded.",
                }

            logger.warning(
                "T-pose API returned no image. Raw content (first 500 chars): %s",
                text[:500],
            )
            return {
                "success": False,
                "image_base64": None,
                "message": f"No image in response. Content: {text[:200]}",
            }

        except Exception as e:  # pylint: disable=broad-except
            logger.exception("LaoZhang T-pose normalization error: %s", e)
            return {
                "success": False,
                "image_base64": None,
                "message": str(e),
            }
