"""
图生 3D 接口的请求/响应数据模型（POST /img2model）。

支持三段式异步流水线：
- mesh:      Tripo image_to_model（基础 GLB）
- rig:       Tripo rig_model（带骨骼，可同时出 GLB + FBX）
- animation: Tripo retarget_animation（预 bake 一段动画，可同时出 GLB + FBX）

每段都把结果写进 task_store，WebXR 前端可以根据 stage 字段实时反馈进度。
"""

from pydantic import BaseModel, Field


# ── 枚举：与 Tripo3D SDK 的 Animation enum 对齐 ────────────────────────────────
# 这里只暴露最常用的人形预设，避免误传其它骨架专属动画（quadruped/serpentine）。
AnimationPreset = (
    "idle", "walk", "run", "dive", "climb", "jump",
    "slash", "shoot", "hurt", "fall", "turn",
)


class RigOptions(BaseModel):
    """绑骨配置；spec=mixamo 时与 Humanoid Avatar 自动映射兼容性最好。"""

    enabled: bool = Field(default=False, description="是否在 mesh 后追加 rig 阶段")
    spec: str = Field(
        default="mixamo",
        description="骨骼命名规范：'mixamo'（Humanoid 友好）或 'tripo'",
    )
    also_emit_fbx: bool = Field(
        default=False,
        description="是否额外导出 FBX（多消耗一次 Tripo 配额，仅 Editor 工作流需要）",
    )


class PoseNormalizationOptions(BaseModel):
    """姿势归一化：LaoZhang Nano-Banana 把任意全身照重绘为 T-pose。"""

    enabled: bool = Field(
        default=False,
        description="是否在 mesh 阶段前先把人像重绘为 T-pose（推荐 rig/animation 时开启）",
    )


class AnimationOptions(BaseModel):
    """动画配置；只在 rig.enabled=True 时有效。"""

    enabled: bool = Field(default=False, description="是否在 rig 后追加 animation 阶段")
    preset: str = Field(
        default="idle",
        description="动画预设：idle / walk / run / jump 等（与 Tripo Animation 枚举一致）",
    )
    also_emit_fbx: bool = Field(
        default=False,
        description="是否额外导出 FBX 动画（多消耗一次 Tripo 配额）",
    )


class Img2ModelRequest(BaseModel):
    """图生 3D 请求。image_url 和 image_base64 二选一。"""

    image_url: str | None = Field(
        default=None,
        description="图片 URL（来自试穿结果 tryon_image_url，或用户上传的 T-pose 全身照）",
    )
    image_base64: str | None = Field(
        default=None,
        description="base64 编码图片（来自试穿结果 tryon_image_base64）",
    )
    filename_prefix: str = Field(
        default="tryon_model",
        description="保存文件名前缀，实际文件名由 Tripo SDK 使用 task_id 决定",
    )
    product_id: int | None = Field(
        default=None,
        description="关联的数据库商品 id（可选，用于生成历史展示）",
    )
    pose_normalization: PoseNormalizationOptions = Field(
        default_factory=PoseNormalizationOptions,
        description="是否在 mesh 阶段前先把任意姿势重绘为 T-pose（约 +5–10s）",
    )
    rig: RigOptions = Field(
        default_factory=RigOptions,
        description="是否在 mesh 之后做自动绑骨",
    )
    animation: AnimationOptions = Field(
        default_factory=AnimationOptions,
        description="是否在 rig 之后预 bake 一段动画",
    )


class Img2ModelResponse(BaseModel):
    """图生 3D 同步响应（保留向后兼容）。"""

    success: bool = Field(..., description="是否成功生成 3D 模型")
    model_path: str | None = Field(
        default=None,
        description="模型在项目内的相对路径，例如 download/xxx_pbr.glb",
    )
    model_url: str | None = Field(
        default=None,
        description="Tripo3D 返回的原始下载 URL（保存后仍可访问）",
    )
    task_id: str | None = Field(default=None, description="Tripo3D 任务 ID，可用于追踪")
    message: str = Field(default="", description="状态说明或错误信息")


class Img2ModelSubmitResponse(BaseModel):
    """异步提交响应：立即返回 task_id，客户端轮询状态。"""

    task_id: str = Field(..., description="本地任务 ID（非 Tripo3D 任务 ID）")
    status_url: str = Field(..., description="轮询任务状态的 URL，例如 /img2model/status/<id>")


class StageArtifacts(BaseModel):
    """单一阶段（mesh / rig / animation）产出的下载链接集合。"""

    glb_url: str | None = Field(default=None, description="GLB 完整下载 URL（含 /download/ 前缀）")
    fbx_url: str | None = Field(default=None, description="FBX 完整下载 URL（含 /download/ 前缀）")
    tripo_task_id: str | None = Field(default=None, description="该阶段对应的 Tripo3D 任务 ID")


class Img2ModelStatus(BaseModel):
    """异步任务状态。

    前端轮询时关心 state + stage：
    - state: pending / running / done / failed
    - stage: mesh / rig / animation —— 当前正在跑的阶段
    """

    task_id: str
    state: str = Field(..., description="pending | running | done | failed")
    stage: str = Field(default="mesh", description="pose_normalize | mesh | rig | animation")
    progress: int = Field(default=0, description="0-100，阶段切换时跳变")
    pose_normalized: bool = Field(
        default=False,
        description="是否完成 T-pose 归一化（pose_normalization.enabled=True 且成功时为 True）",
    )

    # 保留向后兼容字段（指向 mesh 阶段的 GLB）
    model_path: str | None = Field(default=None, description="相对路径，例如 download/xxx.glb（mesh）")
    download_url: str | None = Field(default=None, description="mesh 阶段 GLB 的完整 URL")
    tripo_task_id: str | None = Field(default=None, description="mesh 阶段对应的 Tripo3D 任务 ID")

    # 各阶段分别的产物链接
    mesh: StageArtifacts = Field(default_factory=StageArtifacts)
    rig: StageArtifacts = Field(default_factory=StageArtifacts)
    animation: StageArtifacts = Field(default_factory=StageArtifacts)

    error: str | None = Field(default=None, description="失败原因，仅在 state=failed 时非空")
