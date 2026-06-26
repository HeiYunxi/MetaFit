"""
从 MySQL products 表重建全部推荐索引（离线执行版）。

与商家后台 /merchant/products/reindex 等价，但可直接在命令行运行，
方便首次迁移与验证。

用法（仓库根目录）：
    python backend/scripts/rebuild_index_from_db.py
重建完成后推荐器进程内缓存会自动失效（无需重启）；也可直接运行本脚本离线重建。
"""

import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import close_pool, fetchall  # noqa: E402
from src.services.vector_index_service import rebuild_indexes_from_db  # noqa: E402


async def main():
    products = await fetchall(
        "SELECT p.*, GROUP_CONCAT(ps.size_label) AS sizes "
        "FROM products p "
        "LEFT JOIN product_sizes ps ON p.id = ps.product_id "
        "WHERE p.is_active = 1 "
        "GROUP BY p.id"
    )
    print(f"[rebuild] fetched {len(products)} active products")
    count = await rebuild_indexes_from_db(products)
    print(f"[rebuild] done: {count} documents indexed")
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
