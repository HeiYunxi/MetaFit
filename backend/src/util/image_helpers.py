"""
图片处理工具函数。

当前主要服务于试穿和图生 3D 两条链路，负责：
- 下载图片并转成 base64
- 识别 MIME 类型
- 在上传到模型前做统一压缩
- 从模型响应中提取图片字节
"""
import asyncio
import base64
import binascii
import httpx
from typing import List, Optional, Tuple



# 完整模拟 Chrome 的请求头，和 cstImg/image_utils.py 保持一致。
# 部分 CDN（如 farfetch）需要 sec-fetch-* 等浏览器特征头才会放行。
_BROWSER_IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "image",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site",
    "Referer": "https://www.farfetch.com/",
    "Connection": "keep-alive",
}


async def download_image_to_base64_async(image_url: str, compress: bool = False, max_size_mb: float = 0.5):
    """
    从URL下载图片并转换为base64编码（异步版本）

    Args:
        image_url: 图片URL
        compress: 是否压缩图片（如果超过大小限制）
        max_size_mb: 最大大小（MB），默认0.5MB（500KB），仅在compress=True时生效

    Returns:
        (base64_string, mime_type) 或 (None, None) 如果失败
    """
    try:
        async with httpx.AsyncClient(timeout=30, headers=_BROWSER_IMAGE_HEADERS) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
        
        # 检测图片类型
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        if 'png' in content_type.lower():
            mime_type = 'image/png'
        elif 'jpeg' in content_type.lower() or 'jpg' in content_type.lower():
            mime_type = 'image/jpeg'
        elif 'webp' in content_type.lower():
            mime_type = 'image/webp'
        else:
            mime_type = 'image/jpeg'  # 默认
        
        image_bytes = resp.content
        
        # 如果需要压缩且图片超过大小限制
        if compress:
            image_bytes, mime_type = prepare_image_for_model_upload(
                image_bytes,
                mime_type=mime_type,
                max_size_mb=max_size_mb,
            )
        
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return image_b64, mime_type
    except Exception as e:
        print(f"[ERROR] 下载图片失败: {e}")
        return None, None


async def download_images_concurrent_async(image_urls: List[str], compress: bool = False, max_size_mb: float = 0.5) -> List[Tuple[Optional[str], Optional[str]]]:
    """
    并发下载多张图片并转换为base64编码（异步版本）
    
    Args:
        image_urls: 图片URL列表
        compress: 是否压缩图片（如果超过大小限制）
        max_size_mb: 最大大小（MB），默认0.5MB（500KB），仅在compress=True时生效
    
    Returns:
        列表，每个元素为 (base64_string, mime_type) 或 (None, None) 如果失败
    """
    async def download_one(url):
        return await download_image_to_base64_async(url, compress=compress, max_size_mb=max_size_mb)
    
    # 并发执行所有下载任务
    results = await asyncio.gather(*[download_one(url) for url in image_urls], return_exceptions=True)
    
    # 处理异常情况
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"[ERROR] 并发下载图片失败 (索引 {i}): {result}")
            processed_results.append((None, None))
        else:
            processed_results.append(result)
    
    return processed_results


def normalize_image_mime_type(mime_type: Optional[str], image_bytes: Optional[bytes] = None) -> str:
    """
    规范化图片 MIME 类型；如果未提供，则尝试从图片字节推断。
    """
    normalized = (mime_type or "").strip().lower()
    if normalized == "image/jpg":
        return "image/jpeg"
    if normalized in {"image/png", "image/jpeg", "image/webp"}:
        return normalized

    if image_bytes:
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            return "image/webp"

    return "image/jpeg"


def prepare_image_for_model_upload(
    image_bytes: bytes,
    mime_type: Optional[str] = None,
    max_size_mb: float = 0.5,
) -> Tuple[bytes, str]:
    """
    在图片上传到模型前统一做 MIME 规范化和体积压缩。

    这样调用方不需要关心图片原本来自上传文件、URL 下载，还是其他中间流程。
    """
    resolved_mime_type = normalize_image_mime_type(mime_type, image_bytes)
    return compress_image_if_needed(image_bytes, resolved_mime_type, max_size_mb=max_size_mb)


def compress_base64_image_for_model_upload(
    image_base64: str,
    max_size_mb: float = 0.5,
) -> Tuple[str, str]:
    """
    压缩 base64/data URI 图片，并尽量保持调用方原有的编码形式。
    """
    image_bytes, mime_type, has_data_uri = decode_base64_image(image_base64)
    compressed_bytes, compressed_mime = prepare_image_for_model_upload(
        image_bytes,
        mime_type=mime_type,
        max_size_mb=max_size_mb,
    )
    encoded = base64.b64encode(compressed_bytes).decode("utf-8")

    if has_data_uri:
        return f"data:{compressed_mime};base64,{encoded}", compressed_mime
    return encoded, compressed_mime


def decode_base64_image(image_base64: str) -> Tuple[bytes, str, bool]:
    """
    解析 base64/data URI 图片，返回图片字节、MIME 类型和是否原本带 data URI 前缀。

    有些上游返回的是 `data:image/...;base64,...`，有些只返回纯 base64 字符串，
    这里统一兼容两种格式。
    """
    payload = (image_base64 or "").strip()
    if not payload:
        raise ValueError("Image base64 is empty")

    has_data_uri = payload.startswith("data:")
    mime_type: Optional[str] = None
    encoded = payload

    if has_data_uri:
        header, separator, encoded = payload.partition(",")
        if not separator:
            raise ValueError("Invalid data URI image")
        if ";" in header:
            mime_type = header[5:].split(";", 1)[0]

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError(f"Invalid base64 image: {e}") from e

    return image_bytes, normalize_image_mime_type(mime_type, image_bytes), has_data_uri


def extract_image_from_google_response(result: dict) -> Optional[bytes]:
    """
    从Google原生API响应中提取base64图片数据
    
    Args:
        result: Google API响应字典
    
    Returns:
        图片字节数据，如果失败则返回None
    """
    try:
        # Google原生格式: result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        if "candidates" not in result or not result["candidates"]:
            print("[ERROR] 响应中没有candidates字段")
            return None
        
        candidate = result["candidates"][0]
        if "content" not in candidate:
            print("[ERROR] candidate中没有content字段")
            return None
        
        content = candidate["content"]
        if "parts" not in content or not content["parts"]:
            print("[ERROR] content中没有parts字段")
            return None
        
        parts = content["parts"]
        for part in parts:
            # 支持两种格式：inlineData 和 inline_data
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and "data" in inline_data:
                image_data = inline_data["data"]
                print("[INFO] 成功提取到base64图片数据")
                return base64.b64decode(image_data)
        
        print("[ERROR] 未找到inlineData字段")
        return None
        
    except Exception as e:
        print(f"[ERROR] 提取图片失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def compress_image_if_needed(image_bytes: bytes, mime_type: str, max_size_mb: float = 0.5) -> Tuple[bytes, str]:
    """
    如果图片超过指定大小（默认 500KB），则循环压缩直到满足要求。
    
    Args:
        image_bytes: 图片字节数据
        mime_type: 图片MIME类型
        max_size_mb: 最大大小（MB），默认0.5MB（500KB）
    
    Returns:
        (compressed_bytes, mime_type): 压缩后的图片字节和MIME类型
    """
    try:
        import io
        from PIL import Image
    except ImportError:
        print(f"[WARNING] PIL/Pillow 未安装，无法压缩图片，使用原始图片")
        return image_bytes, mime_type
    
    max_size_bytes = max_size_mb * 1024 * 1024  # 转换为字节
    
    # 如果图片大小未超过限制，直接返回
    if len(image_bytes) <= max_size_bytes:
        return image_bytes, mime_type
    
    try:
        # 打开图片并在内存里逐轮缩放；优先保留清晰度，再逐步降低体积。
        img = Image.open(io.BytesIO(image_bytes))
        original_size = img.size
        current_bytes = image_bytes
        current_img = img
        current_mime = mime_type
        
        # 透明 PNG 尽量继续保留 PNG，其他图片默认转成 JPEG 以获得更好的压缩比。
        output_format = "JPEG"
        output_mime = "image/jpeg"
        if mime_type == "image/png":
            # 检查是否有透明通道
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                output_format = "PNG"
                output_mime = "image/png"
        
        max_iterations = 10  # 最多压缩10次，防止无限循环
        min_dimension = 256  # 最小尺寸限制
        
        for iteration in range(max_iterations):
            current_size_mb = len(current_bytes) / (1024 * 1024)
            
            # 如果已经满足大小要求，退出循环
            if len(current_bytes) <= max_size_bytes:
                if iteration > 0:
                    print(f"[INFO] 经过 {iteration} 次压缩，图片大小已满足要求: {current_size_mb:.2f}MB")
                break
            
            print(f"[INFO] 第 {iteration + 1} 次压缩：图片大小 {current_size_mb:.2f}MB 超过 {max_size_mb}MB，继续压缩...")
            
            # 目标预留 20% 安全余量，减少反复试探次数。
            target_size_bytes = max_size_bytes * 0.8
            compression_ratio = (target_size_bytes / len(current_bytes)) ** 0.5
            
            # 计算新尺寸（保持宽高比）
            current_size = current_img.size
            new_width = int(current_size[0] * compression_ratio)
            new_height = int(current_size[1] * compression_ratio)
            
            # 确保不小于最小尺寸
            if new_width < min_dimension or new_height < min_dimension:
                if new_width < new_height:
                    new_width = min_dimension
                    new_height = int(min_dimension * (current_size[1] / current_size[0]))
                else:
                    new_height = min_dimension
                    new_width = int(min_dimension * (current_size[0] / current_size[1]))
            
            # 调整尺寸
            current_img = current_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为RGB模式（如果不是JPEG格式且需要转换）
            if output_format == "JPEG" and current_img.mode != "RGB":
                if current_img.mode == "RGBA":
                    # 创建白色背景
                    background = Image.new("RGB", current_img.size, (255, 255, 255))
                    background.paste(current_img, mask=current_img.split()[-1])
                    current_img = background
                else:
                    current_img = current_img.convert("RGB")
            
            # 保存到内存
            output_buffer = io.BytesIO()
            save_kwargs = {"format": output_format}
            if output_format == "JPEG":
                save_kwargs["quality"] = 85  # JPEG质量
            
            current_img.save(output_buffer, **save_kwargs)
            current_bytes = output_buffer.getvalue()
            
            # 如果尺寸已经很小但仍然超过限制，降低质量
            if len(current_bytes) > max_size_bytes and output_format == "JPEG":
                for quality in [75, 65, 55, 45]:
                    output_buffer = io.BytesIO()
                    current_img.save(output_buffer, format="JPEG", quality=quality)
                    current_bytes = output_buffer.getvalue()
                    if len(current_bytes) <= max_size_bytes:
                        break
        
        final_size_mb = len(current_bytes) / (1024 * 1024)
        print(f"[INFO] 压缩完成：原始大小 {len(image_bytes) / (1024 * 1024):.2f}MB -> 最终大小 {final_size_mb:.2f}MB")
        
        return current_bytes, output_mime
        
    except Exception as e:
        print(f"[ERROR] 压缩图片失败: {e}")
        return image_bytes, mime_type
