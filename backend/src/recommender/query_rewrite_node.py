"""
多轮对话查询改写节点。

当用户发出跟进式、模糊的问题（如"要红色的""便宜一点"），
这个节点会把它结合历史对话改写成完整的独立查询（如"推荐女士红色长裙"），
确保后续检索和 RAG 能正确理解用户真实意图。

工作流位置：graph 最前端，先于 check_topic 执行。
"""

import os
import sys

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from loguru import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.recommender.state import RecState

# 最多取最近几轮历史（防止 context 过长）
_MAX_HISTORY_TURNS = 3

# 出现这些词大概率是跟进/精炼问题，需要走 LLM 改写。
# 包含：常见代词、修饰修订词、口语化的"换/再/也/价格/颜色/尺码"等。
_REFINEMENT_HINTS = (
    # 中文代词与修订词
    "它", "这", "那", "这些", "那些",
    "换", "再", "也", "继续", "另外", "其它", "其他",
    "便宜", "贵", "价格", "降", "升", "更",
    "颜色", "红", "蓝", "黑", "白", "黄", "绿", "灰", "粉", "紫",
    "尺码", "尺寸", "码", "大点", "小点",
    # 英文常见代词与修订词
    "it", "this", "that", "these", "those",
    "cheaper", "expensive",
    "instead", "another", "also",
    "smaller", "larger", "bigger",
)


def _needs_rewrite(query: str) -> bool:
    """是否需要 LLM 改写。

    判定规则（命中任意一项即认为是"独立查询"，跳过 LLM）：
    - 长度 < 4：极短追问（"红色"、"便宜点"），必须改写
    - 含明显跟进/修订关键词：必须改写
    - 否则：默认认为已经是独立查询，跳过 LLM
    """
    text = query.strip()
    if len(text) <= 4:
        return True
    lower = text.lower()
    for hint in _REFINEMENT_HINTS:
        if hint in text or hint in lower:
            return True
    return False

_REWRITE_SYSTEM_PROMPT = """\
你是一个对话查询改写助手，服务于多轮时尚商品推荐场景。

任务：根据对话历史，把用户当前的跟进问题改写成一个完整、独立的时尚商品搜索查询。

规则：
1. 如果当前问题本身已经完整清晰（不依赖历史上下文），原样输出
2. 如果是跟进或精炼问题，结合历史中的品类、属性、约束，补全成完整查询
3. 只输出改写后的查询本身，不要任何解释、标点前缀或多余文字
4. 保留用户已有的所有约束（颜色、价格、尺码、品类等），再叠加新约束

示例：
历史：用户: 推荐女士长裙  助手: 这里有几款...
当前：要红色的
输出：推荐女士红色长裙

历史：用户: 推荐女士红色长裙  助手: 这里有...
当前：价格低于1000
输出：推荐价格低于1000元的女士红色长裙

历史：用户: 推荐女士红色长裙  助手: ...  用户: 推荐价格低于1000元的女士红色长裙  助手: ...
当前：换成连衣裙
输出：推荐价格低于1000元的女士红色连衣裙\
"""

_REWRITE_HUMAN_PROMPT = """\
对话历史：
{history}

当前查询：{query}\
"""


def _format_history(history: list[dict]) -> str:
    """把最近 N 轮历史格式化成可读文本。"""
    recent = history[-(_MAX_HISTORY_TURNS * 2):]  # 每轮 2 条（user + assistant）
    lines = []
    for h in recent:
        role = "用户" if h["role"] == "user" else "助手"
        lines.append(f"{role}: {h['content']}")
    return "\n".join(lines)


def query_rewrite(state: RecState) -> RecState:
    """
    根据历史对话把当前查询改写为完整独立的查询。

    第一轮（conversation_history 为空）时直接跳过，不调用 LLM，节省成本。
    只有在有历史上下文时才真正执行改写。
    """
    history: list[dict] = state.get("conversation_history") or []
    current_query: str = state["query"]

    # 首轮：没有历史，无需改写
    if not history:
        logger.info(f"[query_rewrite] 首轮查询，跳过改写: {current_query!r}")
        return state

    # 规则前置：如果当前查询看起来已经独立、没有跟进/代词信号，
    # 直接跳过 LLM 调用，省一次 GPT 请求。
    if not _needs_rewrite(current_query):
        logger.info(f"[query_rewrite] 查询无明显跟进信号，跳过 LLM 改写: {current_query!r}")
        return state

    history_text = _format_history(history)
    logger.info(f"[query_rewrite] 历史轮数={len(history)//2}，尝试改写: {current_query!r}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", _REWRITE_SYSTEM_PROMPT),
        ("human", _REWRITE_HUMAN_PROMPT),
    ])

    api_key = settings.LAOZHANG_GPT_API_KEY.get_secret_value() or None
    llm = ChatOpenAI(
        model=settings.LAOZHANG_GPT_MODEL,
        temperature=0,
        base_url=settings.LAOZHANG_GPT_BASE_URL,
        api_key=api_key,
    )

    try:
        result = (prompt | llm).invoke({"history": history_text, "query": current_query})
        rewritten = result.content.strip()

        if rewritten and rewritten != current_query:
            logger.info(f"[query_rewrite] 改写成功: {current_query!r} → {rewritten!r}")
            state["query"] = rewritten
        else:
            logger.info(f"[query_rewrite] 查询无需改写，保持原样: {current_query!r}")
    except Exception as e:
        # 改写失败不阻断流程，降级使用原始查询
        logger.warning(f"[query_rewrite] 改写失败，使用原始查询: {e}")

    return state
