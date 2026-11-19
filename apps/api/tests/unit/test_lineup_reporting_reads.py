"""Line-up read paths show reporting customers only (Warren 2026-11-19 reporting-only rule).

Each read of ``fact_lineup_plan_item`` that feeds the Planning line-up screens or the planned
reservation (``GET /lineup/items`` and the async budget-position derivation) is driven with a
capturing fake session (no database); the sync planned reservation no longer reads line-ups at
all (lane L4, see the last tests). The
statement it emits against the plan-item table must carry the shared reporting definition from
``app.services.customer_reporting`` (reports expected true AND not merged away) as a restriction on
``fact_lineup_plan_item.customer_id``, and must keep its other filters. The cross-module DB proof is
in tests/test_lineup_reporting_filter_db.py.

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from app.api.v1.endpoints import lineup as lineup_endpoint
from app.services.cpor import promo_plan_builder
from app.services.lineup import budget_position
from sqlalchemy.dialects import postgresql

FLAG = "reports_expected is true"
NOT_MERGED = "merged_into_customer_id is null"
RESTRICTION = "fact_lineup_plan_item.customer_id in (select"


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Rows(list):
    def all(self) -> list[Any]:
        return list(self)

    def scalars(self) -> _Rows:
        return self

    def unique(self) -> _Rows:
        return self

    def first(self) -> Any:
        return self[0] if self else None

    def scalar(self) -> Any:
        return None


class _SyncSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()

    def scalars(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()


class _AsyncSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()

    async def scalars(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        self.statements.append(stmt)
        return _Rows()


def _plan_item_reads(statements: list[Any]) -> list[str]:
    reads = []
    for stmt in statements:
        sql = _sql(stmt)
        if "from fact_lineup_plan_item" in sql:
            reads.append(sql)
    return reads


def _assert_reporting_only(sql: str) -> None:
    assert RESTRICTION in sql, sql
    assert FLAG in sql, sql
    assert NOT_MERGED in sql, sql


def test_list_items_carries_reporting_predicate():
    db = _AsyncSession()
    out = asyncio.run(
        lineup_endpoint.list_lineup_items(
            customer_id=None, channel_id=None, period_start=None, db=db
        )
    )
    assert out == []
    reads = _plan_item_reads(db.statements)
    assert len(reads) == 1
    _assert_reporting_only(reads[0])


def test_list_items_keeps_customer_channel_and_period_filters():
    db = _AsyncSession()
    asyncio.run(
        lineup_endpoint.list_lineup_items(
            customer_id=7, channel_id=3, period_start=date(2026, 4, 1), db=db
        )
    )
    (sql,) = _plan_item_reads(db.statements)
    _assert_reporting_only(sql)
    assert "fact_lineup_plan_item.customer_id = " in sql
    assert "fact_lineup_plan_item.channel_id = " in sql
    assert "fact_lineup_plan_item.period_start = " in sql


def test_list_items_for_a_non_reporting_customer_id_is_still_restricted():
    """Asking for one customer never bypasses the reporting restriction (AND, not OR)."""
    db = _AsyncSession()
    asyncio.run(
        lineup_endpoint.list_lineup_items(
            customer_id=99, channel_id=None, period_start=None, db=db
        )
    )
    (sql,) = _plan_item_reads(db.statements)
    _assert_reporting_only(sql)
    assert " or " not in sql.split("where", 1)[1]


def test_budget_position_derivation_carries_reporting_predicate():
    db = _AsyncSession()
    planned, _diag = asyncio.run(
        budget_position.derive_planned_reservations_with_diagnostics(db)
    )
    assert planned == []
    reads = _plan_item_reads(db.statements)
    assert len(reads) == 1
    _assert_reporting_only(reads[0])


def test_planned_reservation_sync_reads_no_lineup_at_all():
    """Warren 2026-11-19 (lane L4): the promotion planner is sell-through only.

    ``derive_planned_reservation_sync`` used to read ``fact_lineup_plan_item`` (and carried the
    reporting-customer restriction). It no longer reads any line-up: the planned reservation is
    "not available" (see tests/unit/test_planner_sellthrough_sources.py). The reporting
    restriction on the line-up screens and the async budget position is covered above.
    """
    session = _SyncSession()
    out = promo_plan_builder.derive_planned_reservation_sync(session, limit=123)
    assert session.statements == []
    assert out["available"] is False
    assert out["planned_reservation_usd"] is None


def test_planned_reservation_sync_with_period_label_reads_nothing():
    session = _SyncSession()
    promo_plan_builder.derive_planned_reservation_sync(session, period_label="2026Q2")
    assert _plan_item_reads(session.statements) == []
    assert session.statements == []
