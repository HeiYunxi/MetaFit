"""
将 processed_data.csv（Farfetch 清洗数据）导入 MySQL `products` 表，统一为唯一数据源。

- 通过 farfetch_id 唯一键幂等：重复运行只更新、不重复插入。
- 同步生成 page_content（与 merchant 创建商品逻辑一致），供后续向量索引重建复用。
- 解析 "Available Sizes" 写入 product_sizes。

用法（在仓库根目录）：
    set PYTHONPATH=backend   (Windows: $env:PYTHONPATH="backend")
    python backend/scripts/import_products_to_db.py
或直接：
    python backend/scripts/import_products_to_db.py --csv backend/data/processed_data.csv
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import pymysql

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import settings  # noqa: E402

_SIZE_CATEGORY = {
    "letter": {"XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL"},
    "one_size": {"ONE SIZE", "ONESIZE", "OS"},
}


def _f(val) -> str:
    return (val or "").strip()


def _to_decimal(val):
    s = str(val or "").replace(",", "").replace("%", "").strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _generate_page_content(row: dict, sizes: list[str]) -> str:
    parts = [_f(row.get("Product Name"))]
    if _f(row.get("Brand")):
        parts.append(f"Brand: {_f(row.get('Brand'))}")
    if _f(row.get("Label")):
        parts.append(f"Category: {_f(row.get('Label'))}")
    if _f(row.get("Description")):
        parts.append(_f(row.get("Description")))
    if _f(row.get("Composition Outer")):
        parts.append(f"Outer: {_f(row.get('Composition Outer'))}")
    if _f(row.get("Composition Lining")):
        parts.append(f"Lining: {_f(row.get('Composition Lining'))}")
    if _f(row.get("Washing Instructions")):
        parts.append(f"Care: {_f(row.get('Washing Instructions'))}")
    if sizes:
        parts.append(f"Sizes: {', '.join(sizes)}")
    return ". ".join(p for p in parts if p)


def _parse_sizes(raw: str) -> list[str]:
    if not raw:
        return []
    tokens = re.split(r"[,/|]", raw)
    out = []
    for t in tokens:
        s = t.strip().upper().replace("SIZE:", "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _size_category(label: str) -> str:
    up = label.upper()
    if up in _SIZE_CATEGORY["one_size"]:
        return "one_size"
    if up in _SIZE_CATEGORY["letter"]:
        return "letter"
    if up.isdigit():
        return "number"
    return "letter"


def _normalize_farfetch_id(val: str) -> str | None:
    s = _f(val)
    if not s or s.lower() == "nan":
        return None
    # CSV 中常见 "33858800.0" 这种浮点串，去掉尾部 .0
    if s.endswith(".0"):
        s = s[:-2]
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=settings.PROCESSED_DATA_PATH)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[import] CSV not found: {csv_path}")
        sys.exit(1)

    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DB,
        charset="utf8mb4",
        autocommit=False,
    )
    inserted, updated, sized = 0, 0, 0
    try:
        with conn.cursor() as cur, open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = _f(row.get("Product Name"))
                if not name:
                    continue
                sizes = _parse_sizes(_f(row.get("Available Sizes")))
                page_content = _generate_page_content(row, sizes)
                farfetch_id = _normalize_farfetch_id(row.get("Farfetch ID"))

                cur.execute(
                    """
                    INSERT INTO products
                        (merchant_id, farfetch_id, brand_style_id, product_name, brand, label,
                         description, price, currency, original_price, discount_percentage,
                         image_url, product_url, composition_outer, composition_lining,
                         washing_instructions, model_info, page_content, is_active)
                    VALUES
                        (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                    ON DUPLICATE KEY UPDATE
                        brand_style_id=VALUES(brand_style_id), product_name=VALUES(product_name),
                        brand=VALUES(brand), label=VALUES(label), description=VALUES(description),
                        price=VALUES(price), currency=VALUES(currency),
                        original_price=VALUES(original_price), discount_percentage=VALUES(discount_percentage),
                        image_url=VALUES(image_url), product_url=VALUES(product_url),
                        composition_outer=VALUES(composition_outer), composition_lining=VALUES(composition_lining),
                        washing_instructions=VALUES(washing_instructions), model_info=VALUES(model_info),
                        page_content=VALUES(page_content), is_active=1
                    """,
                    (
                        farfetch_id,
                        _f(row.get("Brand Style ID")) or None,
                        name,
                        _f(row.get("Brand")),
                        _f(row.get("Label")),
                        _f(row.get("Description")) or None,
                        _to_decimal(row.get("Price")) or 0.0,
                        _f(row.get("Currency")) or "CNY",
                        _to_decimal(row.get("Original Price")),
                        _to_decimal(row.get("Discount Percentage")),
                        _f(row.get("Image URL")),
                        _f(row.get("Product URL")),
                        _f(row.get("Composition Outer")),
                        _f(row.get("Composition Lining")),
                        _f(row.get("Washing Instructions")) or None,
                        _f(row.get("Model Info")),
                        page_content,
                    ),
                )
                # rowcount: 1=insert, 2=update(on duplicate)
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1

                # 解析 product_id（无论新插入还是更新）
                if farfetch_id:
                    cur.execute("SELECT id FROM products WHERE farfetch_id=%s", (farfetch_id,))
                else:
                    cur.execute(
                        "SELECT id FROM products WHERE product_name=%s ORDER BY id DESC LIMIT 1",
                        (name,),
                    )
                pid_row = cur.fetchone()
                if not pid_row:
                    continue
                product_id = pid_row[0]

                # 重写尺码（全量替换）
                cur.execute("DELETE FROM product_sizes WHERE product_id=%s", (product_id,))
                for s in sizes:
                    cur.execute(
                        "INSERT IGNORE INTO product_sizes (product_id, size_label, size_category, stock_status) "
                        "VALUES (%s, %s, %s, 'in_stock')",
                        (product_id, s[:32], _size_category(s)),
                    )
                    sized += 1

        conn.commit()
    finally:
        conn.close()

    print(f"[import] done: inserted={inserted}, updated={updated}, size_rows={sized}")


if __name__ == "__main__":
    main()
