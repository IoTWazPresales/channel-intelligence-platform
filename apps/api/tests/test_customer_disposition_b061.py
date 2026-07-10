"""BACKLOG-061-U3 — customer no-code disposition (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.customer_bulk_promote import run_customer_bulk_promote
from app.services.customer_disposition import run_customer_disposition_batch
from app.services.customer_promote import preview_customer_promote


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-CUST-ABC",
        name="Acme",
        customer_status="unverified",
        merged_into_customer_id=None,
        notes_summary=None,
        no_code_disposition=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db(rows_by_id: dict[int, SimpleNamespace]):
    db = AsyncMock()

    async def _get(_cls, pk):
        return rows_by_id.get(int(pk))

    db.get = AsyncMock(side_effect=_get)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def test_set_parked_and_clear_round_trip():
    row = _row()
    db = _db({10: row})
    out = asyncio.run(
        run_customer_disposition_batch(
            db, customer_ids=[10], disposition="parked", note="junk", dry_run=False
        )
    )
    assert out["summary"]["applied"] == 1
    assert row.no_code_disposition == "parked"
    assert row.customer_status == "unverified"
    assert "[parked]" in (row.notes_summary or "") or "parked" in (row.notes_summary or "")

    out2 = asyncio.run(
        run_customer_disposition_batch(db, customer_ids=[10], disposition="clear", dry_run=False)
    )
    assert out2["summary"]["applied"] == 1
    assert row.no_code_disposition is None
    assert row.customer_status == "unverified"


def test_idempotent_re_set_skipped():
    row = _row(no_code_disposition="excluded")
    db = _db({10: row})
    out = asyncio.run(
        run_customer_disposition_batch(
            db, customer_ids=[10], disposition="excluded", dry_run=False
        )
    )
    assert out["summary"]["skipped"] == 1
    assert "already_set:excluded" in out["rows"][0]["reasons"]


def test_non_tmp_and_merged_blocked():
    a = _row(id=1, code="REAL-1")
    b = _row(id=2, code="TMP-CUST-X", merged_into_customer_id=99)
    db = _db({1: a, 2: b})
    out = asyncio.run(
        run_customer_disposition_batch(
            db, customer_ids=[1, 2], disposition="parked", dry_run=True
        )
    )
    assert out["summary"]["blocked"] == 2
    assert "code_not_tmp_cust" in out["rows"][0]["reasons"]
    assert "row_is_merged_loser" in out["rows"][1]["reasons"]


def test_promote_blocks_disposition_row():
    row = _row(no_code_disposition="parked")
    db = _db({10: row})
    # preview uses db.get + execute for collision — stub execute empty
    async def _exec(_stmt):
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_exec)
    preview = asyncio.run(preview_customer_promote(db, customer_id=10, new_code="ACME-1"))
    assert preview["can_confirm"] is False
    assert "disposition_parked" in preview["eligibility"]["reasons"]


def test_mint_disposition_does_not_advance_next_seq():
    row = _row(no_code_disposition="excluded")
    db = _db({10: row})

    async def _exec(stmt):
        result = MagicMock()
        key = None
        try:
            for v in stmt.compile().params.values():
                if isinstance(v, str):
                    key = v.lower()
                    break
        except Exception:
            key = None
        found = row if key and key.startswith("tmp-cust-") else None
        result.scalars.return_value.first.return_value = found
        return result

    db.execute = AsyncMock(side_effect=_exec)
    settings = SimpleNamespace(next_seq=5)

    async def _fake_mint(*_a, **_k):
        settings.next_seq += 1
        return "CUST-000005", 5

    with patch(
        "app.services.customer_bulk_promote.mint_next_customer_code",
        side_effect=_fake_mint,
    ):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-ABC"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["blocked"] == 1
    assert "disposition_excluded" in out["rows"][0]["reasons"]
    assert settings.next_seq == 5  # mint never called
