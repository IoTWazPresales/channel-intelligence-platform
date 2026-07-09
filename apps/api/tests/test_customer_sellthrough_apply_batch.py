"""Unit tests for the batched customer sell-through apply (no database I/O).

Covers Unit 3's mechanism change: the per-row ``INSERT … ON CONFLICT`` loop is now chunked
multi-row upserts. Conflict behavior is unchanged; lines sharing a ``source_key`` are de-duped
within a chunk (Postgres rejects touching the same key twice) with last-value-wins, and every line
in the group is still marked ``applied`` and pointed at the resulting fact id.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.imports.customer_sell_through as cst
import app.services.imports.customer_sell_through_apply as apply_mod


def _line(i, *, cust, prod, period, units, loc=None, site_label=None):
    return SimpleNamespace(
        id=i,
        resolved_customer_id=cust,
        resolved_product_id=prod,
        resolved_location_id=loc,
        period_start_date=period,
        units_sold=units,
        period_type="weekly",
        raw_mtd_units=None,
        is_mtd_estimate=False,
        unit_sell_price=None,
        unit_cost=None,
        unit_mac=None,
        reported_soh=None,
        site_label=site_label,
        vat_basis=None,
        raw_location_token=site_label,
        raw_row_payload={},
        apply_status=None,
        fact_sellthrough_row_id=None,
    )


def _db_with_lines(lines, returned_rows):
    db = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = lines
    db.scalars.return_value = scalars_result
    db.scalar.return_value = 0  # skipped_unresolved count query
    exec_result = MagicMock()
    exec_result.all.return_value = returned_rows
    db.execute.return_value = exec_result
    return db


def _patch_source_key(monkeypatch):
    monkeypatch.setattr(
        cst,
        "customer_sellthrough_source_key",
        lambda customer_id, customer_location_id, product_id, period_start_date: (
            f"{customer_id}-{customer_location_id}-{product_id}-{period_start_date}"
        ),
    )


def test_dedup_by_source_key_all_grouped_lines_applied(monkeypatch) -> None:
    _patch_source_key(monkeypatch)
    a = _line(1, cust=1, prod=10, period="P1", units=2)
    b = _line(2, cust=1, prod=10, period="P1", units=5)  # same key as a -> grouped, last wins
    c = _line(3, cust=1, prod=11, period="P1", units=3)  # distinct key
    d = _line(4, cust=1, prod=12, period="P1", units=None)  # invalid -> skipped
    returned = [
        SimpleNamespace(id=100, source_key="1-None-10-P1"),
        SimpleNamespace(id=101, source_key="1-None-11-P1"),
    ]
    db = _db_with_lines([a, b, c, d], returned)

    summary = apply_mod.apply_customer_sellthrough_staging(db, 7)

    # a,b,c all applied (3); two unique keys -> one chunk -> one execute (no duplicate-key error).
    assert summary.applied == 3
    assert db.execute.call_count == 1
    assert a.apply_status == b.apply_status == c.apply_status == "applied"
    assert a.fact_sellthrough_row_id == 100 and b.fact_sellthrough_row_id == 100  # group shares fact id
    assert c.fact_sellthrough_row_id == 101
    assert d.apply_status is None  # invalid line untouched
    assert summary.skipped_unresolved == 1


def test_chunking_and_progress(monkeypatch) -> None:
    _patch_source_key(monkeypatch)
    lines = [_line(i, cust=1, prod=i, period="P1", units=1) for i in range(1, 4)]  # 3 unique keys
    returned = [SimpleNamespace(id=200 + i, source_key=f"1-None-{i}-P1") for i in range(1, 4)]
    db = _db_with_lines(lines, returned)
    progress: list[tuple[int, int]] = []

    summary = apply_mod.apply_customer_sellthrough_staging(
        db, 7, chunk_size=1, on_progress=lambda c, t: progress.append((c, t))
    )

    assert summary.applied == 3
    assert db.execute.call_count == 3  # one statement per chunk of 1
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_chunk_failure_records_errors_not_raise(monkeypatch) -> None:
    _patch_source_key(monkeypatch)
    lines = [_line(1, cust=1, prod=10, period="P1", units=2)]
    db = _db_with_lines(lines, [])
    db.execute.side_effect = RuntimeError("constraint boom")

    summary = apply_mod.apply_customer_sellthrough_staging(db, 7)

    assert summary.applied == 0
    assert len(summary.errors) == 1
    assert "line 1" in summary.errors[0] and "boom" in summary.errors[0]
    assert lines[0].apply_status is None
