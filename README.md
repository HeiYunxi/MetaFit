<div align="center">

[**English**](#english) &nbsp;|&nbsp; [**中文**](#chinese)

</div>

---

<h1 id="english" align="center">MetaFit — AI Fashion E-Commerce Platform</h1>

<p align="center"><strong>LLM-powered fashion recommendations, virtual try-on, image-to-3D, and an immersive 3D fitting room — built for COMP5925.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/LangGraph-RAG-7c3aed" alt="LangGraph">
  <img src="https://img.shields.io/badge/Three.js-3D-000000?logo=threedotjs" alt="Three.js">
</p>

---

## Project Overview

**MetaFit** is an end-to-end AI fashion shopping platform. Users browse a product catalog, chat with an AI stylist (RAG), try clothes virtually, generate 3D models, and explore everything inside a **desktop 3D fitting room**. Merchants can upload products and trigger vector index rebuilds from a dedicated portal.

> **Core idea:** Use LLMs as a shopping guide, hybrid vector retrieval for product matching, and image/3D generation so users can *see themselves wearing it*.

**Stack:** FastAPI · LangGraph · FAISS · ChromaDB · MySQL · GPT-4o · Gemini-2.5 · Tripo3D · Three.js

---

## Key Features

| # | Feature | Description |
|---|---------|-------------|
| 01 | **Product catalog** | Browse, filter, and search products (Farfetch seed data + merchant uploads) |
| 02 | **AI recommendations** | Multi-turn RAG chat with query rewrite, topic guard, hybrid retrieval, reranking |
| 03 | **Virtual try-on** | Upload a photo → Gemini-2.5-flash-image compositing; results persisted in MySQL |
| 04 | **Image-to-3D** | Try-on result → Tripo3D GLB pipeline (pose → mesh → rig → animation) |
| 05 | **3D fitting room** | First-person Three.js shop: chat, try-on, 3D showcase, cart, coins (desktop; VR entry disabled) |
| 06 | **User accounts** | JWT auth, profile, body photo, browse/try-on/3D/conversation history |
| 07 | **Commerce** | Session cart, coin rewards, coupon redemption, order checkout |
| 08 | **Merchant portal** | Product CRUD, size management, background vector reindex |
| 09 | **Offline eval** | Golden-set retrieval benchmarks (Recall@K, NDCG@K, MRR) — see `backend/eval/` |

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12, FastAPI, aiomysql |
| **Database** | MySQL 8 (`sql/metafit.sql`) |
| **LLM / Vision** | GPT-4o, Gemini-2.5-flash-image (LaoZhang API proxy) |
| **Retrieval** | FAISS, BM25, ChromaDB Self-Query, Cross-Encoder rerank |
| **Orchestration** | LangGraph (5-node RAG workflow) |
| **3D generation** | Tripo3D (async task pipeline) |
| **Frontend** | Multi-page HTML/JS + shared modules; Three.js fitting room |
| **Embedding** | `sentence-transformers/all-MiniLM-L6-v2` (local, 384-dim) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (multi-page)                                          │
│  /MetaClothesShop  /product  /profile  /fitting-room  /merchant │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST + JWT + X-Session-Id
┌────────────────────────────▼────────────────────────────────────┐
│  FastAPI  —  auth · catalog · cart · coins · coupons · orders   │
│              recommender · try-on · img2model · merchant        │
└────────────┬───────────────────────────────┬────────────────────┘
             │                               │
     ┌───────▼───────┐               ┌───────▼────────┐
     │  MySQL        │               │ Vector indexes │
     │  (products,   │◄── rebuild ──│ FAISS/BM25/    │
     │   sessions,   │               │ ChromaDB       │
     │   history…)   │               └────────────────┘
     └───────────────┘
```

**Data flow:** MySQL is the single source of truth for products. Run `rebuild_index_from_db.py` (or merchant reindex) to sync Chroma/FAISS/BM25 from the database.

---

## Recommendation Flow (LangGraph)

```
User query
  → ① query_rewrite      — Rewrite follow-ups using conversation history
  → ② check_topic         — Guard: fashion-related? (Yes/No)
  → ③ self_query_retrieve — LLM → structured filters → ChromaDB
       ├─ hits  → ⑤ rag_recommender
       └─ empty → ④ ranker (FAISS + BM25 + Cross-Encoder) → ⑤ rag_recommender
  → Product list + LLM recommendation text
```

---

## Frontend Pages

| URL | Page |
|-----|------|
| `/` or `/MetaClothesShop` | Home — product grid, categories, search |
| `/product?id=` | Product detail, add to cart, link to fitting room |
| `/profile` | Account, body photo, orders, history (browse / try-on / 3D / chat) |
| `/fitting-room` | 3D shop + AI chat + try-on + 3D model viewer |
| `/merchant` | Merchant dashboard (role `merchant` or `admin`) |

The fitting room loads `ClothesShop_optimized.glb`, supports WASD + mouse look, zone-based recommendations, cart/coins panels, and 360° model rotation in the **3D Showcase** zone. **Headset VR entry is currently disabled** (not yet validated).

---

## API Endpoints (summary)

| Area | Examples |
|------|----------|
| **Auth** | `POST /auth/register`, `/auth/login`, `/auth/refresh` |
| **Catalog** | `GET /catalog/products`, `POST /catalog/{id}/view` |
| **Recommend** | `POST /recommend/` |
| **Try-on** | `POST /try-on` |
| **3D** | `POST /img2model/submit`, `GET /img2model/status/{id}` |
| **Cart / Orders** | `GET/POST /cart`, `POST /orders` |
| **Coins / Coupons** | `GET /coins/balance`, `POST /coupons/redeem` |
| **User** | `GET /users/me`, `/users/me/history/*` |
| **Merchant** | `GET/POST /merchant/products`, `POST /merchant/reindex` |
| **Misc** | `GET /trending`, `/health`, `/docs` |

Full interactive docs: **http://localhost:8000/docs**

---

## Project Structure

```
MetaFit/
├── backend/
│   ├── src/
│   │   ├── api/           # FastAPI routers, auth middleware
│   │   ├── recommender/   # LangGraph RAG workflow
│   │   ├── indexing/      # Offline index builders
│   │   ├── services/      # Auth, vector index service
│   │   ├── cstImg/        # Virtual try-on
│   │   ├── img2model/     # Image-to-3D (Tripo3D)
│   │   ├── database.py    # MySQL pool
│   │   └── config.py
│   ├── scripts/
│   │   ├── apply_schema.py          # Apply sql/metafit.sql
│   │   ├── import_products_to_db.py # CSV → MySQL
│   │   ├── rebuild_index_from_db.py # MySQL → vector indexes
│   │   └── run_rec_eval.py          # Retrieval evaluation
│   ├── eval/              # Golden set + results
│   └── data/              # CSV dataset + indexes/
├── frontend/
│   ├── assets/            # GLB, sky, ad video
│   └── src/
│       ├── pages/         # home, product, profile
│       ├── fitting-room/  # 3D fitting room entry
│       ├── merchant/      # Merchant portal
│       ├── shared/        # Auth, API clients, nav
│       └── js/            # Three.js scene modules
├── sql/metafit.sql        # Complete MySQL schema
├── .env.example
└── pyproject.toml
```

---

## Setup & Installation

### Prerequisites

- Python **3.12+**
- MySQL **8.0+**
- [`uv`](https://github.com/astral-sh/uv) (recommended)

### 1. Clone & configure

```bash
git clone <repo-url>
cd MetaFit
cp .env.example .env   # fill in API keys and MySQL credentials
```

### 2. Environment variables

| Variable | Purpose |
|----------|---------|
| `LAOZHANG_GPT_API_KEY` | LLM (recommendation, query rewrite, topic guard) |
| `LAOZHANG_IMAGE_API_KEY` | Virtual try-on (Gemini image API) |
| `TRIPO_API_KEY` | Image-to-3D generation |
| `MYSQL_HOST/PORT/USER/PASSWORD/DB` | MySQL connection |
| `JWT_SECRET_KEY` | Access/refresh token signing |

### 3. Install dependencies

```bash
uv python install
uv sync --all-extras
```

### 4. Database & product data

```bash
# Create schema (idempotent)
python backend/scripts/apply_schema.py

# Import Farfetch CSV into MySQL (first time)
python backend/scripts/import_products_to_db.py

# Build vector indexes from MySQL
python backend/scripts/rebuild_index_from_db.py
```

> If `backend/data/indexes/` already exists from a previous CSV-only setup, you can skip import and run rebuild after schema is applied.

### 5. Start the server

```powershell
# PowerShell — run from backend/
cd backend
$env:PYTHONPATH = "."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

```bash
# Linux / macOS
cd backend
export PYTHONPATH=.
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 6. Open the app

| Page | URL |
|------|-----|
| Home | http://localhost:8000/MetaClothesShop |
| Fitting room | http://localhost:8000/fitting-room |
| Profile | http://localhost:8000/profile |
| Merchant | http://localhost:8000/merchant |
| API docs | http://localhost:8000/docs |

### 7. Run retrieval evaluation (optional)

```bash
python backend/scripts/run_rec_eval.py
# See backend/eval/README.md for baselines and metrics
```

---

## Design Highlights

1. **Hybrid retrieval + reranking** — FAISS + BM25 + Self-Query + Cross-Encoder for robust fashion search
2. **Multi-turn dialogue** — Query rewrite reconstructs intent from conversational follow-ups
3. **DB-backed catalog** — Products, sessions, try-on/3D history, orders persisted in MySQL
4. **Modular LangGraph** — Each RAG node is independently replaceable and observable
5. **End-to-end demo loop** — Browse → chat → try-on → 3D model → cart → checkout

---

## Current Limitations

| Issue | Notes |
|-------|-------|
| External API dependency | GPT-4o, Gemini, Tripo3D — cost and latency vary |
| Small catalog | ~100+ products; eval uses rule-based relevance labels |
| Session-scoped cart | Cart binds to `session_id`, not a unified user-level cart |
| JWT default secret | Change `JWT_SECRET_KEY` before any public deployment |

---

## Future Work

- Human-labeled golden set and user study for thesis evaluation
- WebXR / Quest support after QA on desktop 3D experience
- User-level cart merge and browse-history backfill on login
- Domain-specific embedding model for fashion retrieval
- Live merchant API integration beyond static Farfetch seed data

---

<h1 id="chinese" align="center">MetaFit — AI 时尚电商平台</h1>

<p align="center"><strong>融合 LLM 推荐、虚拟试穿、图生 3D 与沉浸式 3D 试衣间的 COMP5925 毕业设计项目。</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/LangGraph-RAG-7c3aed" alt="LangGraph">
  <img src="https://img.shields.io/badge/Three.js-3D-000000?logo=threedotjs" alt="Three.js">
</p>

---

## 项目概述

**MetaFit** 是一条完整的 AI 时尚购物链路：商品浏览 → AI 对话推荐 → 虚拟试穿 → 图生 3D → 3D 试衣间体验，并支持用户账户、购物车、金币优惠券、订单，以及商户上架与向量索引重建。

> **核心思路：** 大模型当导购，混合向量检索找货，图像/3D 生成让用户「看见自己穿上」。

**技术栈：** FastAPI · LangGraph · FAISS · ChromaDB · MySQL · GPT-4o · Gemini-2.5 · Tripo3D · Three.js

---

## 核心功能

| # | 功能 | 说明 |
|---|------|------|
| 01 | **商品目录** | 浏览、筛选、搜索（Farfetch 种子数据 + 商户上传） |
| 02 | **AI 推荐** | 多轮 RAG：查询改写、话题守卫、混合检索、Cross-Encoder 精排 |
| 03 | **虚拟试穿** | 上传全身照 → Gemini 合成；结果写入 MySQL |
| 04 | **图生 3D** | 试穿图 → Tripo3D GLB（pose → mesh → rig → animation） |
| 05 | **3D 试衣间** | Three.js 第一人称商店：对话、试穿、3D 展示、购物车、金币（桌面端；VR 入口已关闭） |
| 06 | **用户系统** | JWT 登录、个人资料、默认试衣照、浏览/试穿/3D/对话历史 |
| 07 | **交易闭环** | Session 购物车、金币激励、优惠券兑换、下单 |
| 08 | **商户后台** | 商品 CRUD、尺码管理、后台向量重建 |
| 09 | **离线评估** | Golden set 检索指标（Recall@K、NDCG@K、MRR）— 见 `backend/eval/` |

---

## 技术栈

| 层次 | 技术 |
|------|------|
| **后端** | Python 3.12、FastAPI、aiomysql |
| **数据库** | MySQL 8（`sql/metafit.sql`） |
| **LLM / 图像** | GPT-4o、Gemini-2.5-flash-image（老张 API） |
| **检索** | FAISS、BM25、ChromaDB Self-Query、Cross-Encoder |
| **编排** | LangGraph 五节点 RAG 工作流 |
| **3D 生成** | Tripo3D 异步流水线 |
| **前端** | 多页面 HTML/JS + Three.js 试衣间 |
| **嵌入** | `all-MiniLM-L6-v2`（本地 384 维） |

---

## 系统架构

```
前端多页面（/MetaClothesShop · /product · /profile · /fitting-room · /merchant）
        │ REST + JWT + X-Session-Id
FastAPI（auth · catalog · cart · coins · coupons · orders · recommender · merchant）
        ├─ MySQL（商品、会话、历史、订单…）← rebuild_index_from_db.py
        └─ 向量索引（FAISS / BM25 / ChromaDB）
```

**MySQL 是商品与业务数据的唯一数据源**；向量索引通过脚本或商户后台重建与 DB 同步。

---

## 推荐流程（LangGraph）

```
用户查询
  → ① query_rewrite      — 结合历史改写追问
  → ② check_topic         — 话题守卫
  → ③ self_query_retrieve — ChromaDB 元数据检索
       ├─ 有结果 → ⑤ rag_recommender
       └─ 无结果 → ④ ranker（FAISS+BM25+精排）→ ⑤ rag_recommender
  → 商品列表 + LLM 推荐理由
```

---

## 前端页面

| URL | 说明 |
|-----|------|
| `/` 或 `/MetaClothesShop` | 首页 — 商品列表、分类、搜索 |
| `/product?id=` | 商品详情、加购、跳转试衣间 |
| `/profile` | 个人中心 — 资料、订单、各类历史 |
| `/fitting-room` | 3D 试衣间 + AI 对话 + 试穿 + 3D 模型 |
| `/merchant` | 商户后台（需 `merchant` / `admin` 角色） |

试衣间支持 WASD 漫游、区域推荐、购物车/金币面板，在 **3D Showcase** 区域 360° 查看模型。**头显 VR 入口暂未开放**（尚未完成测试）。

---

## API 接口（摘要）

| 模块 | 示例 |
|------|------|
| 认证 | `POST /auth/register`、`/auth/login` |
| 目录 | `GET /catalog/products` |
| 推荐 | `POST /recommend/` |
| 试穿 | `POST /try-on` |
| 3D | `POST /img2model/submit` |
| 购物车/订单 | `GET/POST /cart`、`POST /orders` |
| 金币/优惠券 | `GET /coins/balance`、`POST /coupons/redeem` |
| 用户 | `GET /users/me/history/*` |
| 商户 | `POST /merchant/products`、`POST /merchant/reindex` |

完整文档：**http://localhost:8000/docs**

---

## 项目结构

```
MetaFit/
├── backend/
│   ├── src/
│   │   ├── api/           # FastAPI 路由、认证中间件
│   │   ├── recommender/   # LangGraph RAG 推荐工作流
│   │   ├── indexing/      # 离线索引构建脚本
│   │   ├── services/      # 认证、向量索引服务
│   │   ├── cstImg/        # 虚拟试穿（图生图）
│   │   ├── img2model/     # 图生 3D（Tripo3D）
│   │   ├── database.py    # MySQL 连接池
│   │   └── config.py      # 全局配置
│   ├── scripts/
│   │   ├── apply_schema.py          # 应用 sql/metafit.sql
│   │   ├── import_products_to_db.py # CSV → MySQL 商品导入
│   │   ├── rebuild_index_from_db.py # MySQL → 向量索引重建
│   │   └── run_rec_eval.py          # 检索离线评估
│   ├── eval/              # Golden set 与评估结果
│   └── data/              # CSV 数据集与 indexes/
├── frontend/
│   ├── assets/            # GLB 场景、天空盒、广告视频等静态资源
│   └── src/
│       ├── pages/         # 首页、商品详情、个人中心
│       ├── fitting-room/  # 3D 试衣间入口页
│       ├── merchant/      # 商户管理后台
│       ├── shared/        # 认证、API 客户端、导航组件
│       └── js/            # Three.js 场景与试衣间逻辑模块
├── sql/metafit.sql        # MySQL 完整 schema（17 张表）
├── .env.example           # 环境变量模板
└── pyproject.toml         # 项目依赖与工具配置
```

---

## 安装与启动

### 环境要求

- Python **3.12+**
- MySQL **8.0+**
- [`uv`](https://github.com/astral-sh/uv)

### 1. 克隆与配置

```bash
git clone <repo-url>
cd MetaFit
cp .env.example .env   # 填写 API Key 与 MySQL 配置
```

### 2. 关键环境变量

| 变量 | 用途 |
|------|------|
| `LAOZHANG_GPT_API_KEY` | LLM 对话与检索解析 |
| `LAOZHANG_IMAGE_API_KEY` | 虚拟试穿 |
| `TRIPO_API_KEY` | 图生 3D |
| `MYSQL_*` | 数据库连接 |
| `JWT_SECRET_KEY` | JWT 签名密钥 |

### 3. 安装依赖

```bash
uv python install
uv sync --all-extras
```

### 4. 数据库与商品数据

```bash
python backend/scripts/apply_schema.py
python backend/scripts/import_products_to_db.py
python backend/scripts/rebuild_index_from_db.py
```

### 5. 启动服务

```powershell
cd backend
$env:PYTHONPATH = "."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 6. 访问应用

| 页面 | 地址 |
|------|------|
| 首页 | http://localhost:8000/MetaClothesShop |
| 试衣间 | http://localhost:8000/fitting-room |
| 个人中心 | http://localhost:8000/profile |
| 商户后台 | http://localhost:8000/merchant |
| API 文档 | http://localhost:8000/docs |

### 7. 推荐评估（可选）

```bash
python backend/scripts/run_rec_eval.py
```

详见 `backend/eval/README.md`。

---

## 设计亮点

1. **多路召回 + 精排** — 语义、关键词、Self-Query、Cross-Encoder 互补
2. **多轮对话** — Query Rewrite 还原完整购物意图
3. **数据库驱动** — 商品与行为数据持久化，索引可从 DB 重建
4. **模块化 LangGraph** — 节点可独立替换与调试
5. **端到端体验** — 浏览 → 对话 → 试穿 → 3D → 加购 → 下单

---

## 现存限制

| 问题 | 说明 |
|------|------|
| 外部 API 依赖 | GPT、Gemini、Tripo3D 成本与延迟不可控 |
| 商品规模较小 | 约 100+ SKU；评估采用规则标注 |
| 购物车按 session | 非用户级统一购物车 |
| 安全 | 生产环境务必修改 `JWT_SECRET_KEY` |

---

## 未来工作

- 人工标注 Golden set 与用户实验
- 桌面 3D 体验稳定后再启用 WebXR
- 登录后浏览历史回填、用户级购物车合并
- 时尚领域专用嵌入模型
- 对接真实商户实时 API

---

<div align="center">

[**↑ Back to English ↑**](#english)

</div>
