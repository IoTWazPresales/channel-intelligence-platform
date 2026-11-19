"""A real async session whose commits never reach the database (cip_test only).

Services under test often ``await db.commit()`` themselves. A plain ``AsyncSessionLocal`` session
would then persist the fixture rows and a teardown ``rollback()`` could not remove them. Here the
session is joined to an outer connection transaction with
``join_transaction_mode="create_savepoint"``: each service commit only releases a savepoint, and the
outer rollback at teardown removes everything the test wrote. Same pattern as
tests/test_lineup_distributor_as_customer_remediation.py.

``leftover_counts`` opens a separate, fresh session after teardown so a test can prove that none of
its synthetic rows survived.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def rolled_back_async_session() -> AsyncIterator[AsyncSession]:
    from app.db.session import engine

    async with engine.connect() as conn:
        name = (await conn.execute(text("select current_database()"))).scalar_one()
        await conn.rollback()
        if name != "cip_test":
            pytest.skip(f"cip_test only (database is {name})")
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


async def leftover_counts(statements: Mapping[str, Any]) -> dict[str, int]:
    """Run each ``SELECT count(*)`` in a fresh session (outside the rolled-back transaction)."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as fresh:
        try:
            return {key: int(await fresh.scalar(stmt) or 0) for key, stmt in statements.items()}
        finally:
            await fresh.rollback()
