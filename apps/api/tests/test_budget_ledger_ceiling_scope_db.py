"""Portfolio ceiling counts every product line. Listing stays on the caller's scope.

cip_test only. One transaction, always rolled back. Migration 20261113_0062 is applied
inside that transaction when the database does not have it yet, then rolled back, so
cip is never written and cip_test is not left migrated.

A planner scoped to one product line has two campaign commits of 600 on two lines.
The tenant ceiling is 1000. The export gate must block, because the draw is 1200.
The same planner's ledger listing still shows only their own line. An open scope,
which already saw both lines, still draws 1200 and still blocks at 1000. A ceiling
of 1500 still allows the export.
"""

from __future__ import annotations

import importlib.util
import uuid
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


def _scope(conn, read: str) -> None:
    conn.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": read})


def _product_lines(conn) -> str | None:
    return conn.execute(text("select current_setting('cip.product_lines', true)")).scalar_one()


class _OpenSession:
    """Hand the test session to generate_export without closing the outer transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_scoped_planner_export_blocks_on_tenant_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    eng = _engine()
    conn = eng.connect()
    try:
        db = conn.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        if db != "cip_test":
            pytest.fail(
                f"stop: budget ceiling test runs on cip_test only (current_database()={db})"
            )
        conn.rollback()
        tx = conn.begin()
        engaged = False
        try:
            from alembic.operations import Operations
            from alembic.runtime.migration import MigrationContext
            from app.api.v1.endpoints import cpor_exports
            from app.services import commercial_tenant_profile as tenant_profile
            from app.services.budget_ledger import position_rows, used_usd
            from app.services.cpor.budget_reapproval import (
                evaluate_money_position,
                should_require_reapproval,
            )

            m62 = _load(_M62)
            ops_ctx = MigrationContext.configure(conn)
            with Operations.context(ops_ctx):
                m62.downgrade()
                m62.upgrade()

            tag = "w1d-ceil-" + uuid.uuid4().hex[:8]
            line_a, line_b = f"W1D-A-{tag}", f"W1D-B-{tag}"
            quarter = "2026Q4"
            product_ids = {}
            for key, line in (("A", line_a), ("B", line_b)):
                product_ids[key] = int(
                    conn.execute(
                        text(
                            "insert into dim_product (sku, name, is_active, product_line) "
                            "values (:s, :n, true, :l) returning id"
                        ),
                        {"s": f"W1D-{tag}-{key}", "n": f"W1D fixture {key}", "l": line},
                    ).scalar_one()
                )
            seed = [
                ("commit", line_a, product_ids["A"], 600, None, "commit-a"),
                ("commit", line_b, product_ids["B"], 600, None, "commit-b"),
                ("reserve", line_b, product_ids["B"], 5000, "non_campaign", "reserve-b"),
                ("cap", line_a, product_ids["A"], 50, "line_cap", "cap-a"),
            ]
            for entry_type, line, product_id, amount, source_tag, name in seed:
                conn.execute(
                    text(
                        "insert into budget_ledger_entry (entry_type, product_line, product_id, "
                        "landed_quarter, amount_usd, source_tag, source_event_id) "
                        "values (:t, :l, :p, :q, :a, :g, :e)"
                    ),
                    {
                        "t": entry_type,
                        "l": line,
                        "p": product_id,
                        "q": quarter,
                        "a": amount,
                        "g": source_tag,
                        "e": f"{tag}:{name}",
                    },
                )

            engaged = engage_nonsuperuser_role(conn)
            session = Session(bind=conn, join_transaction_mode="create_savepoint")
            try:
                _scope(conn, line_a)
                draw = used_usd(session)
                quarter_draw = used_usd(session, landed_quarter=quarter)
                other_quarter = used_usd(session, landed_quarter="1999Q1")
                print("scoped_draw", draw, "quarter_draw", quarter_draw)
                assert draw == 1200.0
                assert quarter_draw == 1200.0
                assert other_quarter == 0.0
                assert _product_lines(conn) == line_a

                def listed() -> dict[str, dict]:
                    return {
                        row["product_line"]: row
                        for row in position_rows(session)
                        if row["product_line"] in (line_a, line_b)
                    }

                seen = listed()
                assert set(seen) == {line_a}
                assert seen[line_a]["committed"] == 600.0

                monkeypatch.setattr(tenant_profile, "HARD_ENFORCE_BUDGET", True)
                monkeypatch.setattr(
                    "app.services.cpor.budget_reapproval.money_ceiling_usd",
                    lambda: 1000.0,
                )
                position = evaluate_money_position(session, case_id=0, include_this_case=False)
                assert position["portfolio_committed_usd"] == 1200.0
                assert position["money_over"] is True
                assert should_require_reapproval(position) is True

                class _Case:
                    id = 0

                monkeypatch.setattr(cpor_exports, "SessionLocal", lambda: _OpenSession(session))
                monkeypatch.setattr(cpor_exports, "_load_case", lambda _session, _case_id: _Case())
                with pytest.raises(HTTPException) as caught:
                    cpor_exports.generate_export(0, {"id": "w1d-planner"})
                assert caught.value.status_code == 409
                detail = caught.value.detail
                print("export_gate", detail["message"])
                assert "export blocked" in detail["message"]
                assert detail["budget"]["portfolio_committed_usd"] == 1200.0
                assert detail["budget"]["money_ceiling_usd"] == 1000.0
                assert _product_lines(conn) == line_a
                assert listed() == seen

                _scope(conn, "*")
                assert used_usd(session) == 1200.0
                open_position = evaluate_money_position(session, case_id=0, include_this_case=False)
                assert open_position["portfolio_committed_usd"] == 1200.0
                assert open_position["money_over"] is True

                monkeypatch.setattr(
                    "app.services.cpor.budget_reapproval.money_ceiling_usd",
                    lambda: 1500.0,
                )
                under = evaluate_money_position(session, case_id=0, include_this_case=False)
                assert under["portfolio_committed_usd"] == 1200.0
                assert under["money_over"] is False
                assert should_require_reapproval(under) is False
                _scope(conn, line_a)
                under_scoped = evaluate_money_position(session, case_id=0, include_this_case=False)
                assert under_scoped["portfolio_committed_usd"] == 1200.0
                assert under_scoped["money_over"] is False
            finally:
                session.close()
        finally:
            release_nonsuperuser_role(conn, engaged)
            tx.rollback()
    finally:
        conn.close()
        eng.dispose()
