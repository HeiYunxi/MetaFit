"""
图生 3D 服务编排层。

提供两个入口：

1. `run_img2model`   —— 旧的"图 → 静态 GLB"流程，向后兼容同步路由
2. `run_full_pipeline` —— pose_normalize → mesh → rig → animation（默认各阶段只出 GLB），
   通过 progress_cb 把每个阶段的结果实时回写给上层（task_store）

`run_full_pipeline` 不是真正"原子"——任何一段失败都立刻 short-circuit，
但已经完成的产物（比如 mesh）依然保留在 download/ 中，客户端可以走部分降级。
"""

from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from loguru import logger

from src.config import settings
from src.img2model.pose_normalizer import normalize_to_tpose
from src.img2model.schemas import AnimationOptions, PoseNormalizationOptions, RigOptions
from src.img2model.tripo_client import (
    check_riggable_3d,
    image_to_3d,
    retarget_animation_3d,
    rig_3d,
)

# stage 名（与 schemas.Img2ModelStatus.stage 一致）
STAGE_POSE_NORMALIZE = "pose_normalize"
STAGE_MESH = "mesh"
STAGE_RIG = "rig"
STAGE_ANIMATION = "animation"


ProgressCallback = Callable[[dict], Awaitable[None]]


def _ensure_download_dir() -> Path:
    """确保 download/ 目录存在（首次运行时自动创建）。"""
    download_dir = Path(settings.DOWNLOAD_DIR)
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def _relativize(model_path: str | None) -> str | None:
    """把绝对路径转成相对于项目根目录的路径，统一用正斜杠。"""
    if not model_path:
        return None
    try:
        rel = Path(model_path).relative_to(settings.BASE_DIR)
    except ValueError:
        rel = Path(model_path)
    return str(rel).replace("\\", "/")


def _filename_only(rel_path: str | None) -> str | None:
    """从相对路径里只抽文件名，给 /download/{filename} 用。"""
    if not rel_path:
        return None
    return rel_path.rsplit("/", 1)[-1]


async def run_img2model(
    image_url: str | None = None,
    image_base64: str | None = None,
    filename_prefix: str = "tryon_model",
) -> dict:
    """
    旧的「图 → 静态 GLB」流程。返回值与原版兼容：
    {success, model_path, model_url, task_id, message}
    """
    if not image_url and not image_base64:
        return {
            "success": False, "model_path": None, "model_url": None,
            "task_id": None, "message": "Provide either image_url or image_base64",
        }

    download_dir = _ensure_download_dir()
    result = await image_to_3d(
        image_url=image_url,
        image_base64=image_base64,
        texture=True,
        orientation="default",
        output_dir=download_dir,
    )

    if not result.get("success") or not result.get("model_path"):
        return {
            "success": False,
            "model_path": None,
            "model_url": result.get("model_url"),
            "task_id": result.get("task_id"),
            "message": result.get("error") or "Tripo3D task did not return a model file.",
        }

    return {
        "success": True,
        "model_path": _relativize(result["model_path"]),
        "model_url": result.get("model_url"),
        "task_id": result.get("task_id"),
        "message": "3D model generated and saved successfully",
    }


async def _emit(progress_cb: Optional[ProgressCallback], **fields) -> None:
    """安全调用 progress_cb（如果没传就 no-op，避免空判断散在各处）。"""
    if progress_cb is None:
        return
    try:
        await progress_cb(fields)
    except Exception:  # pylint: disable=broad-except
        logger.exception("[img2model] progress callback raised; ignoring.")


async def _run_rig_formats(
    mesh_task_id: str,
    spec: str,
    download_dir: Path,
    *,
    also_emit_fbx: bool = False,
) -> tuple[dict, dict]:
    """
    绑骨：默认只跑 GLB（一次 animate_rig）。
    also_emit_fbx=True 时额外再跑 FBX（第二次 animate_rig，供 Editor 导入）。
    """
    glb_result = await rig_3d(mesh_task_id, out_format="glb", spec=spec, output_dir=download_dir)
    if not glb_result.get("success"):
        return glb_result, {"success": False, "error": "skipped because GLB rig failed"}

    fbx_result: dict = {"success": False, "error": "skipped (GLB-only mode)"}
    if also_emit_fbx:
        fbx_result = await rig_3d(mesh_task_id, out_format="fbx", spec=spec, output_dir=download_dir)
        if not fbx_result.get("success"):
            logger.warning("[img2model] FBX rig failed (GLB still available): %s",
                           fbx_result.get("error"))
    return glb_result, fbx_result


async def _run_animation_formats(
    rig_task_id: str,
    preset: str,
    download_dir: Path,
    *,
    also_emit_fbx: bool = False,
) -> tuple[dict, dict]:
    """动画 retarget：默认只跑 GLB；also_emit_fbx=True 时额外跑 FBX。"""
    glb_result = await retarget_animation_3d(
        rig_task_id, animation=preset, out_format="glb", output_dir=download_dir,
    )
    if not glb_result.get("success"):
        return glb_result, {"success": False, "error": "skipped because GLB anim failed"}

    fbx_result: dict = {"success": False, "error": "skipped (GLB-only mode)"}
    if also_emit_fbx:
        fbx_result = await retarget_animation_3d(
            rig_task_id, animation=preset, out_format="fbx", output_dir=download_dir,
        )
        if not fbx_result.get("success"):
            logger.warning("[img2model] FBX animation failed (GLB still available): %s",
                           fbx_result.get("error"))
    return glb_result, fbx_result


def _stage_payload(glb_result: dict, fbx_result: dict) -> dict[str, Any]:
    """整理单阶段的 GLB/FBX 文件名 + Tripo task_id，方便回写 task_store。"""
    glb_filename = _filename_only(_relativize(glb_result.get("model_path")))
    fbx_filename = _filename_only(_relativize(fbx_result.get("model_path")))
    return {
        "glb_url": f"/download/{glb_filename}" if glb_filename else None,
        "fbx_url": f"/download/{fbx_filename}" if fbx_filename else None,
        "tripo_task_id": glb_result.get("task_id"),
    }


async def run_full_pipeline(
    image_url: str | None = None,
    image_base64: str | None = None,
    filename_prefix: str = "tryon_model",
    pose_options: PoseNormalizationOptions | None = None,
    rig_options: RigOptions | None = None,
    animation_options: AnimationOptions | None = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """
    串联 (可选) pose_normalize → mesh → (可选) rig → (可选) animation。
    默认每阶段只调用一次 Tripo（GLB）；rig.also_emit_fbx / animation.also_emit_fbx 为 True 时才额外出 FBX。

    progress_cb 在每个阶段完成时被 await 一次，参数是要合并写入 task_store 的字段：

        await progress_cb({"stage": "rig", "progress": 80, "rig": {...}})

    Returns:
        dict with overall success flag + 每阶段产物的相对文件名。
    """
    pose_options = pose_options or PoseNormalizationOptions()
    rig_options = rig_options or RigOptions()
    animation_options = animation_options or AnimationOptions()
    download_dir = _ensure_download_dir()

    overall: dict[str, Any] = {
        "success": False,
        "pose_normalized": False,
        "mesh": {}, "rig": {}, "animation": {},
        "message": "",
    }

    # rig/animation 时若客户端未显式关闭，自动开启 T-pose 归一化
    do_pose = pose_options.enabled or rig_options.enabled or animation_options.enabled

    # ── Stage 0 (可选): pose normalization ───────────────────────────────────
    if do_pose:
        await _emit(progress_cb, state="running", stage=STAGE_POSE_NORMALIZE, progress=3)
        norm = await normalize_to_tpose(image_url=image_url, image_base64=image_base64)
        if norm.get("success") and norm.get("image_base64"):
            image_url = None
            image_base64 = norm["image_base64"]
            overall["pose_normalized"] = True
            await _emit(progress_cb, stage=STAGE_POSE_NORMALIZE, progress=8,
                        pose_normalized=True)
        else:
            logger.warning(
                "[img2model] pose normalization failed, falling back to original image: %s",
                norm.get("message"),
            )
            await _emit(progress_cb, stage=STAGE_POSE_NORMALIZE, progress=8,
                        pose_normalized=False,
                        error=f"pose normalize fallback: {norm.get('message')}")

    # ── Stage 1: mesh ────────────────────────────────────────────────────────
    await _emit(progress_cb, state="running", stage=STAGE_MESH, progress=10)
    mesh_result = await image_to_3d(
        image_url=image_url, image_base64=image_base64,
        texture=True, orientation="default", output_dir=download_dir,
    )
    if not mesh_result.get("success") or not mesh_result.get("model_path"):
        overall["message"] = mesh_result.get("error") or "Mesh stage failed."
        await _emit(progress_cb, state="failed", stage=STAGE_MESH, progress=100,
                    error=overall["message"])
        return overall

    mesh_filename = _filename_only(_relativize(mesh_result["model_path"]))
    mesh_payload = {
        "glb_url": f"/download/{mesh_filename}" if mesh_filename else None,
        "fbx_url": None,
        "tripo_task_id": mesh_result.get("task_id"),
    }
    overall["mesh"] = mesh_payload

    # 旧字段保留：向后兼容，客户端不用改也能拿到 mesh
    await _emit(
        progress_cb,
        stage=STAGE_MESH, progress=40,
        mesh=mesh_payload,
        model_path=_relativize(mesh_result["model_path"]),
        download_url=mesh_payload["glb_url"],
        tripo_task_id=mesh_result.get("task_id"),
    )

    # 不需要 rig 的话到这里就结束
    if not rig_options.enabled:
        overall["success"] = True
        overall["message"] = "Mesh generated (rig disabled)."
        await _emit(progress_cb, state="done", stage=STAGE_MESH, progress=100)
        return overall

    # ── Stage 2: rig（GLB + FBX 各跑一次）────────────────────────────────────
    await _emit(progress_cb, stage=STAGE_RIG, progress=45)

    riggable = await check_riggable_3d(mesh_result["task_id"])
    if not riggable.get("riggable"):
        # Tripo 的 prerigcheck 对非 T-pose / 试穿图 mesh 经常误报 false；
        # 不在这里 short-circuit，直接尝试 rig，由 rig 阶段给出真实结果。
        logger.warning(
            "[img2model] check_riggable=false (rig_type=%s); attempting rig anyway. %s",
            riggable.get("rig_type"),
            riggable.get("error") or "",
        )
    elif not riggable.get("success"):
        logger.warning(
            "[img2model] check_riggable API returned success=false (%s); attempting rig anyway.",
            riggable.get("error"),
        )

    # Tripo 内置预设动画（preset:idle 等）只兼容 Tripo 自家骨架；用 mixamo spec 绑骨后
    # 走 animate_retarget 会失败。因此一旦要做动画，就强制 rig 用 tripo spec。
    # 运行时播放的是 baked 动画，不依赖骨骼命名，WebXR 正常工作。
    # （只绑骨、走 FBX 进 Editor 的工作流保持原 spec 不变。）
    rig_spec = rig_options.spec
    if animation_options.enabled and rig_spec.lower() != "tripo":
        logger.info(
            "[img2model] animation enabled → forcing rig spec 'tripo' (was '%s'); "
            "preset animations require the Tripo skeleton.",
            rig_spec,
        )
        rig_spec = "tripo"

    glb_rig, fbx_rig = await _run_rig_formats(
        mesh_task_id=mesh_result["task_id"],
        spec=rig_spec,
        download_dir=download_dir,
        also_emit_fbx=rig_options.also_emit_fbx,
    )
    if not glb_rig.get("success"):
        err = glb_rig.get("error") or "Rig stage failed."
        hint = (
            " Try a T-pose/A-pose full-body photo for better rigging, "
            "or disable Rigging/Animation to keep the static mesh."
        )
        overall["message"] = err + hint
        await _emit(progress_cb, state="failed", stage=STAGE_RIG, progress=100,
                    error=overall["message"])
        return overall

    rig_payload = _stage_payload(glb_rig, fbx_rig)
    overall["rig"] = rig_payload
    await _emit(progress_cb, stage=STAGE_RIG, progress=75, rig=rig_payload)

    # 不需要 animation 的话到这里就结束
    if not animation_options.enabled:
        overall["success"] = True
        overall["message"] = "Mesh + rig generated."
        await _emit(progress_cb, state="done", stage=STAGE_RIG, progress=100)
        return overall

    # ── Stage 3: animation（GLB + FBX 各跑一次）─────────────────────────────
    await _emit(progress_cb, stage=STAGE_ANIMATION, progress=80)
    glb_anim, fbx_anim = await _run_animation_formats(
        rig_task_id=glb_rig["task_id"],  # 用 GLB rig 的 task_id 作为父任务
        preset=animation_options.preset,
        download_dir=download_dir,
        also_emit_fbx=animation_options.also_emit_fbx,
    )
    if not glb_anim.get("success"):
        err = glb_anim.get("error") or "Animation stage failed."
        hint = (
            " Tripo preset animation often fails on non-T-pose try-on photos; "
            "use a T-pose/A-pose full-body image, or disable Animation to keep the rigged GLB."
        )
        overall["message"] = err + hint
        # rig 已经成功，仍然标记整体失败但 rig 产物保留
        await _emit(progress_cb, state="failed", stage=STAGE_ANIMATION, progress=100,
                    error=overall["message"])
        return overall

    anim_payload = _stage_payload(glb_anim, fbx_anim)
    overall["animation"] = anim_payload
    overall["success"] = True
    overall["message"] = "Mesh + rig + animation generated."
    await _emit(progress_cb, state="done", stage=STAGE_ANIMATION, progress=100,
                animation=anim_payload)
    return overall
