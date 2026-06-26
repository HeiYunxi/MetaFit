"""
图生 3D 接口路由。

提供三套调用方式：

1. POST /img2model/                  同步阻塞（保留向后兼容，Streamlit UI 仍在用）
2. POST /img2model/submit            异步提交，立即返回 task_id（长连接客户端用）
   - 通过 body.rig.enabled / body.animation.enabled 控制是否走 rig / 动画阶段
3. GET  /img2model/status/{task_id}  轮询任务状态（含 stage 字段，可展示阶段进度）

异步任务在进程内 asyncio 后台 task 中跑，service 层每个阶段完成会通过回调实时
回写 task_store，前端不用等到全跑完就能拿到 mesh 阶段的 GLB 先预览。
"""

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from src.api.middleware.auth import get_optional_user
from src.api.session_utils import ensure_session
from src.database import execute, insert_and_get_id
from src.img2model.schemas import (
    Img2ModelRequest,
    Img2ModelResponse,
    Img2ModelStatus,
    Img2ModelSubmitResponse,
)
from src.img2model.service import run_full_pipeline, run_img2model
from src.img2model.task_store import task_store

router = APIRouter(prefix="/img2model", tags=["Img2Model"])

# 内存 task_id → img2model_tasks.id 的映射，便于异步任务回写生成历史
_db_task_ids: dict[str, int] = {}

# 内存 state → DB 枚举（img2model_tasks.status）的映射
_STATE_TO_DB = {"pending": "pending", "running": "mesh", "done": "done", "failed": "failed"}


async def _sync_task_record(task_id: str) -> None:
    """把内存任务的当前状态回写到 img2model_tasks（生成历史）。失败不影响主流程。"""
    db_id = _db_task_ids.get(task_id)
    if not db_id:
        return
    snap = task_store.get(task_id)
    if not snap:
        return
    try:
        status = _STATE_TO_DB.get(snap.state, snap.stage or "mesh")
        await execute(
            "UPDATE img2model_tasks SET status=%s, progress=%s, mesh_glb_url=%s, "
            "rig_glb_url=%s, anim_glb_url=%s, error_message=%s WHERE id=%s",
            (
                status,
                int(getattr(snap, "progress", 0) or 0),
                getattr(snap.mesh, "glb_url", None),
                getattr(snap.rig, "glb_url", None),
                getattr(snap.animation, "glb_url", None),
                (getattr(snap, "error", None) or None),
                db_id,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[img2model] sync task record failed (non-fatal): %s", exc)


@router.post("/", response_model=Img2ModelResponse)
async def img2model(body: Img2ModelRequest):
    """
    同步图生 3D（向后兼容）。

    - 调用一次会阻塞 60–180s，直到 Tripo3D 任务完成
    - 不走 rig / animation 阶段（即使 body.rig.enabled=True 也忽略）
    - 移动端建议改用 POST /img2model/submit + GET /img2model/status/<id>
    """
    if not body.image_url and not body.image_base64:
        raise HTTPException(
            status_code=400,
            detail="Provide either image_url or image_base64",
        )

    result = await run_img2model(
        image_url=body.image_url,
        image_base64=body.image_base64,
        filename_prefix=body.filename_prefix or "tryon_model",
    )

    return Img2ModelResponse(
        success=result["success"],
        model_path=result.get("model_path"),
        model_url=result.get("model_url"),
        task_id=result.get("task_id"),
        message=result.get("message", ""),
    )


async def _run_task(task_id: str, body: Img2ModelRequest) -> None:
    """
    异步任务实际工作体。

    把 progress_cb 接到 task_store.update：service 层每跑完一个阶段，
    新的字段就立刻反映到 GET /status/{task_id} 的响应里，
    前端能在 mesh 出来后立刻预览静态模型，再等 rig + animation。
    """

    async def progress_cb(fields: dict) -> None:
        await task_store.update(task_id, **fields)
        await _sync_task_record(task_id)

    await task_store.update(task_id, state="running", progress=5,
                            stage="pose_normalize" if body.pose_normalization.enabled
                            or body.rig.enabled or body.animation.enabled else "mesh")
    await _sync_task_record(task_id)
    try:
        result = await run_full_pipeline(
            image_url=body.image_url,
            image_base64=body.image_base64,
            filename_prefix=body.filename_prefix or "tryon_model",
            pose_options=body.pose_normalization,
            rig_options=body.rig,
            animation_options=body.animation,
            progress_cb=progress_cb,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[img2model] async task failed: %s", exc)
        await task_store.update(task_id, state="failed", progress=100, error=str(exc))
        await _sync_task_record(task_id)
        _db_task_ids.pop(task_id, None)
        return

    # service 已经通过 progress_cb 写过 final state（done/failed），
    # 这里只做兜底，避免 service 内部逻辑分支遗漏。
    snap = task_store.get(task_id)
    if snap and snap.state not in ("done", "failed"):
        await task_store.update(
            task_id,
            state="done" if result.get("success") else "failed",
            progress=100,
            error=None if result.get("success") else result.get("message"),
        )
    await _sync_task_record(task_id)
    _db_task_ids.pop(task_id, None)


@router.post("/submit", response_model=Img2ModelSubmitResponse)
async def submit_img2model(
    body: Img2ModelRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """
    异步提交一次图生 3D，立即返回 task_id。

    根据 body 中的 pose / rig / animation 开关，自动决定流水线长度：
    - 都关 → 只跑 mesh
    - pose 开（或 rig/anim 开，服务端会自动 pose）→ T-pose 归一化 → mesh
    - rig 开 → + 绑骨（默认 GLB 一次）
    - animation 开 → + 预 bake 动画

    客户端拿到 task_id 之后，按 2–3 秒间隔轮询 GET /img2model/status/{task_id}，
    state == "done" 时再用响应里的 mesh/rig/animation.glb_url 加载文件。
    """
    if not body.image_url and not body.image_base64:
        raise HTTPException(
            status_code=400,
            detail="Provide either image_url or image_base64",
        )

    task_id = str(uuid4())
    await task_store.create(task_id)

    # 写入生成历史记录（关联到会话/用户），失败不阻塞任务
    try:
        session_id = await ensure_session(request, user)
        preset = body.animation.preset if body.animation.enabled else None
        db_id = await insert_and_get_id(
            "INSERT INTO img2model_tasks (session_id, product_id, status, progress, animation_preset) "
            "VALUES (%s, %s, 'pending', 0, %s)",
            (session_id, body.product_id, preset),
        )
        _db_task_ids[task_id] = db_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("[img2model] create task record failed (non-fatal): %s", exc)

    asyncio.create_task(_run_task(task_id, body))

    return Img2ModelSubmitResponse(
        task_id=task_id,
        status_url=f"/img2model/status/{task_id}",
    )


@router.get("/status/{task_id}", response_model=Img2ModelStatus)
def get_status(task_id: str):
    """查询异步图生 3D 任务的状态。"""
    status = task_store.get(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="task not found")
    return status
