"""
FastAPI 应用入口。

注册所有路由并挂载静态资源：
- /recommend   → 多轮时尚商品推荐（LangGraph + RAG）
- /try-on      → 虚拟试穿（图生图，Gemini-2.5-flash-image）
- /img2model   → 图生 3D（Tripo3D）
- /download    → 返回生成的 3D 模型文件（供 WebXR 加载使用）
- /assets      → 前端静态资源（frontend/assets/，含 GLB、MP4、图片）
- /MetaClothesShop → WebXR 应用入口（frontend/src/index.html）
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.api.routers import download, recommender, trending
from src.cstImg.router import router as tryon_router
from src.img2model.router import router as img2model_router
from src.recommender.graph import create_recommendaer_graph, warmup

_project_root = Path(__file__).resolve().parent.parent.parent.parent
_frontend_dir = _project_root / "frontend"
_webxr_index = _frontend_dir / "src" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期钩子：启动时预热 + 构建推荐图，关闭时让资源自然释放。"""
    logger.info("[lifespan] Starting up ...")
    warmup()
    app.state.graph_app = create_recommendaer_graph()
    recommender.set_graph_app(app.state.graph_app)
    logger.info("[lifespan] Ready.")
    yield
    logger.info("[lifespan] Shutting down ...")


app = FastAPI(title="LLM Recommender API", version="1.0", lifespan=lifespan)

# ── CORS ─────────────────────────────────────────────────────────────────────
_cors_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "*").strip()
_cors_origins = (
    ["*"] if _cors_origins_env in ("", "*")
    else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API 路由 ──────────────────────────────────────────────────────────────────
app.include_router(recommender.router)
app.include_router(tryon_router)
app.include_router(img2model_router)
app.include_router(download.router)
app.include_router(trending.router)

# ── 前端静态资源 ──────────────────────────────────────────────────────────────
assets_dir = _frontend_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

# CSS & JS 模块（拆分后的前端代码）
css_dir = _frontend_dir / "src" / "css"
if css_dir.exists():
    app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")

js_dir = _frontend_dir / "src" / "js"
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


@app.get("/MetaClothesShop", include_in_schema=False)
@app.get("/MetaClothesShop/", include_in_schema=False)
def meta_clothes_shop():
    """WebXR 3D 服装店入口（HTML 在 frontend/src/）。"""
    if not _webxr_index.is_file():
        return {"error": "WebXR index not found", "path": str(_webxr_index)}
    return FileResponse(_webxr_index, media_type="text/html")


@app.get("/")
def root():
    return {
        "message": "LLM Recommender API",
        "webxr": "/MetaClothesShop",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
