"""Share slow, slowly-changing reads between requests (stale-while-revalidate).

The Brief badge is read by every page. Its sell-through and listing counts take seconds to
build and move on the scale of imports, not clicks. A value younger than ``fresh_seconds`` is
returned as is. A value up to ``stale_seconds`` old is returned at once while one background
load replaces it. Cold or expired keys wait for one load that every concurrent caller shares.
A load that returns ``None`` (a skipped or failed read) is never kept.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any

Loader = Callable[[], Awaitable[Any]]


class StaleWhileRevalidate:
    def __init__(
        self,
        *,
        fresh_seconds: float,
        stale_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fresh = float(fresh_seconds)
        self._stale = max(float(stale_seconds), self._fresh)
        self._clock = clock
        self._store: dict[Hashable, tuple[float, Any]] = {}
        self._inflight: dict[Hashable, asyncio.Task[Any]] = {}

    def clear(self) -> None:
        self._store.clear()

    def _start(self, key: Hashable, loader: Loader) -> asyncio.Task[Any]:
        task = self._inflight.get(key)
        if task is not None and not task.done():
            return task

        async def _load() -> Any:
            try:
                value = await loader()
                if value is not None:
                    self._store[key] = (self._clock(), value)
                return value
            finally:
                self._inflight.pop(key, None)

        task = asyncio.ensure_future(_load())
        self._inflight[key] = task
        # A background refresh nobody awaits must not log "exception was never retrieved".
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        return task

    async def get(self, key: Hashable, loader: Loader) -> Any:
        hit = self._store.get(key)
        if hit is not None:
            age = self._clock() - hit[0]
            if age < self._fresh:
                return hit[1]
            if age < self._stale:
                self._start(key, loader)
                return hit[1]
        # shield: one caller going away must not cancel the load the others wait on
        return await asyncio.shield(self._start(key, loader))
