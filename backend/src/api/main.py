"""
FastAPI 应用入口。

注册所有路由并挂载静态资源：
- /recommend   → 多轮时尚商品推荐（LangGraph + RAG）
- /try-on      → 虚拟试穿（图生图，Gemini-2.5-flash-image）
- /img2model   → 图生 3D（Tripo3D）
- /download    → 返回生成的 3D 模型文件（供 WebXR 加载使用）
- /assets      → 前端静态资源（frontend/assets/，含 GLB、MP4、图片）
- /MetaClothesShop → 商城主页（frontend/src/pages/home/index.html）
- /fitting-room    → 3D 试衣间（frontend/src/fitting-room/index.html）
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.api.routers import download, recommender, trending
from src.api.routers import auth, users, cart, coins, coupons, orders, merchant, catalog
from src.cstImg.router import router as tryon_router
from src.img2model.router import router as img2model_router
from src.recommender.graph import create_recommendaer_graph, warmup
from src.database import close_pool

_project_root = Path(__file__).resolve().parent.parent.parent.parent
_frontend_dir = _project_root / "frontend"


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
    await close_pool()


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
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(cart.router)
app.include_router(coins.router)
app.include_router(coupons.router)
app.include_router(orders.router)
app.include_router(merchant.router)
app.include_router(catalog.router)

# ── 前端静态资源 ──────────────────────────────────────────────────────────────
# 大媒体资源（GLB / MP4 / 图片）
assets_dir = _frontend_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

# 商家上传的产品图片（backend/download/products/）
from src.config import settings as app_settings
products_dir = Path(app_settings.DOWNLOAD_DIR) / "products"
if not products_dir.exists():
    products_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets/products", StaticFiles(directory=str(products_dir)), name="product_images")

# 用户上传的全身照（backend/download/users/）；用独立前缀避免被 /assets 拦截
users_upload_dir = Path(app_settings.DOWNLOAD_DIR) / "users"
if not users_upload_dir.exists():
    users_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/users", StaticFiles(directory=str(users_upload_dir)), name="user_uploads")

# 虚拟试穿结果图（backend/download/tryon/）：模型只返回 base64，落地成文件后才能在历史里展示
tryon_dir = Path(app_settings.DOWNLOAD_DIR) / "tryon"
if not tryon_dir.exists():
    tryon_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/tryon", StaticFiles(directory=str(tryon_dir)), name="tryon_results")

# 整个前端源码目录统一挂载到 /app（shared / css / js / pages / fitting-room / merchant）
# 开发期对前端源码禁用浏览器缓存：避免改动 JS 后浏览器混用新旧 ES module 缓存
# （例如新 main.js 引用旧 api.js 缺失的导出）导致整页脚本中断、场景/列表加载不出来。
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


_src_dir = _frontend_dir / "src"
if _src_dir.exists():
    app.mount("/app", NoCacheStaticFiles(directory=str(_src_dir)), name="app")

# ── 页面入口（HTML 用 FileResponse 暴露干净 URL，资源统一引用 /app/...） ──────
_pages_dir = _src_dir / "pages"
_home_index = _pages_dir / "home" / "index.html"
_product_index = _pages_dir / "product" / "index.html"
_profile_index = _pages_dir / "profile" / "index.html"
_fitting_index = _src_dir / "fitting-room" / "index.html"
_merchant_index = _src_dir / "merchant" / "index.html"


def _serve(path: Path, label: str):
    if not path.is_file():
        return {"error": f"{label} not found", "path": str(path)}
    return FileResponse(path, media_type="text/html")


@app.get("/", include_in_schema=False)
def root():
    """根路径重定向到主页。"""
    return RedirectResponse(url="/MetaClothesShop")


@app.get("/MetaClothesShop", include_in_schema=False)
@app.get("/MetaClothesShop/", include_in_schema=False)
def home_page():
    """主页（未登录可访问的商品商城）。"""
    return _serve(_home_index, "Home page")


@app.get("/product", include_in_schema=False)
@app.get("/product/", include_in_schema=False)
def product_page():
    """商品详情页（?id=...）。"""
    return _serve(_product_index, "Product page")


@app.get("/profile", include_in_schema=False)
@app.get("/profile/", include_in_schema=False)
def profile_page():
    """个人主页（独立页面，需登录）。"""
    return _serve(_profile_index, "Profile page")


@app.get("/fitting-room", include_in_schema=False)
@app.get("/fitting-room/", include_in_schema=False)
def fitting_room_page():
    """3D 试衣间（WebXR 场景）。"""
    return _serve(_fitting_index, "Fitting room")


@app.get("/merchant", include_in_schema=False)
@app.get("/merchant/", include_in_schema=False)
def merchant_portal():
    """商家管理后台入口。"""
    return _serve(_merchant_index, "Merchant portal")


@app.get("/health")
def health():
    return {"status": "healthy"}
