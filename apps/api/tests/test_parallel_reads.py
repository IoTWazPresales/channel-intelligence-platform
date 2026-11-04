"""Test doubles stay on the session they were given."""

from __future__ import annotations

import asyncio

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
