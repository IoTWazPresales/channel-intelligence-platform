"""Run independent reads at the same time without sharing one database session.

SQLAlchemy's async session allows one operation at a time. Brief and cover each
wait on several reads that do not depend on each other. A real request session
opens one session per read so those waits overlap. A test double is not an
``AsyncSession`` and already holds the rows under test, so those reads stay on
that session, one after another.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

Reader = Callable[[Any], Awaitable[Any]]


async def gather_reads(db: Any, *readers: Reader) -> list[Any]:
    """Return each reader's result. Order matches ``readers``."""
    if not isinstance(db, AsyncSession):
        return [await reader(db) for reader in readers]

    async def _one(reader: Reader) -> Any:
        async with AsyncSessionLocal() as extra:
            try:
                return await reader(extra)
            finally:
                await extra.rollback()

    return list(await asyncio.gather(*(_one(reader) for reader in readers)))
