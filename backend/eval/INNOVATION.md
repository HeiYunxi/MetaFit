# MetaFit — Innovation Points (Thesis)

> Systems/integration contribution with measurable evidence.  
> Run `python backend/scripts/run_rec_eval.py` to refresh retrieval metrics in `backend/eval/results/latest.md`.

---

## 1. End-to-end multimodal fashion commerce loop

- **Claim**: MetaFit unifies *conversational recommendation → virtual try-on → image-to-3D → WebXR fitting room* in one product flow, not as isolated demos.
- **Evidence**:
  - LangGraph pipeline: `query_rewrite → check_topic → self_query_retrieve → ranker (fallback) → RAG` (`backend/src/recommender/graph.py`).
  - Try-on persists to `tryon_records` with local image URLs (`backend/src/cstImg/router.py`, `/uploads/tryon`).
  - 3D tasks persist to `img2model_tasks`; profile history deep-links to `/fitting-room?model=&session=` (`frontend/src/js/main.js`).
  - User journey: home grid → product detail → fitting room → profile generation history.

---

## 2. Hybrid retrieval with structured self-query + cross-encoder fallback

- **Claim**: Combines dense (FAISS), sparse (BM25), metadata filtering (Chroma self-query), and cross-encoder reranking in a tiered architecture.
- **Evidence**:
  - Index artifacts: FAISS, BM25 pickle, Chroma `product_collection`, cross-encoder reranker (`backend/src/services/vector_index_service.py`).
  - Self-query metadata schema: price, brand, label, per-size boolean fields (`backend/src/recommender/utils.py` `ATTRIBUTE_INFO`).
  - Conditional routing: self-query empty → ranker fallback (`graph.py` lines 99–104).
  - **Quantitative** (catalog N=107, 18 eval queries): Ensemble (B2) Recall@5 **0.465** / NDCG@5 **0.654**; +Rerank (B3) NDCG@5 **0.706** (+8% vs B2) at similar MRR (`backend/eval/results/latest.md`).

---

## 3. Database-backed catalog with near-real-time search index updates

- **Claim**: MySQL is the single source of truth; merchants can add products and have them searchable without full service restart.
- **Evidence**:
  - Product import & index rebuild from DB (`backend/scripts/import_products_to_db.py`, `rebuild_index_from_db.py`).
  - On create/update: `add_single_document` → Chroma incremental upsert + cache invalidation (`merchant.py` `_index_product_chroma`).
  - Full rebuild runs in **background thread pool**; API returns immediately (`merchant.py` `_run_full_reindex_task`).
  - `doc_to_product_item` injects `product_id` for cart/detail/deep links (`backend/src/recommender/utils.py`).

---

## 4. Session-aware personalization and history continuity

- **Claim**: Anonymous and logged-in users share one session thread; history (browse, try-on, 3D, chat) attaches to the user after login.
- **Evidence**:
  - `ensure_session` bridges cookie `thread_id` ↔ `sessions.user_id` (`backend/src/api/session_utils.py`).
  - Login sends `X-Session-Id` header (`frontend/src/shared/auth.js`).
  - Profile APIs: `/users/me/history/tryons`, `3dmodels`, `recommendations`, `messages` (`backend/src/api/routers/users.py`).
  - Default full-body photo auto-loaded in fitting room (`frontend/src/js/ui.js` `resolvePersonImage`).

---

## 5. Immersive WebXR storefront as recommendation surface

- **Claim**: Recommendations are not only a chat sidebar — users walk a 3D shop, trigger zone-based re-recommendation, and view generated avatars in-scene.
- **Evidence**:
  - Three.js scene loads `ClothesShop_optimized.glb` (`frontend/src/js/scene.js`, `config.js`).
  - Zone entry callbacks re-invoke recommender; generated GLB loads in 3D Showcase (`frontend/src/js/player.js`, `ui.js` `loadModel`).

---

## 6. Merchant-operable catalog and index lifecycle

- **Claim**: Merchants self-serve product CRUD, image upload, and index maintenance without developer intervention.
- **Evidence**:
  - Merchant portal: product list/edit, `POST /merchant/products`, image upload (`frontend/src/merchant/`).
  - `index_rebuild_log` audit table; rebuild status API + polling UI (`dashboard.js` `pollRebuild`).
  - Role-gated routes via `require_role("merchant", "admin")` (`backend/src/api/middleware/auth.py`).

---

## Positioning vs. “component assembly”

| Aspect | Off-the-shelf | MetaFit contribution |
|--------|---------------|----------------------|
| Models | LangChain, FAISS, Tripo, Gemini image API | Orchestration graph, fallback routing, cache hot-reload |
| Data | Farfetch CSV | MySQL SSOT + DB-driven index rebuild |
| UX | Typical e-commerce OR chatbot | Unified 2D shop + 3D fitting room + history deep-links |
| Evaluation | Often none | Reproducible offline retrieval benchmark (`backend/eval/`) |

**Suggested thesis sentence**:  
*We present MetaFit, an integrated multimodal fashion assistant that couples hybrid RAG retrieval with virtual try-on and WebXR presentation, and demonstrate retrieval gains through offline ablation on a curated query set.*

---

## Evidence still recommended before defense

1. Run final eval after full catalog import → attach `latest.md` to thesis.
2. Optional: 10–15 user study (Likert on recommendation relevance + try-on realism).
3. Demo fallback: recorded happy-path video if external APIs fail during live demo.
