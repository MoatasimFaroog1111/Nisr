from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from domain.browser import BrowserEvent


@dataclass(eq=False, slots=True)
class BrowserEventSubscription:
    session_id: str
    hub: "InMemoryBrowserEventHub"
    queue: asyncio.Queue[BrowserEvent] = field(default_factory=lambda: asyncio.Queue(maxsize=128))
    closed: bool = False

    async def receive(self) -> BrowserEvent:
        return await self.queue.get()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.hub.remove(self)


class InMemoryBrowserEventHub:
    """Process-local fan-out hub; transport-neutral and safe for multiple viewers."""

    def __init__(self):
        self._subscriptions: dict[str, set[BrowserEventSubscription]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> BrowserEventSubscription:
        subscription = BrowserEventSubscription(session_id=session_id, hub=self)
        async with self._lock:
            self._subscriptions.setdefault(session_id, set()).add(subscription)
        return subscription

    async def remove(self, subscription: BrowserEventSubscription) -> None:
        async with self._lock:
            group = self._subscriptions.get(subscription.session_id)
            if not group:
                return
            group.discard(subscription)
            if not group:
                self._subscriptions.pop(subscription.session_id, None)

    async def publish(self, event: BrowserEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscriptions.get(event.session_id, ()))
        for subscription in subscribers:
            if subscription.closed:
                continue
            if subscription.queue.full():
                try:
                    subscription.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscriber_count(self, session_id: str) -> int:
        async with self._lock:
            return len(self._subscriptions.get(session_id, ()))
