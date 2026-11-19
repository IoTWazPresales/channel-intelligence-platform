"""One definition of a reporting customer for every PR #122 check (fix round 1, item 3).

The app-wide flag is ``customer_report_config.reports_expected`` (CST steward, Key accounts & feed
profile, Reports expected). A reporting customer is that flag true AND not merged away, which is the
rule ``cst_layouts.list_reporting_customers`` applies. The line-up gate, the new-customer seed
check, the new-customer picker and the CST picker all go through ``customer_reporting``. No database
here; the DB proof is in tests/test_lineup_reporting_gate_db.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.services import customer_reporting
from app.services.lineup import new_customer_proposal as ncp
from app.services.lineup import reporting_gate
from sqlalchemy.dialects import postgresql


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


def test_the_definition_is_flag_true_and_not_merged_away():
    sql = _sql(customer_reporting.reporting_customer_ids_select())
    assert "reports_expected is true" in sql
    assert "merged_into_customer_id is null" in sql


class _CapturingAsyncDb:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        self.statements.append(stmt)

        class _R:
            def scalars(self_inner) -> Any:
                class _S:
                    def all(self_s) -> list[int]:
                        return [3, 4]

                return _S()

        return _R()


def test_gate_reader_runs_the_shared_statement_so_merged_customers_are_not_reporting():
    db = _CapturingAsyncDb()
    ids = asyncio.run(ncp.reporting_customer_ids(db))  # type: ignore[arg-type]
    assert ids == {3, 4}
    assert _sql(db.statements[0]) == _sql(customer_reporting.reporting_customer_ids_select())


class _CapturingSyncDb:
    def __init__(self, found: int | None) -> None:
        self.statements: list[Any] = []
        self._found = found

    def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return self._found


def test_new_customer_check_uses_the_shared_definition_and_names_where_the_flag_is_set():
    db = _CapturingSyncDb(found=None)
    try:
        ncp.ensure_reporting_customer(db, 9)  # type: ignore[arg-type]
    except ncp.ProposalError as err:
        assert err.status_code == 409 and err.code == "customer_not_reporting"
        assert "Key accounts & feed profile" in err.message
        assert "Reports expected" in err.message
    else:  # pragma: no cover
        raise AssertionError("a customer outside the definition must be refused")
    sql = _sql(db.statements[0])
    assert "reports_expected is true" in sql and "merged_into_customer_id is null" in sql


def test_new_customer_check_accepts_a_customer_in_the_definition():
    ncp.ensure_reporting_customer(_CapturingSyncDb(found=9), 9)  # type: ignore[arg-type]


def test_row_refusal_message_names_where_the_flag_is_set():
    assert "Key accounts & feed profile" in reporting_gate.REFUSAL_MESSAGE
    assert "Reports expected" in reporting_gate.REFUSAL_MESSAGE
