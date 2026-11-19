"""B-1: the money ceiling counts the case being checked (``include_this_case=True``).

cip_test only. One transaction, always rolled back. Migration 20261113_0062 is applied
inside that transaction (downgrade then upgrade) so the product-line row security is real,
then rolled back, so cip is never written and cip_test is not left migrated.

Ceiling 1000, approved draw 900 (a commit row on another product line than the planner's).
A draft case with 500 of support must be blocked at the export gate (409): the draw would be
1400. A case that already has commit rows is in the draw and must not be counted twice.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from tests._rls_role import engage_nonsuperuser_role, release_nonsuperuser_role

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_M62 = "20261113_0062_budget_ledger_entry_rls.py"


def _load(fname: str):
    spec = importlib.util.spec_from_file_location("_mig_" + fname.split("_")[1], _VERSIONS / fname)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, poolclass=NullPool)


class _OpenSession:
    """Hand the test session to generate_export without closing the outer transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.fixture()
def conn():
    eng = _engine()
    connection = eng.connect()
    try:
        db = connection.execute(text("select current_database()")).scalar_one()
        if db != "cip_test":
            pytest.skip(f"runs on cip_test only (current_database()={db})")
        connection.rollback()
        tx = connection.begin()
        engaged = False
        try:
            from alembic.operations import Operations
            from alembic.runtime.migration import MigrationContext

            m62 = _load(_M62)
            with Operations.context(MigrationContext.configure(connection)):
                m62.downgrade()
                m62.upgrade()
            engaged = engage_nonsuperuser_role(connection)
            yield connection
        finally:
            release_nonsuperuser_role(connection, engaged)
            tx.rollback()
    finally:
        connection.close()
        eng.dispose()


def _seed(conn, session: Session, tag: str):
    """Two product lines and a customer. Helpers make draft cases (500 support) and commit rows."""
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer

    line_a, line_b = f"B1-A-{tag}", f"B1-B-{tag}"
    product_ids = {}
    for key, line in (("A", line_a), ("B", line_b)):
        product_ids[key] = int(
            conn.execute(
                text(
                    "insert into dim_product (sku, name, is_active, product_line) "
                    "values (:s, :n, true, :l) returning id"
                ),
                {"s": f"B1-{tag}-{key}", "n": f"B1 fixture {key}", "l": line},
            ).scalar_one()
        )
    customer = DimCustomer(tenant_id="default", code=f"B1-{tag}", name=f"B1 customer {tag}")
    session.add(customer)
    session.flush()

    def make_case(label: str) -> CporCase:
        case = CporCase(
            case_code=f"B1-{tag}-{label}",
            tenant_id="default",
            customer_id=customer.id,
            promotion_type="test",
            window_start=date(2026, 10, 1),
            window_end=date(2026, 10, 31),
            status="draft",
        )
        session.add(case)
        session.flush()
        session.add(
            CporCaseLine(
                case_id=case.id,
                product_id=product_ids["A"],
                pod_quarter="2026Q4",
                window_start=date(2026, 10, 1),
                window_end=date(2026, 10, 31),
                srp=1,
                vat_rate=0,
                dealer_margin_pct=0,
                estimate_qty=1,
                ttl_support_usd=500,
            )
        )
        session.flush()
        return case

    def commit_row(case_id, line, product_key, amount, name):
        conn.execute(
            text(
                "insert into budget_ledger_entry (entry_type, product_line, product_id, "
                "landed_quarter, amount_usd, case_id, source_event_id) "
                "values ('commit', :l, :p, '2026Q4', :a, :c, :e)"
            ),
            {
                "l": line,
                "p": product_ids[product_key],
                "a": amount,
                "c": case_id,
                "e": f"{tag}:{name}",
            },
        )

    return {
        "line_a": line_a,
        "line_b": line_b,
        "make_case": make_case,
        "commit_row": commit_row,
    }


def _gate(monkeypatch, ceiling: float) -> None:
    from app.services import commercial_tenant_profile as tenant_profile

    monkeypatch.setattr(tenant_profile, "HARD_ENFORCE_BUDGET", True)
    monkeypatch.setattr(tenant_profile, "CONSTRAINT_AXIS", "money")
    monkeypatch.setattr(tenant_profile, "OVER_BUDGET_ACTION", "require_reapproval")
    monkeypatch.setattr("app.services.cpor.budget_reapproval.money_ceiling_usd", lambda: ceiling)


def test_draft_case_with_500_support_is_blocked_at_export_over_ceiling(
    conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.endpoints import cpor_exports
    from app.services.budget_ledger import used_usd
    from app.services.cpor.budget_reapproval import (
        evaluate_money_position,
        portfolio_committed_usd,
        should_require_reapproval,
    )

    tag = uuid.uuid4().hex[:8]
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        seed = _seed(conn, session, tag)
        draft = seed["make_case"]("draft")
        seed["commit_row"](None, seed["line_b"], "B", 900, "approved-draw")
        # A planner scoped to line A only: the draw still counts line B (0062 fix).
        conn.execute(
            text("select set_config('cip.product_lines', :v, true)"), {"v": seed["line_a"]}
        )
        _gate(monkeypatch, 1000.0)

        assert used_usd(session) == 900.0
        assert portfolio_committed_usd(session, include_case_id=None) == 900.0
        assert portfolio_committed_usd(session, include_case_id=draft.id) == 1400.0
        position = evaluate_money_position(session, case_id=draft.id, include_this_case=True)
        assert position["portfolio_committed_usd"] == 1400.0
        assert position["money_over"] is True
        assert should_require_reapproval(position) is True

        monkeypatch.setattr(cpor_exports, "SessionLocal", lambda: _OpenSession(session))
        with pytest.raises(HTTPException) as caught:
            cpor_exports.generate_export(draft.id, {"id": "b1-planner"})
        assert caught.value.status_code == 409
        assert caught.value.detail["budget"]["portfolio_committed_usd"] == 1400.0
        assert "export blocked" in caught.value.detail["message"]
    finally:
        session.close()


def test_case_with_commit_rows_is_not_double_counted(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.cpor.budget_reapproval import evaluate_money_position, portfolio_committed_usd

    tag = uuid.uuid4().hex[:8]
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        seed = _seed(conn, session, tag)
        approved = seed["make_case"]("approved")
        # 500 is this case's own commit (line A), 400 is another draw on line B: draw 900.
        seed["commit_row"](approved.id, seed["line_a"], "A", 500, "own-commit")
        seed["commit_row"](None, seed["line_b"], "B", 400, "other-draw")
        conn.execute(
            text("select set_config('cip.product_lines', :v, true)"), {"v": seed["line_b"]}
        )
        _gate(monkeypatch, 1000.0)

        # The case is in the ledger draw even though the caller's scope cannot list its line.
        assert portfolio_committed_usd(session, include_case_id=None) == 900.0
        assert portfolio_committed_usd(session, include_case_id=approved.id) == 900.0
        position = evaluate_money_position(session, case_id=approved.id, include_this_case=True)
        assert position["portfolio_committed_usd"] == 900.0
        assert position["money_over"] is False
    finally:
        session.close()
