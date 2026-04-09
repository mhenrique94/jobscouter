from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

TaskType = Literal["ingest", "analyze", "cleanup"]
TaskStatus = Literal["running", "done", "error"]


@dataclass
class TaskState:
    id: str
    type: TaskType
    status: TaskStatus = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    detail: str = ""


class TaskRegistry:
    """
    Registro em memória de tasks em execução.

    Thread-safe via Lock porque _run_assertiveness_cleanup_sync é uma função
    síncrona e roda em thread pool — fora do event loop do asyncio. Sem o lock,
    essa thread poderia modificar _tasks ao mesmo tempo em que o endpoint SSE
    (que roda no event loop) lê o snapshot.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}
        self._lock = threading.Lock()

    def start(self, type: TaskType) -> str:  # noqa: A002
        task_id = uuid4().hex[:8]
        with self._lock:
            self._tasks[task_id] = TaskState(id=task_id, type=type)
        return task_id

    def update(self, task_id: str, detail: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].detail = detail

    def finish(self, task_id: str, status: TaskStatus = "done") -> None:
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = status
                task.ended_at = datetime.now(UTC)
            self._evict_finished_locked()

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [
                {"id": t.id, "type": t.type, "status": t.status, "detail": t.detail}
                for t in self._tasks.values()
            ]

    def _evict_finished_locked(self, max_age_s: int = 30) -> None:
        """Remove tasks concluídas há mais de max_age_s segundos. Deve ser chamado com self._lock adquirido."""
        now = datetime.now(UTC)
        stale = [
            k
            for k, v in self._tasks.items()
            if v.status != "running"
            and v.ended_at is not None
            and (now - v.ended_at).total_seconds() > max_age_s
        ]
        for k in stale:
            del self._tasks[k]

    def evict_finished(self, max_age_s: int = 30) -> None:
        """Remove tasks concluídas há mais de max_age_s segundos."""
        with self._lock:
            self._evict_finished_locked(max_age_s)


task_registry = TaskRegistry()
