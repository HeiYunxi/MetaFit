"""异步图生 3D 任务的进程内状态表。

演示阶段直接用 dict + asyncio.Lock 就够了；
将来要做水平扩展再迁到 Redis / SQLite，调用方接口保持不变。
"""

import asyncio
from typing import Optional

from src.img2model.schemas import Img2ModelStatus


class TaskStore:
    """简单的进程内任务表，按 task_id 维护任务状态。"""

    def __init__(self) -> None:
        self._tasks: dict[str, Img2ModelStatus] = {}
        self._lock = asyncio.Lock()

    async def create(self, task_id: str) -> None:
        """新建一条 pending 记录。"""
        async with self._lock:
            self._tasks[task_id] = Img2ModelStatus(
                task_id=task_id,
                state="pending",
                progress=0,
            )

    async def update(self, task_id: str, **fields) -> None:
        """合并更新任务字段；不存在的 task_id 直接忽略，避免 race 条件抛错。"""
        async with self._lock:
            current = self._tasks.get(task_id)
            if current is None:
                return
            data = current.model_dump()
            data.update(fields)
            self._tasks[task_id] = Img2ModelStatus(**data)

    def get(self, task_id: str) -> Optional[Img2ModelStatus]:
        """同步读取一条记录（pydantic 模型自身已经 immutable，无需锁）。"""
        return self._tasks.get(task_id)


# 进程级单例，由 router 直接 import 使用。
task_store = TaskStore()
