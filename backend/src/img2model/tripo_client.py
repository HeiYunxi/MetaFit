"""
Tripo3D 图生 3D 客户端封装。

提供三段能力，都返回 `{success, model_path, model_url, task_id, error}` 字典：
- image_to_3d:        图生静态 mesh（旧接口，向后兼容）
- rig_3d:             给已有 mesh 任务自动绑骨，可导出 GLB / FBX
- retarget_animation_3d: 给已绑骨的任务追加一段预制动画

调用方按需串联，例如：
    mesh   = await image_to_3d(image_url=...)
    rigged = await rig_3d(mesh["task_id"], out_format="glb")
    anim   = await retarget_animation_3d(rigged["task_id"], animation="idle")
"""

import tempfile
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from tripo3d import TripoClient
from tripo3d import TaskStatus
from tripo3d.models import Animation, RigSpec, RigType

from src.config import settings
from src.util.image_helpers import compress_base64_image_for_model_upload


MODEL_UPLOAD_MAX_SIZE_MB = 0.5

OutFormat = Literal["glb", "fbx"]

# Tripo Animation 枚举里只有人形 + 部分四足/水生预设，
# 我们对外只暴露常见的人形预设，避免误选 quadruped 等不匹配的动画。
_HUMANOID_ANIMATIONS: dict[str, Animation] = {
    "idle":  Animation.IDLE,
    "walk":  Animation.WALK,
    "run":   Animation.RUN,
    "dive":  Animation.DIVE,
    "climb": Animation.CLIMB,
    "jump":  Animation.JUMP,
    "slash": Animation.SLASH,
    "shoot": Animation.SHOOT,
    "hurt":  Animation.HURT,
    "fall":  Animation.FALL,
    "turn":  Animation.TURN,
}

_RIG_SPEC_MAP: dict[str, RigSpec] = {
    "mixamo": RigSpec.MIXAMO,  # Humanoid Avatar 友好
    "tripo":  RigSpec.TRIPO,
}


def _format_task_error(task: Any) -> str:
    """
    把失败任务的可用诊断信息拼成一行，避免上层只拿到 'TaskStatus.FAILED'。

    Tripo 的 Task 在失败时可能给出 error_msg / error_code，也可能两者都为空
    （例如 retarget 阶段骨架不兼容时）。这里尽量把所有线索都带出来。
    """
    parts: list[str] = []
    msg = getattr(task, "error_msg", None)
    code = getattr(task, "error_code", None)
    status = getattr(task, "status", None)
    if msg:
        parts.append(str(msg))
    if code is not None:
        parts.append(f"error_code={code}")
    status_val = getattr(status, "value", status)
    parts.append(f"status={status_val}")
    return " | ".join(parts)


def _get_image_input(image_url: str | None, image_base64: str | None) -> str:
    """
    解析图像输入。

    Tripo SDK 可以直接吃 URL，但 base64 需要先落到临时文件再上传。
    这里也顺手做了上传前压缩，避免 try-on 结果图过大。
    """
    if image_url and image_url.strip().startswith(("http://", "https://")):
        return image_url.strip()
    if image_base64:
        b64, mime_type = compress_base64_image_for_model_upload(
            image_base64,
            max_size_mb=MODEL_UPLOAD_MAX_SIZE_MB,
        )
        data = b64.split(",", 1)[1] if b64.startswith("data:") else b64
        import base64
        try:
            raw = base64.b64decode(data)
        except Exception as e:
            raise ValueError(f"Invalid base64 image: {e}") from e
        suffix = ".png"
        if mime_type == "image/jpeg":
            suffix = ".jpg"
        elif mime_type == "image/webp":
            suffix = ".webp"
        # SDK 期望的是文件路径，因此把 base64 临时写盘并在 finally 中回收。
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(raw)
            return f.name
    raise ValueError("Provide either image_url (http/https) or image_base64")


async def image_to_3d(
    image_url: str | None = None,
    image_base64: str | None = None,
    texture: bool = True,
    orientation: str = "default",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    调用 Tripo3D 官方 SDK 执行图生 3D。

    Args:
        image_url: HTTP(S) URL of the image
        image_base64: Base64 or data URI of the image (saved to temp file)
        texture: Whether to generate texture
        orientation: "default" | "align_image"
        output_dir: Directory to save downloaded models (optional)

    Returns:
        dict with success, task_id, model_path, model_url, downloaded_files, error
    """
    temp_path: str | None = None
    try:
        image_input = _get_image_input(image_url, image_base64)
        if not image_input.startswith(("http://", "https://")):
            temp_path = image_input

        api_key = settings.TRIPO_API_KEY.get_secret_value()
        if not api_key:
            raise ValueError("Set TRIPO_API_KEY in .env (from platform.tripo3d.ai)")

        out_dir = str(output_dir) if output_dir else str(settings.DOWNLOAD_DIR)
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        async with TripoClient(api_key=api_key) as client:
            task_id = await client.image_to_model(
                image=image_input,
                texture=texture,
                orientation=orientation,
            )
            logger.info("Tripo3D task submitted: %s", task_id)

            task = await client.wait_for_task(task_id, verbose=True, timeout=300)

            if task.status != TaskStatus.SUCCESS:
                return {
                    "success": False,
                    "task_id": task_id,
                    "model_path": None,
                    "model_url": getattr(task.output, "model", None) if task.output else None,
                    "downloaded_files": {},
                    "error": _format_task_error(task),
                }

            downloaded = await client.download_task_models(task, out_dir)
            model_url = getattr(task.output, "model", None) if task.output else None
            pbr_url = getattr(task.output, "pbr_model", None) if task.output else None
            # 下载结果可能包含多个文件，优先返回主模型，其次退回 PBR 或第一个可用文件。
            primary_path = downloaded.get("model") or downloaded.get("pbr_model") or (
                list(downloaded.values())[0] if downloaded else None
            )

            return {
                "success": True,
                "task_id": task_id,
                "model_path": primary_path,
                "model_url": model_url or pbr_url,
                "downloaded_files": downloaded,
                "error": None,
            }
    except ValueError as e:
        logger.warning("Tripo3D input error: %s", e)
        return {
            "success": False,
            "task_id": None,
            "model_path": None,
            "model_url": None,
            "downloaded_files": {},
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Tripo3D API error: %s", e)
        return {
            "success": False,
            "task_id": None,
            "model_path": None,
            "model_url": None,
            "downloaded_files": {},
            "error": str(e),
        }
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                # base64 只用于一次性提交，不保留在本地，避免堆积临时文件。
                Path(temp_path).unlink()
            except OSError:
                pass


def _pick_primary_file(downloaded: dict[str, str], out_format: str) -> str | None:
    """
    Tripo SDK 下载后的 dict 可能包含 model / pbr_model / animated_model 等键，
    这里按 "目标格式优先"挑出主文件路径。
    """
    if not downloaded:
        return None
    suffix = f".{out_format.lower()}"
    for path in downloaded.values():
        if path and str(path).lower().endswith(suffix):
            return path
    # 兜底：找不到目标格式时返回任意一个文件，避免上层拿不到结果。
    return next(iter(downloaded.values()), None)


async def _run_dependent_task(
    submit_fn,
    output_dir: str | Path | None,
    *,
    task_label: str,
) -> dict[str, Any]:
    """
    通用包装：跑一个依赖于"上一个 Tripo 任务"的子任务（rig / animation）。

    submit_fn 接收已经连接好的 client，返回新建任务的 task_id；
    本函数负责等待 + 下载 + 异常包装，让上层 service 拿到统一字典。
    """
    try:
        api_key = settings.TRIPO_API_KEY.get_secret_value()
        if not api_key:
            raise ValueError("Set TRIPO_API_KEY in .env (from platform.tripo3d.ai)")

        out_dir = str(output_dir) if output_dir else str(settings.DOWNLOAD_DIR)
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        async with TripoClient(api_key=api_key) as client:
            task_id = await submit_fn(client)
            logger.info("Tripo3D %s task submitted: %s", task_label, task_id)
            task = await client.wait_for_task(task_id, verbose=True, timeout=600)
            if task.status != TaskStatus.SUCCESS:
                error = _format_task_error(task)
                logger.warning("Tripo3D %s task %s failed: %s", task_label, task_id, error)
                return {
                    "success": False,
                    "task_id": task_id,
                    "model_path": None,
                    "model_url": getattr(task.output, "model", None) if task.output else None,
                    "downloaded_files": {},
                    "error": error,
                }
            downloaded = await client.download_task_models(task, out_dir)
            model_url = getattr(task.output, "model", None) if task.output else None
            return {
                "success": True,
                "task_id": task_id,
                "downloaded_files": downloaded,
                "model_url": model_url,
                "error": None,
            }
    except ValueError as e:
        logger.warning("Tripo3D %s input error: %s", task_label, e)
        return {
            "success": False, "task_id": None, "model_path": None,
            "model_url": None, "downloaded_files": {}, "error": str(e),
        }
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("Tripo3D %s API error: %s", task_label, e)
        return {
            "success": False, "task_id": None, "model_path": None,
            "model_url": None, "downloaded_files": {}, "error": str(e),
        }


async def check_riggable_3d(mesh_task_id: str) -> dict[str, Any]:
    """
    检查一个 mesh 任务能否被绑骨。

    Returns:
        {"success": bool, "riggable": bool, "error": Optional[str]}
        失败时 riggable=False；上层可以据此提前 short-circuit 避免无效 rig 任务。
    """
    try:
        api_key = settings.TRIPO_API_KEY.get_secret_value()
        if not api_key:
            raise ValueError("Set TRIPO_API_KEY in .env")

        async with TripoClient(api_key=api_key) as client:
            task_id = await client.check_riggable(mesh_task_id)
            task = await client.wait_for_task(task_id, verbose=False, timeout=120)
            if task.status != TaskStatus.SUCCESS:
                return {
                    "success": False,
                    "riggable": False,
                    "error": _format_task_error(task),
                }
            # task.output.riggable 明确给出能否绑骨；早期 SDK 可能不返回该字段，
            # 此时回退为宽容策略（成功即视为可绑骨）。
            riggable_flag = getattr(task.output, "riggable", None) if task.output else None
            rig_type = getattr(task.output, "rig_type", None) if task.output else None
            riggable = True if riggable_flag is None else bool(riggable_flag)
            return {
                "success": True,
                "riggable": riggable,
                "rig_type": rig_type,
                "error": None if riggable else "Model is not riggable (check_riggable=false).",
            }
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("Tripo3D check_riggable error: %s", e)
        return {"success": False, "riggable": False, "error": str(e)}


async def rig_3d(
    mesh_task_id: str,
    out_format: OutFormat = "glb",
    spec: str = "mixamo",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    给已有 mesh 任务做自动绑骨，输出指定格式（GLB 或 FBX）。

    Args:
        mesh_task_id: image_to_3d 返回的 Tripo task_id
        out_format:   "glb" 或 "fbx"
        spec:         "mixamo"（Humanoid 友好）或 "tripo"
        output_dir:   下载目录，默认 settings.DOWNLOAD_DIR

    Returns:
        与 image_to_3d 一致的字典，model_path 指向下载的 GLB/FBX。
    """
    rig_spec = _RIG_SPEC_MAP.get(spec.lower(), RigSpec.MIXAMO)

    async def _submit(client):
        return await client.rig_model(
            original_model_task_id=mesh_task_id,
            out_format=out_format,
            rig_type=RigType.BIPED,
            spec=rig_spec,
        )

    result = await _run_dependent_task(_submit, output_dir, task_label="rig")
    if result["success"]:
        result["model_path"] = _pick_primary_file(result["downloaded_files"], out_format)
    return result


async def retarget_animation_3d(
    rig_task_id: str,
    animation: str = "idle",
    out_format: OutFormat = "glb",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    给已绑骨的任务追加一段预制动画，输出 GLB / FBX。

    Args:
        rig_task_id: rig_3d 返回的 Tripo task_id
        animation:   动画名（与 schemas.AnimationPreset 对齐），如 "idle" / "walk"
        out_format:  "glb" 或 "fbx"
        output_dir:  下载目录

    Returns:
        与 rig_3d 一致的字典；export_with_geometry=True 让 GLB/FBX 自包含完整几何，
        WebXR 前端加载即可播放。
    """
    anim_enum = _HUMANOID_ANIMATIONS.get(animation.lower())
    if anim_enum is None:
        return {
            "success": False, "task_id": None, "model_path": None, "model_url": None,
            "downloaded_files": {}, "error": f"Unsupported animation preset: {animation}",
        }

    async def _submit(client):
        return await client.retarget_animation(
            original_model_task_id=rig_task_id,
            animation=anim_enum,
            out_format=out_format,
            bake_animation=True,
            export_with_geometry=True,  # 让导出文件自包含 mesh，加载即可播放
        )

    result = await _run_dependent_task(_submit, output_dir, task_label="animation")
    if result["success"]:
        result["model_path"] = _pick_primary_file(result["downloaded_files"], out_format)
    return result
