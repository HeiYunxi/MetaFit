<div align="center">

[**English**](#english) &nbsp;|&nbsp; [**中文**](#chinese)

</div>

---

<h1 id="english" align="center">🛍️ LLM-Based E-Commerce Fashion Recommender</h1>

<p align="center"><strong>AI-powered fashion recommendation system leveraging LLMs, RAG, and immersive 3D technology for next-generation shopping experiences.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Workflow-7c3aed" alt="LangGraph">
  <img src="https://img.shields.io/badge/GPT--4o-LLM-00a67e" alt="GPT-4o">
  <img src="https://img.shields.io/badge/WebXR-Three.js-green" alt="WebXR">
</p>

---

## 🎯 Project Overview

This project is a **Retrieval-Augmented Generation (RAG) chatbot** designed for **fashion e-commerce**. It provides **personalized recommendations, multi-turn conversations, virtual try-on, image-to-3D generation**, and an **immersive WebXR 3D storefront** — a complete end-to-end AI shopping assistant.

> **Core idea:** Use LLMs as a shopping guide, vector search for product retrieval, and image/3D generation to let users **"see themselves wearing it."**

Built with **FastAPI, LangGraph, FAISS, ChromaDB, GPT-4o, Gemini-2.5, Tripo3D, and Three.js/WebXR**.

---

## ✨ Key Features

| # | Feature | Description |
|---|---------|-------------|
| 01 | **AI Fashion Recommendations** | Natural language → smart product matching with LLM-generated reasoning |
| 02 | **Multi-Turn Conversation** | Context-aware follow-up queries ("in red", "cheaper") via Query Rewrite |
| 03 | **Hybrid Retrieval** | FAISS (semantic) + BM25 (keyword) + ChromaDB Self-Query (metadata) + Cross-Encoder (rerank) |
| 04 | **Topic Guard** | LLM classifier filters off-topic queries, keeping the system focused on fashion |
| 05 | **Virtual Try-On** | Upload a photo + select a garment → AI-generated try-on result via Gemini-2.5-flash-image |
| 06 | **Image-to-3D** | Try-on result → GLB 3D model via Tripo3D (pose→mesh→rig→animation pipeline) |
| 07 | **WebXR 3D Storefront** | Immersive 3D clothing shop with first-person controls, zone interactions, and VR support |
| 08 | **REST API** | FastAPI-powered endpoints with Swagger docs at `/docs` |

---

## 🏗️ Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12 |
| **LLM & Vision** | GPT-4o · Gemini-2.5-flash-image (via LaoZhang API proxy) |
| **Vector Search** | FAISS · ChromaDB |
| **Retrieval & Ranking** | BM25 · LangChain · Cross-Encoder |
| **Orchestration** | LangGraph (5-node RAG workflow) |
| **Frontend** | WebXR · Three.js (GLTFLoader + Draco) |
| **3D Generation** | Tripo3D (image-to-3D GLB) |
| **Embedding** | sentence-transformers/all-MiniLM-L6-v2 (local, offline) |
| **Rerank Model** | cross-encoder/ms-marco-MiniLM-L-6-v2 (local) |
| **Data Source** | Farfetch.com product data (local CSV) |

---

## 📊 Data & Indexing

### Data Source
The system uses **Farfetch.com** fashion product data stored locally as CSV (`backend/data/FashionDataset.csv`). Each record includes:
- Product name, brand, price, currency, discount
- Image URL, sizes, category label
- Material composition, washing instructions
- Farfetch ID, brand style ID

> ⚠️ The current dataset is **static** (pre-collected). Future plans include connecting to live merchant data or integrating with other e-commerce platform APIs.

### Indexing Pipeline
1. **Preprocess** — Normalize columns, expand size fields into boolean metadata
2. **Embed** — Generate 384-dim vectors via `all-MiniLM-L6-v2` (runs locally)
3. **Build Indexes** — FAISS + BM25 + ChromaDB + Cross-Encoder (all stored in `backend/data/indexes/`)

---

## 🔄 Recommendation Flow (LangGraph)

```
User Query
  → ① query_rewrite     — Rewrite follow-up queries using conversation history
  → ② check_topic        — Guard: is this fashion-related? (Yes/No)
  → ③ self_query_retrieve — LLM → structured filters → ChromaDB metadata search
       ├─ success → ⑤ rag_recommender
       └─ empty   → ④ ranker (FAISS + BM25 + Cross-Encoder fallback)
                         → ⑤ rag_recommender
  → Final: product list + LLM-generated recommendation
```

Each node has a single responsibility and can be independently replaced, debugged, or extended.

---

## 🖥️ Frontend — WebXR 3D Storefront

The frontend is a **single-page Three.js application** served by FastAPI at `/MetaClothesShop`.

### Architecture
```
index.html
├── Chat Panel        — Natural language query + recommendation cards + trending strip
├── 3D Viewport       — Three.js renderer (WebGLRenderer + ACES tone mapping)
├── Try-On Panel      — Photo upload + virtual try-on trigger
├── Model Panel       — Image-to-3D generation with stage progress (pose→mesh→rig→anim)
├── Cart Panel        — Shopping cart with add/remove/clear
└── Coin Panel        — Rewards system (ad video → coins → coupons)
```

### Scene Management (`scene.js`)
- Loads `ClothesShop_optimized.glb` (86MB, Draco-compressed)
- Procedural sky dome with gradient shader (falls back to `/assets/sky.jpg`)
- PBR environment map generation for reflections
- Material repair pipeline: untextured meshes → warm beige tones
- Collision detection, walkable zones, obstacle boundaries

### First-Person Controls (`player.js`)
- WASD / Arrow keys movement with per-axis collision
- Mouse drag for look rotation (yaw/pitch)
- Height-aware floor detection (tabletop-safe movement)
- 6 interaction zones: Womenswear, Menswear, Kidswear, Lounge, Fitting Room, 3D Showcase

### User Interaction Flow
```
Open /MetaClothesShop
  → Download & render 3D shop scene (GLB)
  → Spawn at entry position
  → Free roam (WASD + mouse)
  → Chat query / Browse trending / Walk into zones
  → Select product → Add to cart / Virtual try-on
  → Upload photo → Generate try-on → Generate 3D model
  → View 360° rotation → Enter VR mode
```

### System Processing Flow (End-to-End)
```
User types query ("Woman dress under $50")
  → POST /recommend {question}
  → LangGraph: query_rewrite → check_topic → self_query/ranker → RAG
  → Return {answer, products[]}
  → Render recommendation cards (Markdown → HTML)

User selects product + uploads photo
  → POST /try-on (multipart: person_image + product_image_url)
  → Gemini-2.5-flash-image generates try-on result
  → Return {tryon_image_url}
  → Display result in chat

User clicks "Generate 3D Model"
  → POST /img2model/submit (async)
  → Tripo3D pipeline: pose_normalize → mesh → rig → animation
  → Poll GET /img2model/status/{id} every 2.5s
  → Load GLB via glTFast → 360° auto-rotation → VR viewing
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/recommend/` | Multi-turn fashion recommendation (RAG) |
| `POST` | `/try-on` | Virtual try-on (person photo + garment image) |
| `POST` | `/img2model/` | Image-to-3D (synchronous, legacy) |
| `POST` | `/img2model/submit` | Image-to-3D (async, with stage progress) |
| `GET` | `/img2model/status/{id}` | Poll async 3D task status |
| `GET` | `/trending` | Trending/hot products |
| `GET` | `/download/{filename}` | Download generated GLB models |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger interactive API docs |

Visit **http://localhost:8000/docs** after starting the API.

---

## 🛠️ Project Structure

```
llm-based-recommender/
├── backend/                 # Backend (API, recommendation engine, data)
│   ├── src/
│   │   ├── api/             # FastAPI entry & routers
│   │   ├── recommender/     # LangGraph recommendation workflow
│   │   ├── indexing/        # Offline index building scripts
│   │   ├── cstImg/          # Virtual try-on (image-to-image)
│   │   ├── img2model/       # Image-to-3D (Tripo3D)
│   │   ├── util/            # Image processing utilities
│   │   └── config.py        # Global configuration
│   ├── data/                # Dataset & offline indexes
│   └── download/            # Generated GLB model cache
├── frontend/                # WebXR frontend
│   ├── assets/              # Static resources (GLB, images, video)
│   └── src/                 # WebXR app (index.html + css/js modules)
├── docs/                    # Documentation & meeting materials
├── pyproject.toml           # Project dependencies
└── .env.example             # Environment variable template
```

---

## 🔧 Setup & Installation

### Prerequisites
- Python **3.12+**
- [`uv`](https://github.com/astral-sh/uv) package manager

### 1. Clone & Setup Environment
```bash
git clone <repo-url>
cd llm-based-recommender
cp .env.example .env    # Then fill in your API keys
```

### 2. Key Environment Variables

| Variable | Purpose |
|----------|---------|
| `LAOZHANG_GPT_API_KEY` | LLM calls (recommendation, topic check, query rewrite) |
| `LAOZHANG_IMAGE_API_KEY` | Virtual try-on (image-to-image) |
| `TRIPO_API_KEY` | Image-to-3D model generation |

### 3. Install Dependencies
```bash
uv python install
uv sync --all-extras
```

### 4. Build Indexes (only if `backend/data/indexes/` is missing)
```powershell
# PowerShell
$env:PYTHONPATH = "backend"
uv run python -m src.indexing.embedding
```
```bash
# Linux / macOS
export PYTHONPATH=backend
uv run python -m src.indexing.embedding
```

### 5. Start the Server
```powershell
# PowerShell
$env:PYTHONPATH = "backend"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```
```bash
# Linux / macOS
export PYTHONPATH=backend
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 6. Open the App
- **WebXR Storefront:** http://localhost:8000/MetaClothesShop
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## 🎯 Design Highlights

1. **Multi-Route Retrieval + Reranking** — FAISS (semantic) + BM25 (keyword) + Self-Query (structured filters) + Cross-Encoder (reranking) for complementary accuracy
2. **True Multi-Turn Dialogue** — Query Rewrite reconstructs full intent from conversational follow-ups, not just history concatenation
3. **Modular Workflow** — LangGraph breaks recommendation into observable, replaceable nodes for easy debugging and extension
4. **End-to-End Experience** — Text recommendation → virtual try-on → 3D model → immersive VR viewing
5. **Local + Cloud Hybrid** — Embedding and reranking run locally (low cost, low latency); only LLM dialogue and image/3D generation use cloud APIs

---

## ⚠️ Current Limitations

| Issue | Description |
|-------|-------------|
| **External API Dependency** | GPT-4o, Gemini, Tripo3D rely on third-party services — cost and latency are not fully controllable |
| **Static Dataset** | Farfetch data is pre-collected; no live merchant API integration yet |
| **WebXR POC Stage** | Frontend interaction UX is still being refined |
| **Embedding Model** | `all-MiniLM-L6-v2` is a general-purpose model (384-dim); domain-specific fashion models would improve accuracy |
| **No Personalization** | Recommendations are query-based only; user profiling and feedback loops not yet implemented |

---

## 🚀 Future Work

- 🔹 **Fine-tune LLMs** on fashion domain data to reduce closed-source API dependency
- 🔹 **Multi-language support** (Chinese, Japanese, etc.)
- 🔹 **Cloud deployment** (AWS/GCP with auto-scaling)
- 🔹 **Personalized recommendations** using user behavior history and preferences
- 🔹 **Evaluation framework** (NDCG, MRR, user satisfaction metrics)
- 🔹 **Live data integration** — connect to real merchant/e-commerce platform APIs
- 🔹 **Enhanced VR experience** — full virtual fitting room with social shopping

---

<h1 id="chinese" align="center">🛍️ 基于大语言模型的时尚电商推荐系统</h1>

<p align="center"><strong>融合 LLM、RAG 与沉浸式 3D 技术的 AI 导购系统，打造下一代购物体验。</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Workflow-7c3aed" alt="LangGraph">
  <img src="https://img.shields.io/badge/GPT--4o-LLM-00a67e" alt="GPT-4o">
  <img src="https://img.shields.io/badge/WebXR-Three.js-green" alt="WebXR">
</p>

---

## 🎯 项目概述

这是一个面向**时尚电商**场景的 **AI 导购系统**。将「检索增强生成(RAG)」「多轮对话」「虚拟试穿」「图生 3D」「WebXR 沉浸式展示」串成一条完整链路，模拟用户从「描述需求 → 得到推荐 → 试穿 → 3D/VR 查看」的购物体验。

> **核心思路：** 用大模型当导购，用向量检索找货，用图像/3D 生成让用户**「看见自己穿上」**。

技术栈：**FastAPI、LangGraph、FAISS、ChromaDB、GPT-4o、Gemini-2.5、Tripo3D、Three.js/WebXR**。

---

## ✨ 核心功能

| # | 功能 | 说明 |
|---|------|------|
| 01 | **AI 时尚推荐** | 自然语言描述需求 → 智能匹配商品 + LLM 生成推荐理由 |
| 02 | **多轮对话理解** | 上下文追问（"要红色的""便宜点的"），Query Rewrite 自动改写为完整查询 |
| 03 | **混合检索** | FAISS（语义）+ BM25（关键词）+ ChromaDB Self-Query（元数据过滤）+ Cross-Encoder（精排） |
| 04 | **话题守卫** | LLM 分类器拦截非时尚话题，聚焦导购场景 |
| 05 | **虚拟试穿** | 上传人物照 + 选中商品图 → Gemini-2.5 合成试穿效果，中英双语 Prompt |
| 06 | **图生 3D** | 试穿图 → Tripo3D 生成 GLB 三维模型（pose→mesh→rig→animation 四阶段流水线） |
| 07 | **WebXR 3D 商店** | 沉浸式 3D 服装店，第一人称漫游 + 区域交互推荐 + VR 模式 |
| 08 | **REST API** | FastAPI 标准化接口，提供 Swagger 在线文档（`/docs`） |

---

## 🏗️ 技术栈

| 层次 | 技术 |
|------|------|
| **编程语言** | Python 3.12 |
| **LLM / 图像 API** | GPT-4o · Gemini-2.5-flash-image（经老张 API 代理） |
| **向量检索** | FAISS · ChromaDB |
| **检索与排序** | BM25 · LangChain · Cross-Encoder |
| **流程编排** | LangGraph（五节点 RAG 工作流） |
| **前端** | WebXR · Three.js（GLTFLoader + Draco 压缩） |
| **3D 生成** | Tripo3D（图生 3D GLB） |
| **嵌入模型** | sentence-transformers/all-MiniLM-L6-v2（本地运行，384 维） |
| **重排模型** | cross-encoder/ms-marco-MiniLM-L-6-v2（本地运行） |
| **数据来源** | Farfetch.com 时尚商品数据（本地 CSV） |

---

## 📊 数据与索引

### 数据来源
系统使用 **Farfetch.com** 时尚商品数据，以 CSV 格式存储在本地（`backend/data/FashionDataset.csv`）。每条记录包含：
- 商品名称、品牌、价格、货币、折扣
- 图片 URL、尺码、品类标签
- 材质成分、洗护说明
- Farfetch ID、品牌款式 ID

> ⚠️ 当前数据集为**静态数据**（预先采集）。未来计划接入商户实时数据或其他电商平台 API。

### 索引构建流程
1. **预处理** — 列规范化、尺码字段展开为布尔元数据
2. **嵌入生成** — `all-MiniLM-L6-v2` 生成 384 维向量（本地运行）
3. **构建索引** — FAISS + BM25 + ChromaDB + Cross-Encoder（存储在 `backend/data/indexes/`）

---

## 🔄 推荐流程（LangGraph）

```
用户查询
  → ① query_rewrite      — 结合对话历史改写追问（多轮支持）
  → ② check_topic         — 话题守卫：是否属于时尚推荐？（Yes/No）
  → ③ self_query_retrieve — LLM → 结构化过滤条件 → ChromaDB 元数据检索
       ├─ success → ⑤ rag_recommender
       └─ empty   → ④ ranker（FAISS + BM25 + Cross-Encoder 兜底）
                         → ⑤ rag_recommender
  → 最终输出：商品列表 + LLM 生成的推荐理由
```

每个节点职责单一、可独立替换、可观测调试。

---

## 🖥️ 前端 — WebXR 3D 商店

前端是基于 **Three.js** 的单页面应用，由 FastAPI 在 `/MetaClothesShop` 统一托管。

### 模块架构
```
index.html
├── Chat Panel         — 自然语言查询 + 推荐卡片（Markdown 渲染）+ Trending 热门商品
├── 3D Viewport        — Three.js 渲染器（WebGLRenderer + ACES 色调映射）
├── Try-On Panel       — 照片上传 + 虚拟试穿触发
├── Model Panel        — 图生 3D 生成 + 阶段进度展示（pose→mesh→rig→animation）
├── Cart Panel         — 购物车（添加/移除/清空）
└── Coin Panel         — 金币积分系统（广告视频 → 金币 → 优惠券兑换）
```

### 场景管理（`scene.js`）
- 加载 `ClothesShop_optimized.glb`（86MB，Draco 压缩）
- 程序化天空球（渐变 Shader，支持 `/assets/sky.jpg` 图片兜底）
- PBR 环境贴图生成（真实反射）
- 材质修复：无贴图网格 → 暖色调（米色/奶油色）
- 碰撞检测、可行走区域、障碍物边界

### 第一人称控制（`player.js`）
- WASD / 方向键移动（逐轴碰撞检测）
- 鼠标拖拽环视（偏航/俯仰角）
- 高度感知地面检测（防止走上桌面）
- 6 个交互区域：女装区、男装区、童装区、休息区、试衣间、3D 展示区

### 用户交互流程
```
打开 /MetaClothesShop
  → 下载并渲染 3D 店铺场景 (GLB)
  → 自动定位到入口位置
  → 自由漫游（WASD + 鼠标）
  → 聊天查询 / 浏览 Trending / 走进区域
  → 选中商品 → 加入购物车 / 虚拟试穿
  → 上传照片 → 生成试穿图 → 生成 3D 模型
  → 360° 旋转查看 → 进入 VR 模式
```

### 系统处理流程（端到端）
```
用户输入查询（"Woman dress under $50"）
  → POST /recommend {question}
  → LangGraph：query_rewrite → check_topic → self_query/ranker → RAG
  → 返回 {answer, products[]}
  → 渲染推荐卡片（Markdown → HTML）

用户选中商品 + 上传照片
  → POST /try-on（multipart：人物照 + 商品图）
  → Gemini-2.5-flash-image 生成试穿效果
  → 返回 {tryon_image_url}
  → 在聊天区展示结果

用户点击 "Generate 3D Model"
  → POST /img2model/submit（异步提交）
  → Tripo3D 流水线：pose_normalize → mesh → rig → animation
  → 每 2.5s 轮询 GET /img2model/status/{id}
  → 加载 GLB → 360° 自动旋转 → VR 查看
```

---

## 📡 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/recommend/` | 多轮时尚推荐（RAG 主链路） |
| `POST` | `/try-on` | 虚拟试穿（人物照 + 商品图） |
| `POST` | `/img2model/` | 图生 3D（同步，向后兼容） |
| `POST` | `/img2model/submit` | 图生 3D（异步，支持阶段进度查询） |
| `GET` | `/img2model/status/{id}` | 查询异步 3D 任务状态 |
| `GET` | `/trending` | 热门/趋势商品 |
| `GET` | `/download/{filename}` | 下载生成的 GLB 模型文件 |
| `GET` | `/health` | 健康检查 |
| `GET` | `/docs` | Swagger 交互式 API 文档 |

启动后端后，访问 **http://localhost:8000/docs** 可在线调试所有接口。

---

## 🛠️ 项目结构

```
llm-based-recommender/
├── backend/                 # 后端（API、推荐引擎、数据）
│   ├── src/
│   │   ├── api/             # FastAPI 入口与路由
│   │   ├── recommender/     # LangGraph 推荐工作流
│   │   ├── indexing/        # 离线索引构建脚本
│   │   ├── cstImg/          # 虚拟试穿（图生图）
│   │   ├── img2model/       # 图生 3D（Tripo3D）
│   │   ├── util/            # 图片处理工具
│   │   └── config.py        # 全局配置
│   ├── data/                # 数据集与离线索引
│   └── download/            # 生成的 GLB 模型缓存
├── frontend/                # WebXR 前端
│   ├── assets/              # 静态资源（GLB、图片、视频）
│   └── src/                 # WebXR 应用（index.html + css/js 模块）
├── docs/                    # 文档与会议材料
├── pyproject.toml           # 项目依赖
└── .env.example             # 环境变量模板
```

---

## 🔧 安装与启动

### 环境要求
- Python **3.12+**
- [`uv`](https://github.com/astral-sh/uv) 包管理器

### 1. 克隆仓库 & 配置环境
```bash
git clone <repo-url>
cd llm-based-recommender
cp .env.example .env    # 填写你的 API 密钥
```

### 2. 关键环境变量

| 变量 | 用途 |
|------|------|
| `LAOZHANG_GPT_API_KEY` | LLM 调用（推荐对话、话题判断、查询改写） |
| `LAOZHANG_IMAGE_API_KEY` | 虚拟试穿（图生图） |
| `TRIPO_API_KEY` | 图生 3D 模型生成 |

### 3. 安装依赖
```bash
uv python install
uv sync --all-extras
```

### 4. 构建索引（仅当 `backend/data/indexes/` 缺失时需要）
```powershell
# PowerShell
$env:PYTHONPATH = "backend"
uv run python -m src.indexing.embedding
```
```bash
# Linux / macOS
export PYTHONPATH=backend
uv run python -m src.indexing.embedding
```

### 5. 启动服务
```powershell
# PowerShell
$env:PYTHONPATH = "backend"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```
```bash
# Linux / macOS
export PYTHONPATH=backend
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 6. 打开应用
- **WebXR 3D 商店：** http://localhost:8000/MetaClothesShop
- **API 文档：** http://localhost:8000/docs
- **健康检查：** http://localhost:8000/health

> Quest 头显访问（同一局域网）：`http://你的电脑IP:8000/MetaClothesShop`

---

## 🎯 设计亮点

1. **多路召回 + 精排** — FAISS（语义）+ BM25（关键词）+ Self-Query（结构化过滤）+ Cross-Encoder（重排），互补提升准确率与鲁棒性
2. **真·多轮对话** — Query Rewrite 将口语化追问还原为完整意图，而非简单的历史拼接
3. **模块化流程** — LangGraph 将推荐拆分为可观测、可替换的节点，便于调试与扩展
4. **端到端体验闭环** — 文本推荐 → 虚拟试穿 → 图生 3D → WebXR/VR 展示，覆盖完整购物链路
5. **本地 + 云端混合** — 嵌入和重排在本地运行（省钱、低延迟），仅 LLM 对话和图像/3D 生成走云端 API

---

## ⚠️ 现存问题

| 问题 | 说明 |
|------|------|
| **依赖外部 API** | GPT-4o、Gemini、Tripo3D 均依赖第三方服务，成本与延迟不可控，密钥存在额度耗尽风险 |
| **数据集为静态** | Farfetch 数据为预先采集，尚未接入商户实时 API |
| **WebXR 前端 POC 阶段** | 交互体验待优化，UI 需进一步完善 |
| **嵌入模型精度有限** | `all-MiniLM-L6-v2` 为通用模型，时尚领域语义区分不如领域专用模型 |
| **缺少个性化闭环** | 推荐仅基于单次查询，未利用用户画像、行为历史及反馈信号 |

---

## 🚀 未来工作

- 🔹 **LLM 微调** — 在时尚电商领域数据上微调开源 LLM，减少闭源 API 依赖
- 🔹 **多语言支持** — 扩展中文、日语等语言的查询理解与推荐生成
- 🔹 **云端部署** — 迁移至 AWS/GCP，实现自动扩缩容与高可用
- 🔹 **个性化推荐** — 引入用户画像、浏览历史、购买记录等行为信号
- 🔹 **评估框架** — 建立 NDCG、MRR、用户满意度等离线/在线评估体系
- 🔹 **实时数据接入** — 对接真实商户/电商平台 API，替代静态数据集
- 🔹 **沉浸式 VR 完善** — 实现完整虚拟试衣间与社交购物体验

---

<div align="center">

[**↑ Back to English ↑**](#english)

</div>
