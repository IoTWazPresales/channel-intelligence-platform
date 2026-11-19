"""Every reader of ``customer_report_config.reports_expected`` uses the one definition (PR #122 r2,
B2).

A reporting customer is the flag true AND not merged into another customer
(``app.services.customer_reporting``). Each reader below is driven with a capturing fake session (no
database); every statement it emits that reads the flag must also carry the not-merged clause, and
the Python-side checks must refuse a merged-away customer whose flag is still true. Callers keep
their other conditions (tenant, key account) unchanged. The cross-module DB proof is in
tests/test_reporting_customer_readers_db.py.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from app.services import customer_reporting
from sqlalchemy.dialects import postgresql

FLAG = "reports_expected is true"
NOT_MERGED = "merged_into_customer_id is null"


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Rows(list):
    """An empty (or given) result usable as ``.all()``, ``.scalars()`` or an iterator."""

    def all(self) -> list[Any]:
        return list(self)

    def scalars(self) -> _Rows:
        return self

    def first(self) -> Any:
        return self[0] if self else None


class _CapturingSession:
    def __init__(self, scalar_results: list[Any] | None = None) -> None:
        self.statements: list[Any] = []
        self._scalar_results = list(scalar_results or [])

    def execute(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()

    def scalars(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()

    def scalar(self, stmt: Any, *_a: Any, **_k: Any) -> Any:
        self.statements.append(stmt)
        return self._scalar_results.pop(0) if self._scalar_results else None

    def get(self, *_a: Any, **_k: Any) -> Any:
        return None


def _flag_statements(statements: list[Any]) -> list[str]:
    out = []
    for stmt in statements:
        try:
            sql = _sql(stmt)
        except Exception:  # noqa: BLE001 - non-SQL arguments are not readers
            continue
        if FLAG in sql:
            out.append(sql)
    return out


def _assert_every_flag_read_excludes_merged(statements: list[Any]) -> None:
    reads = _flag_statements(statements)
    assert reads, "the reader emitted no statement that reads the reporting flag"
    for sql in reads:
        assert NOT_MERGED in sql, sql


# ------------------------------------------------------------------ the shared definition


def test_python_side_definition_is_flag_true_and_not_merged():
    cfg = SimpleNamespace(reports_expected=True)
    live = SimpleNamespace(merged_into_customer_id=None)
    merged = SimpleNamespace(merged_into_customer_id=7)
    assert customer_reporting.is_reporting(cfg, live) is True
    assert customer_reporting.is_reporting(cfg, merged) is False
    assert customer_reporting.is_reporting(SimpleNamespace(reports_expected=False), live) is False
    assert customer_reporting.is_reporting(None, live) is False
    assert customer_reporting.is_reporting(cfg, None) is False


def test_sql_expression_form_carries_both_clauses():
    sql = _sql(customer_reporting.reporting_customer_expr())
    assert "reports_expected is true" in sql and NOT_MERGED in sql


# ------------------------------------------------------------------ listing capture


def test_listing_discovery_reporting_customers_and_tenants_exclude_merged():
    from app.services.listing_capture import discovery

    db = _CapturingSession()
    discovery._reporting_customers(db, "t-unit")  # type: ignore[arg-type]
    discovery._tenant_ids(db, None)  # type: ignore[arg-type]
    _assert_every_flag_read_excludes_merged(db.statements)
    assert any("tenant_id" in s for s in _flag_statements(db.statements))


def test_listing_autoconfig_reporting_customers_and_tenants_exclude_merged():
    from app.services.listing_capture import autoconfig

    db = _CapturingSession()
    autoconfig._reporting_customers(db, "t-unit")  # type: ignore[arg-type]
    autoconfig._tenant_ids(db, None)  # type: ignore[arg-type]
    _assert_every_flag_read_excludes_merged(db.statements)


def test_listing_coverage_customer_flag_excludes_merged():
    from app.services.listing_capture import coverage

    db = _CapturingSession()
    coverage._customers(db, "t-unit")  # type: ignore[arg-type]
    _assert_every_flag_read_excludes_merged(db.statements)


def test_stock_not_listed_reporting_customers_exclude_merged():
    from app.services.listing_capture import stock_not_listed

    db = _CapturingSession()
    stock_not_listed._reporting_customers(db, "t-unit", None)  # type: ignore[arg-type]
    _assert_every_flag_read_excludes_merged(db.statements)


class _OnboardSession:
    """Answers the customer lookup, then the config lookup; anything after that is a failure."""

    def __init__(self, customer: Any, config: Any) -> None:
        self._answers = [customer, config]

    def scalar(self, _stmt: Any) -> Any:
        if not self._answers:
            raise AssertionError("site onboarding went past the reporting check")
        return self._answers.pop(0)

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"site onboarding went past the reporting check ({name})")


def test_site_onboarding_refuses_a_merged_away_customer_with_the_flag_still_true():
    from app.models.customer_report_config import CustomerReportConfig
    from app.models.dimensions import DimCustomer
    from app.services.listing_capture import site_onboarding

    customer = DimCustomer(id=11, tenant_id="t-unit", code="UNIT-11", name="Unit customer")
    customer.merged_into_customer_id = 12
    config = CustomerReportConfig(customer_id=11, reports_expected=True)
    with pytest.raises(site_onboarding.SiteOnboardError) as err:
        site_onboarding.record_customer_site(
            _OnboardSession(customer, config),  # type: ignore[arg-type]
            tenant_id="t-unit",
            customer_id=11,
            site_key="unit-site",
            domain="unit.example",
            example_urls=None,
            actor="unit",
        )
    assert err.value.code == "not_reporting"


# ------------------------------------------------------------------ CST slot job


def test_cst_slot_job_walks_only_reporting_customers_and_keeps_the_key_account_rule():
    from app.services.imports import cst_d1

    db = _CapturingSession()
    out = cst_d1.advance_cst_report_slots(
        db,  # type: ignore[arg-type]
        as_of=date(2026, 11, 19),
        now=datetime(2026, 11, 19, tzinfo=UTC),
    )
    assert out["created"] == 0
    _assert_every_flag_read_excludes_merged(db.statements)


# ------------------------------------------------------------------ sell-through overview


def test_sell_through_coverage_marks_a_merged_away_customer_not_expected():
    from app.services.business_calendar import BusinessCalendar
    from app.services.channel_intelligence import sell_through_overview as sto

    f = sto.OverviewFilters(date_from=date(2026, 11, 2), date_to=date(2026, 11, 15))
    cfg = SimpleNamespace(
        reports_expected=True, expected_cadence="weekly", overdue_threshold_days=0
    )
    live = SimpleNamespace(name="Live", code="L", merged_into_customer_id=None)
    merged = SimpleNamespace(name="Merged", code="M", merged_into_customer_id=1)
    out = sto._coverage(
        BusinessCalendar(),
        f,
        [],
        {1, 2},
        {1: live, 2: merged},
        {1: cfg, 2: cfg},
        date(2026, 11, 19),
    )
    expected = {row["customer_id"]: row["reports_expected"] for row in out["customers"]}
    assert expected == {1: True, 2: False}


def test_sell_through_in_view_and_filter_options_exclude_merged_from_reporting():
    from app.services.channel_intelligence import sell_through_overview as sto

    in_view = _sql(sto.in_view_config_rows_select())
    assert NOT_MERGED in in_view
    assert "is_key_account is true" in in_view  # the key-account condition is unchanged

    db = _CapturingSession()
    sto.filter_options(db, "t-unit")  # type: ignore[arg-type]
    _assert_every_flag_read_excludes_merged(db.statements)


# ------------------------------------------------------------------ ops health


def test_ops_report_health_counts_only_reporting_customers(monkeypatch):
    from app.api.v1.endpoints import ops

    monkeypatch.setattr(ops, "get_settings", lambda: SimpleNamespace(cip_ops_state_dir=""))
    monkeypatch.setattr(ops, "file_health", lambda *args, **kwargs: {})
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=["forbidden_unit", 0, 0, 0, None, 0, 0]),
        execute=AsyncMock(side_effect=[Mock(), Mock(all=lambda: []), Mock(all=lambda: [])]),
    )
    asyncio.run(
        ops.ops_overview(
            db=db, user={"id": "1", "tenant_id": "ops-unit", "role": "admin"}, failed_limit=5
        )
    )
    statements = [
        c.args[0] for c in db.scalar.await_args_list + db.execute.await_args_list if c.args
    ]
    reads = _flag_statements(statements)
    assert len(reads) == 4  # slot counts, newest receipt, expected customers, untracked customers
    _assert_every_flag_read_excludes_merged(statements)
