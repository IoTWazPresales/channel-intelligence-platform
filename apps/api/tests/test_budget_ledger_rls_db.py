"""Product-line row security on budget_ledger_entry (20261113_0062). cip_test only.

One transaction, always rolled back. The test applies 0062's own downgrade() first (the
20261110_0061 shape, row security off), seeds two products on two fixture lines and three ledger
rows, and shows the old leak: a user scoped to one line reads the other line's rows. It then applies
0062's upgrade() and measures, as the non-superuser NOBYPASSRLS role from tests/_rls_role.py, that
a user who can see a line sees its ledger rows and a user who cannot does not, through raw SQL and
through the ledger position read. Finally downgrade() then upgrade() again: each removes or restores
exactly the row security and the two policies, and no row changes.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from tests._rls_role import engage_nonsuperuser_role, release_nonsuperuser_role

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_M62 = "20261113_0062_budget_ledger_entry_rls.py"
_M25 = "20261007_0025_product_line_rls_inline.py"


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


def _scope(conn, read: str, edit: str = "") -> None:
    conn.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": read})
    conn.execute(text("select set_config('cip.editable_product_lines', :v, true)"), {"v": edit})


def _rls(conn) -> tuple[bool, bool]:
    row = conn.execute(
        text(
            "select relrowsecurity, relforcerowsecurity from pg_class "
            "where relname = 'budget_ledger_entry'"
        )
    ).one()
    return bool(row[0]), bool(row[1])


def _policies(conn) -> dict[str, str]:
    return {
        str(name): str(cmd)
        for name, cmd in conn.execute(
            text("select policyname, cmd from pg_policies where tablename = 'budget_ledger_entry'")
        ).all()
    }


def _visible(conn, tag: str) -> set[str]:
    return {
        str(r[0])
        for r in conn.execute(
            text("select source_event_id from budget_ledger_entry where source_event_id like :t"),
            {"t": f"{tag}:%"},
        ).all()
    }


def _owner_count(conn) -> int:
    _scope(conn, "", "")  # '' is an open scope (0025)
    return int(conn.execute(text("select count(*) from budget_ledger_entry")).scalar_one())


def _try_insert(conn, tag: str, name: str, product_id: int, line: str) -> str:
    sp = conn.begin_nested()
    try:
        conn.execute(
            text(
                "insert into budget_ledger_entry (entry_type, product_line, product_id, "
                "landed_quarter, amount_usd, source_event_id) "
                "values ('commit', :l, :p, '2026Q4', 1, :e)"
            ),
            {"l": line, "p": product_id, "e": f"{tag}:{name}"},
        )
        return "ok"
    except Exception as exc:  # noqa: BLE001 - classified below
        return "RLS" if "row-level security" in str(exc) else f"ERR:{type(exc).__name__}"
    finally:
        sp.rollback()


def test_budget_ledger_rows_follow_product_line_access() -> None:
    eng = _engine()
    conn = eng.connect()
    try:
        db = conn.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        if db != "cip_test":
            pytest.skip(f"runs on cip_test only (current_database()={db})")
        conn.rollback()
        tx = conn.begin()
        engaged = False
        try:
            from alembic.operations import Operations
            from alembic.runtime.migration import MigrationContext

            m62 = _load(_M62)
            m25 = _load(_M25)
            ops_ctx = MigrationContext.configure(conn)

            # ---- 0061 shape: no row security on the ledger
            with Operations.context(ops_ctx):
                m62.downgrade()
            assert _rls(conn) == (False, False)
            assert _policies(conn) == {}

            tag = "w1d-" + uuid.uuid4().hex[:8]
            line_a, line_b = f"W1D-A-{tag}", f"W1D-B-{tag}"
            pid = {}
            for key, line in (("A", line_a), ("B", line_b)):
                pid[key] = int(
                    conn.execute(
                        text(
                            "insert into dim_product (sku, name, is_active, product_line) "
                            "values (:s, :n, true, :l) returning id"
                        ),
                        {"s": f"W1D-{tag}-{key}", "n": f"W1D fixture {key}", "l": line},
                    ).scalar_one()
                )
            seed = [
                ("commit", line_a, pid["A"], 100, "commit-a"),
                ("commit", line_b, pid["B"], 200, "commit-b"),
                ("transfer", line_a, None, 5, "transfer-a"),  # line-level row, no product
            ]
            for entry_type, line, product_id, amount, name in seed:
                conn.execute(
                    text(
                        "insert into budget_ledger_entry (entry_type, product_line, product_id, "
                        "landed_quarter, amount_usd, source_event_id) "
                        "values (:t, :l, :p, '2026Q4', :a, :e)"
                    ),
                    {
                        "t": entry_type,
                        "l": line,
                        "p": product_id,
                        "a": amount,
                        "e": f"{tag}:{name}",
                    },
                )
            every = {f"{tag}:commit-a", f"{tag}:commit-b", f"{tag}:transfer-a"}
            count_before = _owner_count(conn)

            # ---- old wrong: a user scoped to line A reads line B's row
            engaged = engage_nonsuperuser_role(conn)
            who = conn.execute(
                text(
                    "select current_user, rolsuper, rolbypassrls from pg_roles "
                    "where rolname = current_user"
                )
            ).one()
            print("measured as", who[0], "rolsuper", who[1], "rolbypassrls", who[2])
            assert not who[1] and not who[2]
            _scope(conn, line_a)
            # 0061 shape: no row security, every line is readable.
            assert _visible(conn, tag) == every
            release_nonsuperuser_role(conn, engaged)
            engaged = False

            # ---- 0062
            with Operations.context(ops_ctx):
                m62.upgrade()
            assert _rls(conn) == (True, True)
            assert _policies(conn) == {"cip_pl_select": "SELECT", "cip_pl_insert": "INSERT"}
            # A protected table by the 0025 rule (product_id column + cip_pl_select policy).
            assert "budget_ledger_entry" in {t for t, _c in m25.protected_tables(conn)}
            assert _owner_count(conn) == count_before

            engaged = engage_nonsuperuser_role(conn)
            # New right: each line sees its own product rows only. The row with no product stays
            # visible to every scope, as on every other product-keyed table.
            _scope(conn, line_a)
            assert _visible(conn, tag) == {f"{tag}:commit-a", f"{tag}:transfer-a"}
            _scope(conn, line_b)
            assert _visible(conn, tag) == {f"{tag}:commit-b", f"{tag}:transfer-a"}
            _scope(conn, "!")
            assert _visible(conn, tag) == {f"{tag}:transfer-a"}
            _scope(conn, f"{line_a},{line_b}")
            assert _visible(conn, tag) == every
            _scope(conn, "*")
            assert _visible(conn, tag) == every

            # The ledger position read (GET /budgets/ledger) through the service.
            from app.services.budget_ledger import position_rows

            session = Session(bind=conn, join_transaction_mode="create_savepoint")
            try:
                def by_line() -> dict[str, dict]:
                    return {
                        r["product_line"]: r
                        for r in position_rows(session)
                        if r["product_line"] in (line_a, line_b)
                    }

                _scope(conn, line_a)
                seen = by_line()
                assert set(seen) == {line_a}
                assert seen[line_a]["committed"] == 100.0
                _scope(conn, line_b)
                seen = by_line()
                assert seen[line_b]["committed"] == 200.0
                # Line A shows up for a line-B user only through the no-product transfer row.
                assert line_a not in seen or seen[line_a]["committed"] == 0.0
            finally:
                session.close()

            # Writes: an editor of line A may append a line-A product row, not a line-B one.
            _scope(conn, line_a, line_a)
            assert _try_insert(conn, tag, "ins-a", pid["A"], line_a) == "ok"
            assert _try_insert(conn, tag, "ins-b", pid["B"], line_b) == "RLS"
            _scope(conn, line_a, "!")
            assert _try_insert(conn, tag, "ins-a2", pid["A"], line_a) == "RLS"
            release_nonsuperuser_role(conn, engaged)
            engaged = False

            # ---- downgrade removes exactly what upgrade added; upgrade restores it; no row changes
            with Operations.context(ops_ctx):
                m62.downgrade()
            assert _rls(conn) == (False, False)
            assert _policies(conn) == {}
            assert _owner_count(conn) == count_before
            with Operations.context(ops_ctx):
                m62.upgrade()
                m62.upgrade()  # idempotent
            assert _rls(conn) == (True, True)
            assert _policies(conn) == {"cip_pl_select": "SELECT", "cip_pl_insert": "INSERT"}
            assert _owner_count(conn) == count_before
        finally:
            release_nonsuperuser_role(conn, engaged)
            tx.rollback()
    finally:
        conn.close()
        eng.dispose()
