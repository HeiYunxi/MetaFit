"""Serve downloaded 3D model files for VR/WebXR clients."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import settings

router = APIRouter(prefix="/download", tags=["Download"])

# GLB 文件按文件 mtime 倒序返回，新生成的模型排在最前面。
SUPPORTED_MODEL_SUFFIXES = (".glb", ".gltf")


class ModelInfo(BaseModel):
    """单个模型文件元数据，给 WebXR 前端做列表展示用。"""

    filename: str
    url: str
    size_bytes: int
    modified_ts: float


class ModelListResponse(BaseModel):
    """模型列表响应。"""

    count: int
    models: list[ModelInfo]


@router.get("/", response_model=ModelListResponse)
def list_models():
    """
    列出 download/ 目录下所有可用的 3D 模型（GLB / GLTF）。

    WebXR 前端启动后可以先调一次这个接口来发现已有模型，
    然后再按需调 GET /download/{filename} 下载。

    Returns:
        ModelListResponse with sorted models (newest first).
    """
    base = Path(settings.DOWNLOAD_DIR)
    if not base.exists():
        return ModelListResponse(count=0, models=[])

    items: list[ModelInfo] = []
    for p in base.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_MODEL_SUFFIXES:
            continue
        stat = p.stat()
        items.append(
            ModelInfo(
                filename=p.name,
                url=f"/download/{p.name}",
                size_bytes=stat.st_size,
                modified_ts=stat.st_mtime,
            )
        )
    items.sort(key=lambda m: m.modified_ts, reverse=True)
    return ModelListResponse(count=len(items), models=items)


@router.get("/{filename}")
def serve_model(filename: str):
    """
    Serve GLB/GLTF model files from download/ directory.
    Used by WebXR clients to load 3D models.

    Example: GET /download/tryon_model_20250116_123456.glb

    Headers:
        - Cache-Control: public, max-age=86400 — 浏览器可缓存一天
        - Accept-Ranges: bytes — 允许大模型按 Range 分段下载
    """
    # 先拒绝明显的路径穿越输入，避免把任意系统文件暴露出去。
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid filename")
    base = Path(settings.DOWNLOAD_DIR).resolve()
    requested = (base / filename).resolve()
    # resolve 后再次校验前缀，防止符号链接或变体路径绕过下载目录限制。
    if not str(requested).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    # FileResponse 默认已经支持 Range 请求，这里补上 Cache-Control 让浏览器
    # 拿到稳定的缓存策略。
    return FileResponse(
        requested,
        media_type="model/gltf-binary",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
        },
    )
