"""Sessions that already hold the rows under test stay on that session."""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.parallel_reads import gather_reads


class _Double:
    pass


def test_gather_reads_keeps_a_test_double_on_one_session() -> None:
    db = _Double()
    seen: list[object] = []

    async def reader(session: object) -> int:
        seen.append(session)
        return len(seen)

    async def run() -> list[int]:
        return await gather_reads(db, reader, reader)

    assert asyncio.run(run()) == [1, 2]
    assert seen == [db, db]


def test_gather_reads_keeps_a_connection_bound_session() -> None:
    """An AsyncSession bound to one connection must not open a second one.

    The on-the-water fixture seeds rows in an open transaction and hands the
    request that same connection. A pooled session cannot see those rows.
    """
    url = os.environ.get("DATABASE_URL", "")
    if "/cip_test" not in url:
        pytest.skip("cip_test only")

    async def run() -> None:
        eng = create_async_engine(url)
        try:
            async with eng.connect() as conn:
                db = AsyncSession(
                    bind=conn,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                assert type(db.bind).__name__ == "AsyncConnection"
                seen: list[object] = []

                async def reader(session: object) -> str:
                    seen.append(session)
                    return "same"

                assert await gather_reads(db, reader) == ["same"]
                assert seen == [db]
                await db.close()
        finally:
            await eng.dispose()

    asyncio.run(run())
