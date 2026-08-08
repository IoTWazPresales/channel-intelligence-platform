"""BACKLOG-125/126 remediation helpers."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_preview_backlog_125_126_shape():
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_distributor_as_customer_remediation import (
        preview_backlog_125_126,
    )

    async with AsyncSessionLocal() as db:
        prev = await preview_backlog_125_126(db)
        assert prev["open_channel_customer_id"] == 1
        assert 4145 in prev["absorb_loser_ids"]
        assert 1152 in prev["absorb_loser_ids"]
        assert prev["smd_policy"].startswith("customer_token_leave")
        assert "syntech" in prev["stamp_tokens"]
        # after apply: superdisti alias present
        assert prev["superdisti_alias"] is not None
        assert prev["superdisti_alias"]["distributor_id"] == 50


@pytest.mark.anyio
async def test_ensure_distributor_alias_idempotent():
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_distributor_as_customer_remediation import (
        ensure_distributor_alias,
    )

    async with AsyncSessionLocal() as db:
        a = await ensure_distributor_alias(
            db,
            None,
            distributor_id=50,
            raw_token="superdisti",
            reason="test idempotent",
        )
        assert a["distributor_id"] == 50
        assert a["normalized_token"] == "superdisti"
        b = await ensure_distributor_alias(
            db,
            None,
            distributor_id=50,
            raw_token="superdisti",
            reason="test idempotent",
        )
        assert b["created"] is False
        assert int(b["alias_id"]) == int(a["alias_id"])
        await db.rollback()


@pytest.mark.anyio
async def test_syntech_lines_are_oc_plus_syntech_dist():
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    """
            SELECT customer_id, distributor_id, count(*) n
            FROM commercial_lineup_line
            WHERE lower(trim(customer_token)) = 'syntech'
            GROUP BY 1, 2
            """
                )
            )
        ).all()
        assert rows, "expected syntech lines"
        for customer_id, distributor_id, _n in rows:
            assert int(customer_id) == 1
            assert int(distributor_id) == 51


@pytest.mark.anyio
async def test_smd_left_unresolved():
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        n = (
            await db.execute(
                text(
                    """
            SELECT count(*) FROM commercial_lineup_line
            WHERE lower(trim(customer_token)) = 'smd' AND customer_id IS NULL
            """
                )
            )
        ).scalar()
        assert int(n or 0) >= 1
