"""
推荐图共享状态定义。

每个节点都会在这个状态对象上读写字段，因此这里相当于整条推荐链路的隐式契约。
"""

from typing import Any, TypedDict


class RecState(TypedDict):
    """
    LangGraph 运行时状态。

    Attributes:
    -----------
    query: str
        当前用户输入（经 query_rewrite 节点改写后变为完整独立查询）。
    on_topic: str
        主题判断结果，实际使用的是 "Yes"/"No" 字符串。
    recommendation: str
        The LLM recommendation.
    products: str
        The retrieved products formatted as text for the RAG prompt.
    product_items: list[dict[str, Any]]
        The retrieved products in structured form for API/UI consumers.
    self_query_state: str
        self-query 召回结果状态，例如 "success" 或 "empty"。
    conversation_history: list[dict]
        多轮对话历史，每条记录格式为 {"role": "user"|"assistant", "content": str}。
        由 rag_recommender 在每轮成功推荐后追加，被 query_rewrite 节点读取来改写跟进查询。
        MemorySaver 会在同一 thread_id 下跨请求持久化这个字段。
    """

    query: str
    on_topic: str
    recommendation: str
    products: str
    product_items: list[dict[str, Any]]
    self_query_state: str
    conversation_history: list[dict]
