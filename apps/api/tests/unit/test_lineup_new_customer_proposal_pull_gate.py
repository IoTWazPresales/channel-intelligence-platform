"""Final wave (a): the automatic line-up pull only writes rows for reporting customers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.services.lineup import export_apply


class _Result:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._rows


class _FakeDb:
    """Answers the customer and product reads of apply_net_requirement_to_lineup."""

    def __init__(self) -> None:
        self.customers = [
            SimpleNamespace(id=1, code="C-REP", name="Reporting"),
            SimpleNamespace(id=2, code="C-OTH", name="Not reporting"),
        ]
        self.products = [SimpleNamespace(id=10, sku="S-10", name="Product ten")]

    async def execute(self, stmt: Any) -> _Result:
        text = str(stmt)
        return _Result(self.customers if "dim_customer" in text else self.products)

    async def commit(self) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        return None


def _payload() -> dict[str, Any]:
    return {
        "row_count": 1,
        "rows": [
            {
                "product_id": 10,
                "distributor_id": 5,
                "net_requirement": 100,
                "customer_allocation": [
                    {"customer_id": 1, "suggested_lineup_units": 30, "share": 0.3},
                    {"customer_id": 2, "suggested_lineup_units": 70, "share": 0.7},
                ],
            }
        ],
    }


def test_apply_skips_customers_that_do_not_report_and_counts_them(monkeypatch):
    seen: dict[str, Any] = {}

    async def fake_net(*_a, **_k):
        return _payload()

    async def fake_bu(_db):
        return {}

    async def fake_bias(_db, *, apply_bias):
        return {}

    async def fake_reporting(_db):
        return {1}

    async def fake_bulk(_db, rows, *, replace_matching):
        seen["codes"] = [r["customer_code"] for r in rows]
        return {"inserted": len(rows), "updated": 0, "skipped": 0, "errors": 0, "results": []}

    monkeypatch.setattr(export_apply, "build_net_requirement_rows", fake_net)
    monkeypatch.setattr(export_apply, "_product_bu_map", fake_bu)
    monkeypatch.setattr(export_apply, "_bias_by_bu", fake_bias)
    monkeypatch.setattr(export_apply, "reporting_customer_ids", fake_reporting)
    monkeypatch.setattr(export_apply, "bulk_upsert_lineup_items", fake_bulk)

    out = asyncio.run(
        export_apply.apply_net_requirement_to_lineup(
            _FakeDb(),
            period_start=__import__("datetime").date(2026, 10, 1),
            write_commercial_case=False,
        )
    )
    assert seen["codes"] == ["C-REP"]
    assert out["skipped_not_reporting"] == 1
    assert out["draft_rows_built"] == 1


def test_apply_with_no_reporting_customers_writes_nothing(monkeypatch):
    async def fake_net(*_a, **_k):
        return _payload()

    async def fake_empty(_db, *a, **k):
        return {}

    async def fake_reporting(_db):
        return set()

    async def fail_bulk(*_a, **_k):  # pragma: no cover - must not be called
        raise AssertionError("no rows may be written for non-reporting customers")

    monkeypatch.setattr(export_apply, "build_net_requirement_rows", fake_net)
    monkeypatch.setattr(export_apply, "_product_bu_map", fake_empty)
    monkeypatch.setattr(export_apply, "_bias_by_bu", fake_empty)
    monkeypatch.setattr(export_apply, "reporting_customer_ids", fake_reporting)
    monkeypatch.setattr(export_apply, "bulk_upsert_lineup_items", fail_bulk)

    out = asyncio.run(
        export_apply.apply_net_requirement_to_lineup(
            _FakeDb(),
            period_start=__import__("datetime").date(2026, 10, 1),
            write_commercial_case=False,
        )
    )
    assert out["inserted"] == 0 and out["draft_rows_built"] == 0
    assert out["skipped_not_reporting"] == 2
