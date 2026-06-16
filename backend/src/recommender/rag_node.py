"""
RAG 推荐节点。

负责把检索结果与用户查询（以及对话历史）输入 LLM，生成自然语言推荐回复。
每轮成功推荐后，会把本轮 Q&A 追加到 conversation_history，供下一轮 query_rewrite 使用。
"""

import os
import sys

from langchain.globals import set_llm_cache
from langchain.schema.output_parser import StrOutputParser
from langchain_community.cache import InMemoryCache
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langchain_openai import ChatOpenAI
from loguru import logger

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import settings
from src.recommender.state import RecState
from src.recommender.utils import create_rag_template

# 存入 conversation_history 时截断 assistant 回复的最大字符数，
# 避免历史 context 随轮次增长过快。
_HISTORY_CONTENT_LIMIT = 400

# LLM 调用结果缓存只需要在进程内设置一次，
# 之前在 build_rag_chain 里调用会导致每次请求都重置缓存（等同于关闭）。
set_llm_cache(InMemoryCache())

# 模块级 chain 缓存，由 build_rag_chain() / warmup() 复用。
_rag_chain = None


def _build_history_section(history: list[dict]) -> str:
    """把最近两轮（4 条消息）历史格式化成 prompt 段落。"""
    if not history:
        return ""
    recent = history[-4:]  # 最近 2 轮
    lines = ["Previous conversation context (for reference):"]
    for h in recent:
        role = "User" if h["role"] == "user" else "Assistant"
        lines.append(f"  {role}: {h['content']}")
    return "\n".join(lines)


def build_rag_chain():
    """构建 RAG 链，输入 keys: docs / query / history。

    使用模块级缓存，避免每次请求都重新构造 LLM 客户端与 chain。
    """
    global _rag_chain
    if _rag_chain is not None:
        return _rag_chain

    api_key = settings.LAOZHANG_GPT_API_KEY.get_secret_value() or None
    llm = ChatOpenAI(
        model=settings.LAOZHANG_GPT_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        base_url=settings.LAOZHANG_GPT_BASE_URL,
        api_key=api_key,
    )

    prompt = create_rag_template()
    parser = StrOutputParser()

    _rag_chain = (
        RunnableParallel(
            {
                "docs": RunnableLambda(lambda x: x["docs"]),
                "query": RunnableLambda(lambda x: x["query"]),
                # history 已经是格式化好的字符串，直接透传给模板
                "history": RunnableLambda(lambda x: x["history"]),
            }
        )
        | prompt
        | llm
        | parser
    )

    return _rag_chain


def rag_recommender(state: RecState) -> RecState:
    """
    RAG 推荐节点。

    1. 用检索到的商品文本 + 当前查询 + 多轮历史，调用 LLM 生成推荐回复。
    2. 把本轮 (query, recommendation) 追加到 conversation_history，
       供下一轮 query_rewrite 节点使用。
    """
    rag_chain = build_rag_chain()
    query: str = state["query"]
    docs: str = state["products"]
    history: list[dict] = state.get("conversation_history") or []

    history_section = _build_history_section(history)
    output: str = rag_chain.invoke({"docs": docs, "query": query, "history": history_section})

    state["recommendation"] = output
    logger.info(f"[rag_recommender] 推荐生成完毕，query={query!r}")

    # 把本轮对话追加到历史，供下一轮改写使用。
    # assistant 回复截断存储，避免历史体积随轮次膨胀。
    updated_history = list(history)
    updated_history.append({"role": "user", "content": query})
    updated_history.append({"role": "assistant", "content": output[:_HISTORY_CONTENT_LIMIT]})
    state["conversation_history"] = updated_history

    return state
