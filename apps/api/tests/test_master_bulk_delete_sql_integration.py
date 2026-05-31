"""Integration: real AsyncSession must emit exactly 2 SQL statements for customer preview."""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import AsyncSessionLocal, engine
from app.services.db_sql_counter import sql_counter_scope
from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteTimeoutError,
    is_statement_timeout_error,
    preview_master_bulk_delete,
)


def _integration_db_allowed() -> bool:
    return os.getenv("ALLOW_TESTS_ON_DEV_DB", "1").strip() == "1"


def test_preview_real_session_exactly_two_sql_statements():
    """Proof against real DB: 1 UNION ALL ref check + 1 label SELECT (not 21 round trips)."""
    if not _integration_db_allowed():
        pytest.skip("Set ALLOW_TESTS_ON_DEV_DB=1 to run real-session SQL count tests")

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            db_name = (await db.execute(text("SELECT current_database()"))).scalar_one()
            # Read-only; uses whatever DATABASE_URL points at (local cip or dev Supabase).
            assert db_name, "could not read current_database()"

        customer_ids: list[int] = []
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text("SELECT id FROM dim_customer ORDER BY id LIMIT 6"))).all()
            customer_ids = [int(r[0]) for r in rows]
        if not customer_ids:
            pytest.skip("no dim_customer rows in cip")

        with sql_counter_scope(engine) as counter:
            t0 = time.perf_counter()
            async with AsyncSessionLocal() as db:
                payload = await preview_master_bulk_delete(db, "customers", customer_ids)
            elapsed = time.perf_counter() - t0

        assert counter.count == 2, (
            f"expected 2 SQL statements (union + labels), got {counter.count}: {counter.statements}"
        )
        first = counter.statements[0].upper()
        assert "UNION ALL" in first or "FACT_SALES_SELLOUT" in first
        assert "DIM_CUSTOMER" in counter.statements[1].upper()
        assert elapsed < 30.0, f"preview took {elapsed:.1f}s — expected under 30s with 2 SQL round trips"
        assert "entity_ids" in payload

    asyncio.run(_run())


def test_customer_breakdown_real_session_single_execute():
    if not _integration_db_allowed():
        pytest.skip("Set ALLOW_TESTS_ON_DEV_DB=1")

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("SELECT id FROM dim_customer ORDER BY id LIMIT 1"))).first()
        if not row:
            pytest.skip("no customers")
        cid = int(row[0])

        from app.services.customer_usage import customer_hard_reference_breakdown_batch

        with sql_counter_scope(engine) as counter:
            async with AsyncSessionLocal() as db:
                await customer_hard_reference_breakdown_batch(db, [cid])

        assert counter.count == 1
        assert "UNION ALL" in counter.statements[0].upper() or "FACT_" in counter.statements[0].upper()

    asyncio.run(_run())


def test_is_statement_timeout_error_pg_sqlstate():
    class Orig:
        sqlstate = "57014"

    assert is_statement_timeout_error(DBAPIError("stmt", {}, Orig()))


def test_timeout_error_maps_to_master_bulk_delete_timeout():
    exc = MasterBulkDeleteTimeoutError("timed out", phase="reference_union")
    assert exc.phase == "reference_union"
