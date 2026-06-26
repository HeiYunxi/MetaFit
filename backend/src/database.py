"""
MySQL 异步连接池（aiomysql）。

提供全局连接池的单例获取，所有后端 API 通过此模块访问 metafit 数据库。
"""

import asyncio
from typing import Any

import aiomysql
from loguru import logger

from src.config import settings

_pool: aiomysql.Pool | None = None
_lock = asyncio.Lock()


async def get_pool() -> aiomysql.Pool:
    """获取或创建全局 MySQL 连接池（线程安全）。"""
    global _pool
    if _pool is not None:
        return _pool

    async with _lock:
        if _pool is not None:
            return _pool
        logger.info("[db] Creating MySQL connection pool → %s:%s/%s",
                    settings.MYSQL_HOST, settings.MYSQL_PORT, settings.MYSQL_DB)
        _pool = await aiomysql.create_pool(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DB,
            charset="utf8mb4",
            autocommit=True,
            minsize=2,
            maxsize=10,
            pool_recycle=3600,
        )
    return _pool


async def close_pool() -> None:
    """关闭连接池（应用退出时调用）。"""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("[db] MySQL connection pool closed.")


async def execute(sql: str, args: tuple | None = None) -> int:
    """执行 INSERT/UPDATE/DELETE，返回受影响行数。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return cur.rowcount


async def fetchone(sql: str, args: tuple | None = None) -> dict[str, Any] | None:
    """查询单行，返回字典或 None。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


async def fetchall(sql: str, args: tuple | None = None) -> list[dict[str, Any]]:
    """查询多行，返回字典列表。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchall()


async def fetchval(sql: str, args: tuple | None = None) -> Any:
    """查询单个值（如 COUNT(*)）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            row = await cur.fetchone()
            return row[0] if row else None


async def insert_and_get_id(sql: str, args: tuple | None = None) -> int:
    """执行 INSERT 并返回自增 ID。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return cur.lastrowid


async def execute_many(sql: str, args_list: list[tuple]) -> int:
    """批量执行 INSERT，返回受影响行数。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, args_list)
            return cur.rowcount
