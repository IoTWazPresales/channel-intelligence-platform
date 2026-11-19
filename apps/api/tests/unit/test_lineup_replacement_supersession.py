"""Fix round 1 / B1: a replacement import with no eligible rows must not retire the old line-up.

The bulk backfill used to supersede the existing case the moment the replacement case was
created, before its parse had run. With the reporting gate the parse can legitimately refuse
every row, so the supersession now happens inside the parse transaction, only when the
replacement keeps at least one row. No database here; the DB-backed proof is
tests/test_lineup_replacement_supersession_db.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.services.commercial_planner import lineup_case_supersession as sup

# --- the decision (pure) ----------------------------------------------------------------------


def test_replacement_with_eligible_rows_supersedes():
    out = sup.decide_replacement_supersession(eligible_line_count=3, refused_count=2)
    assert out["supersede"] is True and out["reason"] is None


def test_replacement_with_only_refused_rows_does_not_supersede_and_says_why():
    out = sup.decide_replacement_supersession(eligible_line_count=0, refused_count=5)
    assert out["supersede"] is False
    assert out["reason"] == sup.REASON_REPLACEMENT_HAS_NO_ELIGIBLE_ROWS
    assert out["refused_count"] == 5


def test_replacement_with_no_rows_at_all_does_not_supersede():
    out = sup.decide_replacement_supersession(eligible_line_count=0, refused_count=0)
    assert out["supersede"] is False and out["refused_count"] == 0


# --- the shared parser applies the decision inside its transaction ----------------------------


def _run_parse(
    monkeypatch: Any, *, reporting: set[int], customer_ids: list[int | None], replaces: int | None
):
    from app.services.commercial_planner import lineup_case_parser as lcp

    parsed = [
        {
            "source_row_number": n,
            "product_id": 10,
            "customer_id": cid,
            "customer_token": f"tok{n}",
            "sku_raw": f"SKU{n}",
            "diagnostic_codes": [],
            "row_status": "resolved",
            "raw_row_payload": {"uploaded": {}},
        }
        for n, cid in enumerate(customer_ids, start=2)
    ]
    monkeypatch.setattr(
        lcp,
        "_parse_file_to_row_dicts",
        lambda *_a, **_k: (list(parsed), [], len(parsed), len(parsed), 0, 0, 0, []),
    )

    async def fake_reporting(_db: Any) -> set[int]:
        return reporting

    monkeypatch.setattr(lcp, "reporting_customer_ids", fake_reporting)

    original = lcp.ImportJob

    class _Job(original):  # type: ignore[misc, valid-type]
        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            opts = {"replaces_case_id": replaces} if replaces is not None else {}
            self.staged_metadata = {"lineup_parse_options": opts}

    monkeypatch.setattr(lcp, "ImportJob", _Job)

    case = SimpleNamespace(
        id=10,
        import_job_id=None,
        file_name=None,
        period_label=None,
        inferred_period_start=None,
        product_line=None,
        business_unit="BU",
        commercial_status="draft_imported",
    )
    added: list[Any] = []
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.scalar = AsyncMock(return_value=SimpleNamespace(id=77))
    db.flush = AsyncMock()
    db.add = MagicMock(side_effect=added.append)
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.run_sync = AsyncMock(return_value={"loser_case_id": replaces})
    result = asyncio.run(lcp.parse_current_lineup_file(db, 10, "f.csv", b"x"))
    job = next(o for o in added if type(o).__name__ == "_Job")
    return result, job, db


def test_parser_does_not_supersede_when_every_row_is_refused(monkeypatch):
    result, job, db = _run_parse(
        monkeypatch, reporting=set(), customer_ids=[1, 2], replaces=99
    )
    assert result.line_count == 0 and result.refused_count == 2
    db.run_sync.assert_not_called()  # the existing case and its PO links are left alone
    note = job.staged_metadata["lineup_replacement"]
    assert note["existing_case_id"] == 99 and note["superseded"] is False
    assert note["reason"] == sup.REASON_REPLACEMENT_HAS_NO_ELIGIBLE_ROWS
    assert note["refused_count"] == 2
    assert any("existing case #99 was kept" in w for w in result.warnings)


def test_parser_supersedes_inside_the_parse_when_a_row_is_kept(monkeypatch):
    result, job, db = _run_parse(
        monkeypatch, reporting={1}, customer_ids=[1, 2], replaces=99
    )
    assert result.line_count == 1 and result.refused_count == 1
    db.run_sync.assert_awaited_once()
    assert job.staged_metadata["lineup_replacement"] == {
        "existing_case_id": 99,
        "superseded": True,
        "reason": None,
        "refused_count": 1,
    }
    # The supersession is part of the same transaction as the lines: it ran before the commit.
    assert db.commit.await_count == 1


def test_parser_without_a_replaced_case_never_touches_supersession(monkeypatch):
    result, job, db = _run_parse(monkeypatch, reporting=set(), customer_ids=[1], replaces=None)
    db.run_sync.assert_not_called()
    assert "lineup_replacement" not in job.staged_metadata
    assert result.refused_count == 1
