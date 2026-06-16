"""
推荐接口路由。

职责：
- 在应用启动时初始化 LangGraph 推荐图
- 为每个用户维护 `thread_id`，让多轮对话能复用图状态
- 把图返回的商品结构规范化成前端更容易消费的 JSON
"""

import warnings
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from loguru import logger
from pydantic import BaseModel

warnings.filterwarnings("ignore")


router = APIRouter(prefix="/recommend", tags=["Recommender"])

# 推荐图由 main.py 的 lifespan 钩子构建并通过 set_graph_app 注入，
# 这样 router 模块本身不直接依赖 LangGraph 初始化，方便单测与重用。
graph_app = None


def set_graph_app(app) -> None:
    """由 FastAPI lifespan 注入已构建好的推荐图实例。"""
    global graph_app
    graph_app = app


class QuestionRequest(BaseModel):
    """
    Request model for a question.
    """

    question: str


def normalize_products(products: list[dict] | None) -> list[dict]:
    """统一商品字段，保证不同前端拿到稳定的响应结构。"""
    if not products:
        return []

    normalized_products = []
    for product in products:
        normalized_products.append(
            {
                "product_name": product.get("product_name", ""),
                "brand": product.get("brand", ""),
                "label": product.get("label", ""),
                "description": product.get("description", ""),
                "price": product.get("price", 0.0),
                "currency": product.get("currency", ""),
                "original_price": product.get("original_price", 0.0),
                "discount_percentage": product.get("discount_percentage", 0.0),
                "available_sizes": product.get("available_sizes", ""),
                "composition_outer": product.get("composition_outer", ""),
                "composition_lining": product.get("composition_lining", ""),
                "washing_instructions": product.get("washing_instructions", ""),
                "model_info": product.get("model_info", ""),
                "product_url": product.get("product_url", ""),
                "image_url": product.get("image_url", ""),
                "farfetch_id": product.get("farfetch_id", ""),
                "brand_style_id": product.get("brand_style_id", ""),
            }
        )
    return normalized_products


def get_or_create_thread_id(
    request: Request,
    thread_id: Optional[str] = Cookie(default=None),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
) -> str:
    """
    获取或创建用户会话 ID。

    优先级：
    1. 浏览器 cookie（Streamlit / WebXR）
    2. `X-Session-Id` header（移动客户端，cookie 不友好）
    3. 全部缺失时新建一个 UUID，并通过 Set-Cookie 回写给浏览器客户端

    这个 ID 会传给 LangGraph 的 configurable 配置，用于关联 MemorySaver 中的状态。
    """
    if thread_id:
        return thread_id
    if x_session_id:
        # header 路径不需要回写 cookie，客户端自己负责持久化
        return x_session_id
    logger.info("Creating new thread ID for the user session.")
    new_id = str(uuid4())
    request.state.new_thread_id = new_id  # mark for setting cookie
    return new_id


@router.post("/", response_model=dict)
def get_chat_response(
    request: Request,
    response: Response,
    body: QuestionRequest,
    thread_id: str = Depends(get_or_create_thread_id),
):
    try:
        # 首次访问时把新 thread_id 回写到 cookie，后续请求就能走同一会话上下文。
        if hasattr(request, "state") and hasattr(request.state, "new_thread_id"):
            response.set_cookie("thread_id", request.state.new_thread_id)

        config = {"configurable": {"thread_id": thread_id}}
        result = graph_app.invoke({"query": body.question}, config=config)

        recommendation = result.get("recommendation", "No recommendation found.")
        products = normalize_products(result.get("product_items"))
        return {
            "question": body.question,
            "thread_id": thread_id,
            "answer": recommendation,
            "products": products,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
