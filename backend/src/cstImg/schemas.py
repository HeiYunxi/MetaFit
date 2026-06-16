"""
试穿接口的请求/响应数据模型。

TryOnResponse 是 /try-on 接口统一返回结构。
Nano Banana（gemini-2.5-flash-image）返回的是 base64 图片而不是 URL，
因此 tryon_image_url 与 tryon_image_base64 只会有一个有值。
"""

from pydantic import BaseModel, Field


class TryOnResponse(BaseModel):
    """虚拟试穿接口响应。"""

    success: bool = Field(..., description="是否成功生成试穿图")
    tryon_image_url: str | None = Field(
        default=None,
        description="试穿结果图 URL（部分模型返回 URL，Nano Banana 通常返回 base64）",
    )
    tryon_image_base64: str | None = Field(
        default=None,
        description="试穿结果图 base64 编码（Nano Banana 主路径）",
    )
    product_image_url: str = Field(
        ...,
        description="本次试穿使用的服饰图 URL（原样透传，方便前端对比）",
    )
    message: str = Field(
        default="",
        description="状态说明或错误信息",
    )
