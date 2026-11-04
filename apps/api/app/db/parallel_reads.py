"""Run independent reads at the same time without sharing one database session.

SQLAlchemy's async session allows one operation at a time. Brief and cover each
wait on several reads that do not depend on each other. A request session opened
on the engine gets one pooled session per read so those waits overlap.

Two callers must keep the session they were given. A test double is not an
``AsyncSession``. A session bound to an existing connection is already inside
that connection's transaction, and a second pooled connection cannot see its
uncommitted rows (the on-the-water fixture is one of these).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

Reader = Callable[[Any], Awaitable[Any]]


def _shares_caller_connection(db: Any) -> bool:
    """True when ``db`` is tied to one connection rather than the engine pool."""
    bind = getattr(db, "bind", None)
    if bind is None:
        return False
    name = type(bind).__name__
    return name == "Connection" or name == "AsyncConnection"


async def gather_reads(db: Any, *readers: Reader) -> list[Any]:
    """Return each reader's result. Order matches ``readers``."""
    if not isinstance(db, AsyncSession) or _shares_caller_connection(db):
        return [await reader(db) for reader in readers]

    async def _one(reader: Reader) -> Any:
        async with AsyncSessionLocal() as extra:
            try:
                return await reader(extra)
            finally:
                await extra.rollback()

    return list(await asyncio.gather(*(_one(reader) for reader in readers)))
