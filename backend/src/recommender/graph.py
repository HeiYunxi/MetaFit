"""
推荐主流程的 LangGraph 编排入口。

整体路由分四步：
1. `query_rewrite` 结合历史对话把跟进问题改写成完整独立查询（支持多轮追问）。
2. `check_topic` 判断查询是否属于时尚推荐域。
3. `self_query_retrieve` 优先走 Chroma + 元数据过滤做精准召回。
4. 如果 self-query 没有结果，退回 `ranker`，最后统一交给 RAG 生成回复。
"""

import os
import sys

from langchain.globals import set_debug
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from loguru import logger

# Append project root directory
# pylint: disable=wrong-import-position
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.config import settings
from src.recommender.check_topic_node import topic_classifier
from src.recommender.query_rewrite_node import query_rewrite
from src.recommender.rag_node import build_rag_chain, rag_recommender
from src.recommender.ranker_node import load_cross_encoder_model, ranker_node
from src.recommender.self_query_node import (
    build_self_query_chain,
    initialize_embeddings_model,
    load_chroma_index,
    self_query_retrieve,
)
from src.recommender.state import RecState

# 仅当日志级别显式设为 DEBUG 时才打开 LangChain 全量调试输出，避免生产环境刷屏与性能下降。
set_debug(str(settings.LOGGING_LEVEL).upper() == "DEBUG")


def warmup() -> None:
    """启动期预热：把推荐链路里所有重资源一次性加载好。

    - HuggingFace embedding 模型
    - Chroma 向量库
    - SelfQueryRetriever（包含 LLM 客户端）
    - Cross-encoder fallback ranker（几十 MB pickle）
    - RAG chain（LLM 客户端 + prompt）

    失败时不阻塞应用启动，只记录日志：缺索引或没配 API Key 时仍可让进程起来，
    具体节点在首次调用时再抛错。
    """
    logger.info("[warmup] Preloading recommender resources ...")
    try:
        embeddings = initialize_embeddings_model()
        try:
            chroma = load_chroma_index(embeddings)
            build_self_query_chain(chroma)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"[warmup] self-query 预热失败（可忽略，将在请求时重试）: {exc}")
        try:
            load_cross_encoder_model()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"[warmup] cross-encoder 预热失败（可忽略，将在请求时重试）: {exc}")
        try:
            build_rag_chain()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"[warmup] RAG chain 预热失败（可忽略，将在请求时重试）: {exc}")
        logger.info("[warmup] Done.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(f"[warmup] embedding 预热失败（可忽略，将在请求时重试）: {exc}")


def create_recommendaer_graph():
    """
    创建推荐工作流。

    `MemorySaver` 让同一 `thread_id` 下的多轮请求共享图状态（含 conversation_history），
    query_rewrite 节点利用这份历史来把追问改写成完整查询，实现多轮推荐能力。
    """
    workflow = StateGraph(RecState)

    # 注册全部节点
    workflow.add_node("query_rewrite", query_rewrite)
    workflow.add_node("check_topic", topic_classifier)
    workflow.add_node("self_query_retrieve", self_query_retrieve)
    workflow.add_node("rag_recommender", rag_recommender)
    workflow.add_node("ranker", ranker_node)

    # 固定边：query_rewrite 是每轮请求的第一步
    workflow.set_entry_point("query_rewrite")
    workflow.add_edge("query_rewrite", "check_topic")

    # 只允许时尚推荐相关的问题继续进入检索链路，减少无关问题污染状态。
    workflow.add_conditional_edges(
        "check_topic",
        lambda state: state["on_topic"],
        {"Yes": "self_query_retrieve", "No": END},
    )

    # self-query 命中则直接生成推荐；命不中再用 fallback ranker 兜底。
    workflow.add_conditional_edges(
        "self_query_retrieve",
        lambda state: state["self_query_state"],
        {"success": "rag_recommender", "empty": "ranker"},
    )

    workflow.add_edge("ranker", "rag_recommender")
    workflow.add_edge("rag_recommender", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# app = create_recommendaer_graph()

if __name__ == "__main__":
    app = create_recommendaer_graph()
    # app.get_graph().draw_mermaid_png(output_file_path="flow.png")
    # Run the workflow
    config = {"configurable": {"thread_id": "1"}}
    state = {"query": "Woman dress less than 50"}
    output = app.invoke(state, config=config)

    logger.info(output)
