from __future__ import annotations

import asyncio
from dataclasses import dataclass

from application.browser_runtime import BrowserService


@dataclass(slots=True)
class _StreamTask:
    task: asyncio.Task
    viewers: int = 1


class BrowserFrameStreamer:
    """Maintains one screenshot stream per session regardless of viewer count."""

    def __init__(self, service: BrowserService, interval_ms: int = 650):
        self._service = service
        self._interval = max(0.25, int(interval_ms) / 1000)
        self._tasks: dict[str, _StreamTask] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: str, user_id: str) -> None:
        async with self._lock:
            current = self._tasks.get(session_id)
            if current and not current.task.done():
                current.viewers += 1
                return
            task = asyncio.create_task(self._run(session_id, user_id), name=f"browser-frame-{session_id[:8]}")
            self._tasks[session_id] = _StreamTask(task=task)

    async def release(self, session_id: str) -> None:
        async with self._lock:
            current = self._tasks.get(session_id)
            if not current:
                return
            current.viewers -= 1
            if current.viewers > 0:
                return
            self._tasks.pop(session_id, None)
            current.task.cancel()
        try:
            await current.task
        except asyncio.CancelledError:
            pass

    async def _run(self, session_id: str, user_id: str) -> None:
        consecutive_errors = 0
        while True:
            try:
                await self._service.publish_frame(session_id, user_id)
                consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except KeyError:
                return
            except Exception:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    return
            await asyncio.sleep(self._interval)

    async def close(self) -> None:
        async with self._lock:
            tasks = [entry.task for entry in self._tasks.values()]
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
