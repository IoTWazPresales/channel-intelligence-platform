"""BACKLOG-125/126 remediation helpers.

N-0096 (BACKLOG-144): these tests read rows that only existed on the production-shaped database
(customer 1, distributor 50 and 51, 'syntech' and 'smd' lines). They now seed their own distributor,
case and lines inside one transaction on cip_test that is always rolled back, and assert the rule
(a distributor named in the customer column becomes Open Channel plus that distributor; a customer
name with no evidence is left for the picker), not the production ids.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@asynccontextmanager
async def _rolled_back_session():
    from app.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            name = (await conn.execute(text("select current_database()"))).scalar_one()
            if name != "cip_test":
                await outer.rollback()
                pytest.skip(f"remediation tests run on cip_test only (database is {name})")
            session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()


async def _open_channel_id(db: AsyncSession) -> int:
    from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id

    oc = await get_open_channel_customer_id(db)
    if oc is None:
        pytest.skip("cip_test has no Open Channel reference customer (run the system reference seed)")
    return int(oc)


async def _distributor(db: AsyncSession, name: str):
    from app.models.dimensions import DimDistributor

    row = DimDistributor(code=f"D-{uuid.uuid4().hex[:10].upper()}", name=name, distributor_status="active")
    db.add(row)
    await db.flush()
    return row


async def _lines(db: AsyncSession, token: str, n: int = 2):
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine

    case = CommercialLineupCase(
        file_name=f"n0096_{uuid.uuid4().hex[:6]}.xlsx",
        period_label="2099 Q1",
        import_intent="historical_lineup_backfill",
        source_context="n0096_test",
    )
    db.add(case)
    await db.flush()
    rows = []
    for i in range(n):
        ln = CommercialLineupLine(
            case_id=int(case.id), source_row_number=i + 1, customer_token=token, quantity_units=1.0
        )
        db.add(ln)
        rows.append(ln)
    await db.flush()
    return rows


@pytest.mark.anyio
async def test_preview_backlog_125_126_shape():
    from app.services.commercial_planner.lineup_distributor_as_customer_remediation import (
        ensure_distributor_alias,
        preview_backlog_125_126,
    )

    async with _rolled_back_session() as db:
        oc = await _open_channel_id(db)
        prev = await preview_backlog_125_126(db)
        assert prev["open_channel_customer_id"] == oc
        assert 4145 in prev["absorb_loser_ids"]
        assert 1152 in prev["absorb_loser_ids"]
        assert prev["smd_policy"].startswith("customer_token_leave")
        assert "syntech" in prev["stamp_tokens"]
        assert prev["superdisti_alias"] is None  # nothing minted yet on a clean database

        dist = await _distributor(db, f"Superdist {uuid.uuid4().hex[:6]}")
        await ensure_distributor_alias(db, None, distributor_id=int(dist.id), raw_token="superdisti", reason="test")
        after = await preview_backlog_125_126(db)
        assert after["superdisti_alias"] is not None
        assert after["superdisti_alias"]["distributor_id"] == int(dist.id)


@pytest.mark.anyio
async def test_ensure_distributor_alias_idempotent():
    from app.services.commercial_planner.lineup_distributor_as_customer_remediation import (
        ensure_distributor_alias,
    )

    async with _rolled_back_session() as db:
        dist = await _distributor(db, f"Superdist {uuid.uuid4().hex[:6]}")
        a = await ensure_distributor_alias(
            db, None, distributor_id=int(dist.id), raw_token="superdisti", reason="test idempotent"
        )
        assert a["distributor_id"] == int(dist.id)
        assert a["normalized_token"] == "superdisti"
        assert a["created"] is True
        b = await ensure_distributor_alias(
            db, None, distributor_id=int(dist.id), raw_token="superdisti", reason="test idempotent"
        )
        assert b["created"] is False
        assert int(b["alias_id"]) == int(a["alias_id"])


@pytest.mark.anyio
async def test_syntech_lines_are_oc_plus_syntech_dist():
    """A distributor named in the customer column stamps as Open Channel plus that distributor."""
    from app.services.commercial_planner.lineup_customer_token_stamp import apply_customer_token_stamp
    from app.services.imports.distributor_sales_inventory import _norm_key

    async with _rolled_back_session() as db:
        oc = await _open_channel_id(db)
        name = f"Zq Syntech {uuid.uuid4().hex[:6]}"
        dist = await _distributor(db, name)
        lines = await _lines(db, name)
        assert all(ln.customer_id is None for ln in lines)

        out = await apply_customer_token_stamp(
            db,
            None,
            norm_token=_norm_key(name),
            target_customer_id=oc,
            reason="N-0096 self-seeded distributor-as-customer",
            commit=False,
        )
        assert out["stamped_count"] == len(lines)
        rows = (
            await db.execute(
                text(
                    "SELECT customer_id, distributor_id, count(*) FROM commercial_lineup_line "
                    "WHERE customer_token = :t GROUP BY 1, 2"
                ),
                {"t": name},
            )
        ).all()
        assert [(int(c), int(d), int(n)) for c, d, n in rows] == [(oc, int(dist.id), len(lines))]


@pytest.mark.anyio
async def test_smd_left_unresolved():
    """The remediation run leaves a customer name with no customer, alias or distributor for the picker."""
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.dimensions import DimDistributor
    from app.services.commercial_planner.lineup_distributor_as_customer_remediation import (
        _SUPERDIST_ID,
        apply_backlog_125_126_async_phase,
    )

    async with _rolled_back_session() as db:
        await _open_channel_id(db)
        if await db.get(DimDistributor, _SUPERDIST_ID) is None:
            db.add(DimDistributor(id=_SUPERDIST_ID, code="N0096-SUPERDIST", name="Superdist", distributor_status="active"))
            await db.flush()
        token = f"SMD {uuid.uuid4().hex[:6]}"
        lines = await _lines(db, token)
        out = await apply_backlog_125_126_async_phase(db, None, commit=False)
        assert out["smd"] == "left_unresolved_customer_free_picker"
        got = (
            await db.execute(
                select(CommercialLineupLine.customer_id).where(CommercialLineupLine.customer_token == token)
            )
        ).scalars().all()
        assert len(got) == len(lines) and all(c is None for c in got)
