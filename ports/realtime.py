from __future__ import annotations

from typing import Protocol

from domain.browser import BrowserEvent


class BrowserEventSubscriptionPort(Protocol):
    async def receive(self) -> BrowserEvent: ...
    async def close(self) -> None: ...


class BrowserEventPublisherPort(Protocol):
    async def publish(self, event: BrowserEvent) -> None: ...


class BrowserEventStreamPort(Protocol):
    async def subscribe(self, session_id: str) -> BrowserEventSubscriptionPort: ...
