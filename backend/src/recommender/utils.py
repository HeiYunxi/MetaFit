"""
推荐模块的通用工具函数。

这里主要放两类逻辑：
- Self-query 需要的元数据描述与 Chroma 过滤翻译器
- LangChain Document 和前端/API 商品结构之间的映射
"""

import re

from langchain.prompts import PromptTemplate
from langchain_community.query_constructors.chroma import (
    ChromaTranslator as BaseChromaTranslator,
)
from langchain_core.structured_query import Comparison


class CustomChromaTranslator(BaseChromaTranslator):
    def visit_comparison(self, comparison: Comparison):
        """
        将过滤表达式限制在 Chroma 支持的原始类型上。

        尺码不会对 `Available Sizes` 做字符串模糊匹配，
        而是依赖离线索引阶段展开出的布尔字段，例如 `Size M == true`。
        """
        return super().visit_comparison(comparison)


ATTRIBUTE_INFO = [
    {
        "name": "Product Name",
        "description": "The name of the fashion product.",
    },
    {
        "name": "Brand",
        "description": "The brand of the product.",
    },
    {
        "name": "Price",
        "description": "Current selling price of the product. Use `lt`, `lte`, `gt`, or `gte` for filtering.",
    },
    {
        "name": "Currency",
        "description": "Currency code or symbol associated with the price.",
    },
    {
        "name": "Original Price",
        "description": "Original price before discount.",
    },
    {
        "name": "Discount Percentage",
        "description": "Discount percentage applied to the product.",
    },
    {
        "name": "Label",
        "description": "High-level product category or label, such as dress, bag, shoes, or jacket.",
    },
    {
        "name": "Description",
        "description": "Detailed marketing description of the product.",
    },
    {
        "name": "Composition Outer",
        "description": "Outer material composition of the product.",
    },
    {
        "name": "Composition Lining",
        "description": "Lining material composition of the product.",
    },
    {
        "name": "Washing Instructions",
        "description": "Care and washing instructions for the product.",
    },
    {
        "name": "Model Info",
        "description": "Model measurements or fit information provided by the store.",
    },
    {
        "name": "Size XXXS",
        "description": 'Whether the product is available in size XXXS. Use `eq("Size XXXS", true)` when the user asks for XXXS.',
    },
    {
        "name": "Size XXS",
        "description": 'Whether the product is available in size XXS. Use `eq("Size XXS", true)` when the user asks for XXS.',
    },
    {
        "name": "Size XS",
        "description": 'Whether the product is available in size XS. Use `eq("Size XS", true)` when the user asks for XS.',
    },
    {
        "name": "Size S",
        "description": 'Whether the product is available in size S. Use `eq("Size S", true)` when the user asks for S or small.',
    },
    {
        "name": "Size M",
        "description": 'Whether the product is available in size M. Use `eq("Size M", true)` when the user asks for M or medium.',
    },
    {
        "name": "Size L",
        "description": 'Whether the product is available in size L. Use `eq("Size L", true)` when the user asks for L or large.',
    },
    {
        "name": "Size XL",
        "description": 'Whether the product is available in size XL. Use `eq("Size XL", true)` when the user asks for XL.',
    },
    {
        "name": "Size XXL",
        "description": 'Whether the product is available in size XXL. Use `eq("Size XXL", true)` when the user asks for XXL.',
    },
    {
        "name": "Size XXXL",
        "description": 'Whether the product is available in size XXXL. Use `eq("Size XXXL", true)` when the user asks for XXXL.',
    },
    {
        "name": "Size One Size",
        "description": 'Whether the product is available as one size. Use `eq("Size One Size", true)` when the user asks for one size.',
    },
]

DOC_CONTENT = (
    "A fashion e-commerce product including product name, brand, category, price, "
    "available sizes, description, materials, care instructions, and product metadata."
)


def get_metadata_info():
    return ATTRIBUTE_INFO, DOC_CONTENT


def _parse_product_from_page_content(page_content: str) -> dict:
    """当 metadata 缺失时，从 page_content 回退解析商品字段。"""
    result = {}
    for line in page_content.split("\n"):
        if ": " in line:
            key, _, val = line.partition(": ")
            result[key.strip()] = val.strip()
    return result


def _extract_first_number(s: str) -> float:
    """Extract first number from string like '12900 CNY' or '50%'."""
    if not s:
        return 0.0
    m = re.search(r"[\d.]+", str(s))
    return float(m.group()) if m else 0.0


def doc_to_product_item(doc) -> dict:
    """
    把 LangChain Document 转成 API/UI 能直接消费的商品字典。

    某些检索链路里 metadata 可能不完整，因此这里保留了 page_content 回退解析，
    避免前端拿到半残缺的商品信息。
    """
    metadata = doc.metadata or {}
    page_parsed = _parse_product_from_page_content(doc.page_content or "")

    def get_val(meta_key: str, page_key: str, default=""):
        v = metadata.get(meta_key)
        if v is not None and str(v).strip() != "":
            return v
        return page_parsed.get(page_key, default)

    def get_num(meta_key: str, page_key: str, default=0.0):
        v = metadata.get(meta_key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        p = page_parsed.get(page_key, "")
        return _extract_first_number(p) if p else default

    return {
        "product_id": metadata.get("product_id"),
        "product_name": get_val("Product Name", "Product Name", ""),
        "brand": get_val("Brand", "Brand", ""),
        "label": get_val("Label", "Label", ""),
        "description": get_val("Description", "Description", ""),
        "price": get_num("Price", "Price", 0.0),
        "currency": get_val("Currency", "Currency", ""),
        "original_price": get_num("Original Price", "Original Price", 0.0),
        "discount_percentage": get_num("Discount Percentage", "Discount Percentage", 0.0),
        "available_sizes": get_val("Available Sizes", "Available Sizes", ""),
        "composition_outer": get_val("Composition Outer", "Composition Outer", ""),
        "composition_lining": get_val("Composition Lining", "Composition Lining", ""),
        "washing_instructions": get_val("Washing Instructions", "Washing Instructions", ""),
        "model_info": get_val("Model Info", "Model Info", ""),
        "product_url": get_val("Product URL", "Product URL", ""),
        "image_url": get_val("Image URL", "Image URL", ""),
        "farfetch_id": get_val("Farfetch ID", "Farfetch ID", ""),
        "brand_style_id": get_val("Brand Style ID", "Brand Style ID", ""),
    }


def create_rag_template():
    """
    构建 RAG 推荐 prompt 模板。

    输入变量：
    - query   当前查询（已经过 query_rewrite 补全为完整独立查询）
    - docs    检索到的商品文本
    - history 多轮对话历史（格式化后的字符串，可为空）
    """
    prompt_template = """\
You are an intelligent fashion shopping assistant that helps users find the best products based on their query.

{history}
The user is looking for products related to: **{query}**.

Here are some available products:
{docs}

Please recommend the best products in a friendly, conversational tone. Consider the following:
- **Match with the user's preferences** such as product type, brand, price, discount, and size.
- **Use the product description, materials, and care information** when they help explain why an item fits.
- **Rank the most relevant items first** and explain each recommendation clearly.
- **If there is conversation history above**, build naturally on it — don't repeat what was already recommended unless it still fits the new request.

When possible, mention:
- product name
- brand
- current price and original price or discount
- available sizes
- label/category
- notable material or washing information

If the retrieved products are limited or only partially match, say so honestly and still suggest the closest options.
Respond in natural language as if you were personally assisting the user.
"""

    prompt = PromptTemplate(template=prompt_template, input_variables=["docs", "query", "history"])
    return prompt
