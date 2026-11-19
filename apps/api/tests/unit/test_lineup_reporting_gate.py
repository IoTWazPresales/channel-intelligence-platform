"""Warren 2026-11-19: line-up uploads and imports refuse rows for customers that are not reporting.

One rule everywhere: ``customer_report_config.reports_expected`` true (``reporting_customer_ids``).
Refused rows are reported back with a reason; none is dropped silently. No database here; the
DB-backed proof is in tests/test_lineup_reporting_gate_db.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.services.lineup import bulk as bulk_mod
from app.services.lineup import reporting_gate as gate

# --- pure split ---------------------------------------------------------------------------------


def _row(
    n: int, customer_id: int | None, token: str | None = "Tok", sku: str = "S"
) -> dict[str, Any]:
    return {
        "source_row_number": n,
        "customer_id": customer_id,
        "customer_token": token,
        "sku_raw": sku,
    }


def test_rows_for_reporting_customers_are_kept_and_others_refused_with_a_reason():
    rows = [_row(1, 7), _row(2, 8, token="Other", sku="S2"), _row(3, 7)]
    kept, refused = gate.split_rows_by_reporting(rows, {7})
    assert [r["source_row_number"] for r in kept] == [1, 3]
    assert [r["source_row_number"] for r in refused] == [2]
    [ref] = refused
    assert ref["reason"] == gate.REASON_NOT_REPORTING == "customer_not_reporting"
    assert ref["customer_token"] == "Other" and ref["sku_raw"] == "S2"
    assert "not reporting" in ref["message"].lower()


def test_rows_with_no_resolved_customer_are_not_a_customer_row_and_stay_as_before():
    kept, refused = gate.split_rows_by_reporting([_row(1, None, token=None)], set())
    assert len(kept) == 1 and refused == []


def test_nothing_is_reporting_refuses_every_customer_row_never_silently_drops():
    rows = [_row(1, 1), _row(2, 2)]
    kept, refused = gate.split_rows_by_reporting(rows, set())
    assert kept == [] and len(refused) == 2


def test_reported_refusals_are_capped_but_the_count_is_exact():
    refused = [{"source_row_number": i, "reason": gate.REASON_NOT_REPORTING} for i in range(500)]
    shown = gate.cap_refused_rows(refused)
    assert len(shown) == gate.MAX_REFUSED_ROWS_REPORTED < 500


# --- bulk fact_lineup_plan_item upsert ------------------------------------------------------------


class _Scalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class _Result:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _Scalars:
        return _Scalars(self._items)

    def scalar_one_or_none(self) -> Any:
        return None


class _FakeBulkDb:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.customers = [
            SimpleNamespace(id=1, code="CUST-A", name="Alpha", merged_into_customer_id=None),
            SimpleNamespace(id=2, code="CUST-B", name="Beta", merged_into_customer_id=None),
        ]
        self.products = [SimpleNamespace(id=10, sku="SKU-1")]

    async def execute(self, stmt: Any) -> _Result:
        text = str(stmt).lower()
        if "from dim_customer" in text:
            return _Result(self.customers)
        if "from dim_channel" in text:
            return _Result([])
        if "from dim_product" in text:
            return _Result(self.products)
        return _Result([])  # _find_existing: nothing exists

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for i, obj in enumerate(self.added, start=500):
            if getattr(obj, "id", None) is None:
                obj.id = i

    async def commit(self) -> None:
        return None


def _bulk(monkeypatch, reporting: set[int], rows: list[dict[str, Any]]) -> tuple[dict, _FakeBulkDb]:
    async def fake_reporting(_db: Any) -> set[int]:
        return reporting

    monkeypatch.setattr(bulk_mod, "reporting_customer_ids", fake_reporting)
    db = _FakeBulkDb()
    out = asyncio.run(bulk_mod.bulk_upsert_lineup_items(db, rows, replace_matching=False))  # type: ignore[arg-type]
    return out, db


def _item(code: str) -> dict[str, Any]:
    return {"customer_code": code, "sku": "SKU-1", "period_start": "2026-10-01"}


def test_bulk_upsert_refuses_rows_for_a_non_reporting_customer_and_says_why(monkeypatch):
    out, db = _bulk(monkeypatch, {1}, [_item("CUST-A"), _item("CUST-B")])
    assert out["inserted"] == 1 and out["refused"] == 1
    refused = [r for r in out["results"] if r["status"] == "refused"]
    assert len(refused) == 1
    assert refused[0]["reason"] == "customer_not_reporting"
    assert refused[0]["errors"] and "not reporting" in refused[0]["errors"][0].lower()
    assert [o.customer_id for o in db.added] == [1]  # nothing was written for the refused customer


def test_bulk_upsert_with_no_reporting_customers_writes_nothing(monkeypatch):
    out, db = _bulk(monkeypatch, set(), [_item("CUST-A")])
    assert out["inserted"] == 0 and out["refused"] == 1 and db.added == []


def test_bulk_upsert_refusal_does_not_count_as_a_validation_error(monkeypatch):
    out, _db = _bulk(monkeypatch, set(), [_item("CUST-A"), {"sku": "SKU-1"}])
    assert out["refused"] == 1
    assert out["errors"] == 1  # the row with no customer_code is still a validation error


# --- the shared file parser (unified import, parse-apply and bulk backfill end here) ---


def _run_parse(monkeypatch, *, reporting: set[int], parse_opts: dict[str, Any] | None = None):
    from unittest.mock import AsyncMock, MagicMock

    from app.services.commercial_planner import lineup_case_parser as lcp

    def row(n: int, customer_id: int | None) -> dict[str, Any]:
        return {
            "source_row_number": n,
            "product_id": 10,
            "customer_id": customer_id,
            "customer_token": f"tok{n}",
            "sku_raw": f"SKU{n}",
            "diagnostic_codes": [],
            "row_status": "resolved",
            "raw_row_payload": {"uploaded": {}},
        }

    parsed = [row(2, 1), row(3, 2), row(4, None)]
    monkeypatch.setattr(
        lcp,
        "_parse_file_to_row_dicts",
        lambda *_a, **_k: (list(parsed), [], 3, 3, 0, 1, 0, []),
    )

    async def fake_reporting(_db: Any) -> set[int]:
        return reporting

    monkeypatch.setattr(lcp, "reporting_customer_ids", fake_reporting)
    case = SimpleNamespace(
        id=10,
        import_job_id=None,
        file_name=None,
        period_label=None,
        inferred_period_start=None,
        product_line=None,
        business_unit="BU",  # set, so the business-unit resolution (which reads the DB) is skipped
        commercial_status="accepted",
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
    result = asyncio.run(lcp.parse_current_lineup_file(db, 10, "f.csv", b"x"))
    return result, added


def test_parser_writes_only_reporting_customers_rows_and_reports_the_refused_ones(monkeypatch):
    from app.models.commercial_lineup import CommercialLineupLine

    result, added = _run_parse(monkeypatch, reporting={1})
    lines = [o for o in added if isinstance(o, CommercialLineupLine)]
    # Reporting-customer and unresolved-customer rows are written; the non-reporting one is not.
    assert sorted(ln.source_row_number for ln in lines) == [2, 4]
    assert result.line_count == 2 and result.refused_count == 1
    [ref] = result.refused_rows
    assert ref["source_row_number"] == 3 and ref["reason"] == "customer_not_reporting"
    assert any("1 row(s) refused" in w for w in result.warnings)
    job = next(o for o in added if type(o).__name__ == "ImportJob")
    assert job.staged_metadata["lineup_refused_rows"]["count"] == 1


def test_parser_with_no_reporting_customers_refuses_every_customer_row(monkeypatch):
    from app.models.commercial_lineup import CommercialLineupLine

    result, added = _run_parse(monkeypatch, reporting=set())
    lines = [o for o in added if isinstance(o, CommercialLineupLine)]
    assert [ln.source_row_number for ln in lines] == [4]
    assert result.refused_count == 2


def test_parser_slice_row_count_check_counts_refused_rows_as_accounted_for(monkeypatch):
    from app.services.commercial_planner import lineup_case_parser as lcp

    # A backfill slice names source rows 2 and 3; row 3 is refused, so only one line persists.
    # That must not raise the "slice row count mismatch" error.
    original = lcp.ImportJob

    class _Job(original):  # type: ignore[misc, valid-type]
        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.staged_metadata = {"lineup_parse_options": {"slice_source_rows": [2, 3]}}

    monkeypatch.setattr(lcp, "ImportJob", _Job)
    result, _added = _run_parse(monkeypatch, reporting={1})
    assert result.line_count == 1 and result.refused_count == 1
