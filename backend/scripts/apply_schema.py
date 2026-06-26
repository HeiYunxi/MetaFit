"""
Apply sql/metafit.sql to MySQL (CREATE TABLE IF NOT EXISTS, idempotent).

Usage: python backend/scripts/apply_schema.py
"""

import os
import sys
from pathlib import Path

import pymysql

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import settings  # noqa: E402

SCHEMA_FILE = settings.BASE_DIR.parent / "sql" / "metafit.sql"


def _split_statements(text: str) -> list[str]:
    # 去掉以 -- 开头的注释行，再按分号拆分
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def main():
    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DB,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            if not SCHEMA_FILE.is_file():
                raise FileNotFoundError(f"Schema file not found: {SCHEMA_FILE}")
            print(f"[schema] applying {SCHEMA_FILE.name}")
            for stmt in _split_statements(SCHEMA_FILE.read_text(encoding="utf-8")):
                try:
                    cur.execute(stmt)
                except Exception as e:  # noqa: BLE001
                    print(f"  ! {e}")
    finally:
        conn.close()
    print("[schema] done")


if __name__ == "__main__":
    main()
