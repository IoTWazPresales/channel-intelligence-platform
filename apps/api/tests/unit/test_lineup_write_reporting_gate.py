"""Lane E: the line-up WRITE endpoints act on reporting customers only (BACKLOG-262 R-06).

The reads already carry the shared reporting definition (``customer_reporting``). The write routes
that act on existing ``fact_lineup_plan_item`` rows (group approval, PATCH, DELETE, clear-all) now
use the same definition: a write for a non-reporting customer is refused with the shared reason
(``customer_not_reporting``) and message, and clear-all deletes reporting customers' rows only.
Bulk import and apply-net-requirement already gate in their services (``bulk.py``,
``export_apply.py``). Unit tests with mocks, no database.

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.v1.endpoints import lineup as ep
from app.services.lineup import reporting_gate as gate
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

FLAG = "reports_expected is true"
NOT_MERGED = "merged_into_customer_id is null"


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Scalars:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class _ExecResult:
    def __init__(self, rows: list[Any] | None = None, rowcount: int = 0):
        self._rows = rows or []
        self.rowcount = rowcount

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)


def _db(**attrs: Any) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_ExecResult())
    db.get = AsyncMock(return_value=None)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    for k, v in attrs.items():
        setattr(db, k, v)
    return db


def _assert_refused(exc: pytest.ExceptionInfo[HTTPException]) -> None:
    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": gate.REASON_NOT_REPORTING,
        "message": gate.REFUSAL_MESSAGE,
    }


_NOT_REPORTING = patch.object(ep, "customer_is_reporting", AsyncMock(return_value=False))
_REPORTING = patch.object(ep, "customer_is_reporting", AsyncMock(return_value=True))


# ------------------------------------------------------------------ the gate helper


def test_customer_is_reporting_false_for_no_customer_without_a_query():
    db = _db()
    assert asyncio.run(gate.customer_is_reporting(db, None)) is False
    db.execute.assert_not_awaited()


def test_customer_is_reporting_uses_the_shared_definition_for_one_customer():
    db = _db()
    db.execute = AsyncMock(return_value=_ExecResult([42]))
    assert asyncio.run(gate.customer_is_reporting(db, 42)) is True
    sql = _sql(db.execute.await_args.args[0])
    assert FLAG in sql and NOT_MERGED in sql
    assert "dim_customer.id = " in sql


def test_customer_is_reporting_false_when_the_shared_definition_finds_no_row():
    db = _db()
    db.execute = AsyncMock(return_value=_ExecResult([]))
    assert asyncio.run(gate.customer_is_reporting(db, 42)) is False


def test_not_reporting_detail_is_the_shared_reason_and_message():
    assert gate.not_reporting_detail() == {
        "code": "customer_not_reporting",
        "message": gate.REFUSAL_MESSAGE,
    }


# ------------------------------------------------------------------ group approval


def _group_body() -> Any:
    return ep.LineupGroupApprovalBody(
        customer_id=5, period_start=date(2026, 4, 1), approval_status="approved"
    )


def test_group_approval_for_a_non_reporting_customer_is_refused_before_any_read():
    db = _db()
    with _NOT_REPORTING, pytest.raises(HTTPException) as exc:
        asyncio.run(ep.group_approve_lineup_items(_group_body(), db=db, user={"id": 1}))
    _assert_refused(exc)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_group_approval_for_a_reporting_customer_goes_on_to_read_the_rows():
    db = _db()  # no rows: the route's own 404 proves the gate let it through
    with _REPORTING, pytest.raises(HTTPException) as exc:
        asyncio.run(ep.group_approve_lineup_items(_group_body(), db=db, user={"id": 1}))
    assert exc.value.status_code == 404
    db.execute.assert_awaited_once()


# ------------------------------------------------------------------ PATCH one item


def test_patch_item_of_a_non_reporting_customer_is_refused_and_not_changed():
    row = SimpleNamespace(id=3, customer_id=5, approval_status="draft", notes=None, planned_volume_units=1)
    db = _db(get=AsyncMock(return_value=row))
    body = ep.LineupItemPatch(approval_status="approved")
    with _NOT_REPORTING, pytest.raises(HTTPException) as exc:
        asyncio.run(ep.patch_lineup_item(3, body, db=db, user={"id": 1}))
    _assert_refused(exc)
    assert row.approval_status == "draft"
    db.commit.assert_not_awaited()


def test_patch_item_of_a_reporting_customer_is_applied():
    row = SimpleNamespace(id=3, customer_id=5, approval_status="draft", notes=None, planned_volume_units=1)
    db = _db(get=AsyncMock(return_value=row))
    body = ep.LineupItemPatch(notes="checked")
    with _REPORTING:
        out = asyncio.run(ep.patch_lineup_item(3, body, db=db, user={"id": 1}))
    assert out["notes"] == "checked"
    db.commit.assert_awaited_once()


def test_patch_item_missing_is_still_404():
    db = _db()
    with _NOT_REPORTING, pytest.raises(HTTPException) as exc:
        asyncio.run(ep.patch_lineup_item(3, ep.LineupItemPatch(notes="x"), db=db, user={"id": 1}))
    assert exc.value.status_code == 404


# ------------------------------------------------------------------ DELETE one item


def test_delete_item_of_a_non_reporting_customer_is_refused_and_kept():
    row = SimpleNamespace(id=3, customer_id=5)
    db = _db(get=AsyncMock(return_value=row))
    with _NOT_REPORTING, pytest.raises(HTTPException) as exc:
        asyncio.run(ep.delete_lineup_item(3, db=db))
    _assert_refused(exc)
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_delete_item_of_a_reporting_customer_is_deleted():
    row = SimpleNamespace(id=3, customer_id=5)
    db = _db(get=AsyncMock(return_value=row))
    with _REPORTING:
        resp = asyncio.run(ep.delete_lineup_item(3, db=db))
    assert resp.status_code == 204
    db.delete.assert_awaited_once_with(row)
    db.commit.assert_awaited_once()


# ------------------------------------------------------------------ clear-all


def test_clear_all_deletes_reporting_customers_rows_only():
    db = _db(execute=AsyncMock(return_value=_ExecResult(rowcount=4)))
    out = asyncio.run(ep.clear_lineup_items(ep.ClearConfirmBody(confirm=True), db=db))
    assert out == {"deleted": 4}
    sql = _sql(db.execute.await_args.args[0])
    assert sql.startswith("delete from fact_lineup_plan_item"), sql
    assert "fact_lineup_plan_item.customer_id in (select" in sql, sql
    assert FLAG in sql and NOT_MERGED in sql, sql


def test_clear_all_still_needs_confirm():
    db = _db()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ep.clear_lineup_items(ep.ClearConfirmBody(confirm=False), db=db))
    assert exc.value.status_code == 400
    db.execute.assert_not_awaited()
