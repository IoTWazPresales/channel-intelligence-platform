"""Warren 2026-11-19: planner cards show EXACT counts (BACKLOG-254).

``GET /cpor/cases/counts`` counts current cases only (``superseded_by_case_id`` null), with the same
tenant, fixture-case and filter rules as ``GET /cpor/cases``. The statement is compiled and read as
SQL here (no database); the DB-backed proof is tests/test_cpor_case_counts_db.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app.api.v1.endpoints import cpor_cases as ep
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

USER = {"sub": "u1", "tenant_id": "tenant-a"}


class _Rows:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, int]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None

    def execute(self, stmt: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows(self.rows)


def _call(monkeypatch, rows, **overrides) -> tuple[dict[str, Any], str]:
    session = _FakeSession(rows)
    monkeypatch.setattr(ep, "SessionLocal", lambda: session)
    args: dict[str, Any] = dict(
        status=None,
        exclude_status=[],
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit=None,
        window_from=None,
        window_to=None,
        test_data=None,
        q=None,
        evidence_basis=None,
        user=USER,
    )
    args.update(overrides)
    out = ep.count_cases(**args)
    sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    return out, " ".join(sql.split())


def test_counts_are_summed_from_the_grouped_statuses_and_never_capped(monkeypatch):
    out, _sql = _call(monkeypatch, [("draft", 3), ("proposed", 612), ("active", 40)])
    assert out["total_current"] == 655  # above the 500-row page the list can return
    assert out["status_counts_current"] == {"draft": 3, "proposed": 612, "active": 40}


def test_no_cases_is_a_real_zero(monkeypatch):
    out, _sql = _call(monkeypatch, [])
    assert out == {"total_current": 0, "status_counts_current": {}}


def test_replaced_cases_are_excluded_by_the_pointer_not_by_status(monkeypatch):
    _out, sql = _call(monkeypatch, [])
    assert "cpor_case.superseded_by_case_id IS NULL" in sql


def test_tenant_and_fixture_scoping_match_the_cases_list(monkeypatch):
    _out, sql = _call(monkeypatch, [])
    assert "cpor_case.tenant_id = 'tenant-a'" in sql
    # The default list scope hides fixture (intelligence_exclude) cases; so do the counts.
    assert "intelligence_exclude" in sql


def test_status_window_and_excluded_status_filters_reach_the_statement(monkeypatch):
    _out, sql = _call(
        monkeypatch,
        [],
        status=None,
        exclude_status=["cancelled", "rejected"],
        window_from=date(2026, 11, 19),
        window_to=date(2026, 12, 17),
    )
    assert "cpor_case.status NOT IN ('cancelled', 'rejected')" in sql
    assert "cpor_case.window_start >= '2026-11-19'" in sql
    assert "cpor_case.window_start <= '2026-12-17'" in sql
    _out, sql = _call(monkeypatch, [], status="proposed")
    assert "cpor_case.status = 'proposed'" in sql


def test_product_line_and_customer_scope_filters_match_the_list(monkeypatch):
    _out, sql = _call(monkeypatch, [], customer_id=9, business_unit="Audio")
    assert "cpor_case.customer_id = 9" in sql
    assert "dim_product.business_unit ILIKE '%%Audio%%'" in sql
    assert "dim_product.product_line ILIKE '%%Audio%%'" in sql


def test_unknown_status_and_unknown_exclusion_are_refused(monkeypatch):
    with pytest.raises(HTTPException) as bad:
        _call(monkeypatch, [], status="superseded")
    assert bad.value.status_code == 400
    with pytest.raises(HTTPException) as bad2:
        _call(monkeypatch, [], exclude_status=["nonsense"])
    assert bad2.value.status_code == 400


def test_counts_route_is_declared_before_the_case_id_route():
    paths = [getattr(r, "path", "") for r in ep.router.routes]
    assert paths.index("/cases/counts") < paths.index("/cases/{case_id}")
