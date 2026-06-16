"""
图片基础工具函数（下载、格式转换、校验）。

这里只放轻量的无状态工具；涉及压缩/MIME 识别的复杂逻辑统一放在
src/util/image_helpers.py，service 层按需调用。
"""

import base64
import tempfile
from pathlib import Path
from typing import BinaryIO

import requests
from loguru import logger

# 完整模拟 Chrome 的请求头。部分商品图 CDN（如 farfetch）有反爬机制，
# 只带简单 UA + Referer 会被 403；补齐 sec-fetch-* / sec-ch-ua / Accept-Language
# 等浏览器特征头后即可正常下载。Referer 指向商品站主域而非图片 URL 本身。
BROWSER_IMAGE_HEADERS = {
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


def download_image(url: str, timeout: int = 30) -> bytes:
    """从 URL 下载图片并返回原始字节。"""
    response = requests.get(url, headers=BROWSER_IMAGE_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.content


def image_to_base64(data: bytes, mime_type: str = "image/png") -> str:
    """把图片字节转成 data URI 格式的 base64 字符串（含 MIME 前缀）。"""
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def bytes_to_base64(data: bytes) -> str:
    """把原始字节转成纯 base64 字符串（不含 data URI 前缀）。"""
    return base64.b64encode(data).decode("utf-8")


def save_temp_image(data: bytes, suffix: str = ".png") -> Path:
    """把图片字节写入临时文件并返回路径（调用方负责清理）。"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with open(fd, "wb") as f:
            f.write(data)
        return Path(path)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise


def read_upload_to_bytes(upload_file: BinaryIO) -> bytes:
    """从上传文件对象中读取全部字节。"""
    return upload_file.read()


def get_image_mime_from_filename(filename: str) -> str:
    """根据文件名后缀推断 MIME 类型，未知格式默认 image/png。"""
    ext = (Path(filename).suffix or "").lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return mime_map.get(ext, "image/png")


def validate_image_size(data: bytes, max_mb: float = 4.0) -> None:
    """校验图片大小，超过上限则抛出 ValueError。"""
    size_mb = len(data) / (1024 * 1024)
    if size_mb > max_mb:
        raise ValueError(f"Image size {size_mb:.2f}MB exceeds limit {max_mb}MB")
