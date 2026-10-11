"""N-0065 / D-0056: the product-line gate in the database, cip_test only.

Applies migration 20261006_0024 (when cip_test lacks the gate functions; from
round 3 cip_test is at 20261007_0025) and inserts three fixture products inside
one transaction that is always rolled back, binds the settings the API would
bind (from product_line_scope_for), and counts what the connection can read and
update in dim_product. Skips on any database other than cip_test. Never writes
to cip.
"""

from __future__ import annotations

import importlib.util
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.product_line_scope import (
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
    scope_csv,
)

_MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261006_0024_product_line_access.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_20261006_0024", _MIGRATION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def gated_conn():
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"product-line gate test runs on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    try:
        has_fn = conn.execute(
            text("select count(*) from pg_proc where proname = 'cip_product_line_visible'")
        ).scalar_one()
        if not has_fn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                _load_migration().upgrade()
        # Fixture products (rolled back with everything else): two on line A, one on line B.
        tag = uuid.uuid4().hex[:8]
        line_a, line_b = f"N0065-A-{tag}", f"N0065-B-{tag}"
        for i, line in enumerate((line_a, line_a, line_b)):
            conn.execute(
                text(
                    "insert into dim_product (sku, name, is_active, product_line) "
                    "values (:sku, :name, true, :line)"
                ),
                {"sku": f"N0065-{tag}-{i}", "name": f"N0065 gate fixture {i}", "line": line},
            )
        yield conn, [(line_a, 2), (line_b, 1)]
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


def _bind(conn, read: frozenset[str], edit: frozenset[str]) -> None:
    conn.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": scope_csv(read)})
    conn.execute(text("select set_config('cip.editable_product_lines', :v, true)"), {"v": scope_csv(edit)})


def _count(conn) -> int:
    return int(conn.execute(text("select count(*) from dim_product")).scalar_one())


def _touch(conn, line: str) -> int:
    """No-op update; returns how many rows the policy let through."""
    res = conn.execute(
        text("update dim_product set product_line = product_line where product_line = :l"), {"l": line}
    )
    return int(res.rowcount)


def test_db_unset_scope_still_sees_every_product(gated_conn) -> None:
    conn, _ = gated_conn
    assert conn.execute(text("select current_database()")).scalar_one() == "cip_test"
    assert conn.execute(text("select current_setting('cip.product_lines', true)")).scalar_one() in (None, "")
    unset_total = _count(conn)
    assert unset_total > 0
    _bind(conn, *product_line_scope_for(is_admin=True, assignments=[]))
    assert _count(conn) == unset_total


def test_db_admin_with_no_rows_sees_and_edits_every_line(gated_conn) -> None:
    conn, lines = gated_conn
    total = _count(conn)
    _bind(conn, *product_line_scope_for(is_admin=True, assignments=[]))
    assert _count(conn) == total
    for line, n in lines:
        assert _touch(conn, line) == n


def test_db_non_admin_with_no_rows_sees_no_products(gated_conn) -> None:
    conn, lines = gated_conn
    _bind(conn, *product_line_scope_for(is_admin=False, assignments=[]))
    assert _count(conn) == 0
    assert _touch(conn, lines[0][0]) == 0


def test_db_read_only_line_is_visible_but_not_editable(gated_conn) -> None:
    conn, lines = gated_conn
    (line_a, n_a), (line_b, n_b) = lines
    _bind(conn, *product_line_scope_for(is_admin=False, assignments=[(line_a, False), (line_b, True)]))
    assert _count(conn) == n_a + n_b
    assert _touch(conn, line_a) == 0  # read-only
    assert _touch(conn, line_b) == n_b  # read and edit
    pid_a = conn.execute(
        text("select id from dim_product where product_line = :l limit 1"), {"l": line_a}
    ).scalar_one()
    assert conn.execute(text("select cip_product_id_visible(:p)"), {"p": pid_a}).scalar_one() is True
    assert conn.execute(text("select cip_product_id_editable(:p)"), {"p": pid_a}).scalar_one() is False


def test_db_unassigned_line_is_hidden(gated_conn) -> None:
    conn, lines = gated_conn
    (line_a, n_a), (line_b, _) = lines
    _bind(conn, *product_line_scope_for(is_admin=False, assignments=[(line_a, True)]))
    assert _count(conn) == n_a
    assert _touch(conn, line_b) == 0


# --- Round 2 (GOV-008 C1/K2): request-path SessionLocal() and AsyncSession get the scope ---
# The Session after_begin listener (app.core.product_line_scope) binds the request contextvars
# at the start of every ORM transaction. Before it, a sync SessionLocal() read as unset (open).


@contextmanager
def _request_scope(read, edit):
    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        yield
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)


def _session_on(conn):
    """A SessionLocal() session joined to the fixture transaction (migration + fixtures live there)."""
    from app.db.session_sync import SessionLocal

    return SessionLocal(bind=conn, join_transaction_mode="create_savepoint")


def _session_count(conn, read, edit) -> int:
    with _request_scope(read, edit):
        with _session_on(conn) as s:
            return int(s.execute(text("select count(*) from dim_product")).scalar_one())


def test_db_sessionlocal_follows_the_bound_request_scope(gated_conn) -> None:
    conn, lines = gated_conn
    (line_a, n_a), _ = lines
    # Worker / script: contextvars unset -> no set_config -> gate open. Runs first: a later
    # rolled-back set leaves the placeholder at '' on this connection.
    total = _session_count(conn, None, None)
    assert total > 0
    assert _session_count(conn, *product_line_scope_for(is_admin=False, assignments=[])) == 0
    assert _session_count(conn, *product_line_scope_for(is_admin=True, assignments=[])) == total
    one_line = product_line_scope_for(is_admin=False, assignments=[(line_a, False)])
    assert _session_count(conn, *one_line) == n_a
    # The scoped sessions left the setting at '' on this connection. Under 0024 the gate read
    # that as "no lines"; from 0025 it is open. Either way a worker reusing the connection is
    # bound open ('*') by the listener.
    assert conn.execute(text("select current_setting('cip.product_lines', true)")).scalar_one() == ""
    assert _session_count(conn, None, None) == total


def test_db_sessionlocal_read_only_line_cannot_be_written(gated_conn) -> None:
    conn, lines = gated_conn
    (line_a, _), (line_b, n_b) = lines
    scope = product_line_scope_for(is_admin=False, assignments=[(line_a, False), (line_b, True)])
    upd = text("update dim_product set product_line = product_line where product_line = :l")
    with _request_scope(*scope):
        with _session_on(conn) as s:
            assert s.execute(upd, {"l": line_a}).rowcount == 0  # read-only line
            assert s.execute(upd, {"l": line_b}).rowcount == n_b
            s.rollback()


def test_db_sessionlocal_rebinds_after_commit(gated_conn) -> None:
    conn, lines = gated_conn
    (line_a, n_a), _ = lines
    count = text("select count(*) from dim_product")
    with _request_scope(*product_line_scope_for(is_admin=True, assignments=[])):
        with _session_on(conn) as s:
            total = int(s.execute(count).scalar_one())
            s.commit()
            # What a real commit leaves for the next transaction: an empty setting
            # (0024: no lines; from 0025: open).
            conn.execute(text("select set_config('cip.product_lines', '', true)"))
            conn.execute(text("select set_config('cip.editable_product_lines', '', true)"))
            # The next transaction is re-bound by the listener, so the admin still sees all.
            assert int(s.execute(count).scalar_one()) == total
    # The direction that matters from 0025: a leftover '' is open, so a one-line user must
    # be re-bound after a commit, or they would see every line.
    one_line = product_line_scope_for(is_admin=False, assignments=[(line_a, False)])
    with _request_scope(*one_line):
        with _session_on(conn) as s:
            assert int(s.execute(count).scalar_one()) == n_a
            s.commit()
            conn.execute(text("select set_config('cip.product_lines', '', true)"))
            conn.execute(text("select set_config('cip.editable_product_lines', '', true)"))
            assert int(s.execute(count).scalar_one()) == n_a


def _require_cip_test(s) -> None:
    db = s.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        pytest.skip(f"runs on cip_test only (current_database()={db})")


def test_db_real_commit_keeps_scope_and_does_not_leak_through_the_pool() -> None:
    """Plain SessionLocal() on the pooled sync engine, read-only transactions, a real COMMIT."""
    from app.db.session_sync import SessionLocal

    show = text("select current_setting('cip.product_lines', true)")
    with _request_scope(frozenset({"N0065-ROUND2"}), frozenset()):
        with SessionLocal() as s:
            _require_cip_test(s)
            s.execute(text("SET TRANSACTION READ ONLY"))
            assert s.execute(show).scalar_one() == "N0065-ROUND2"
            s.commit()
            s.execute(text("SET TRANSACTION READ ONLY"))
            assert s.execute(show).scalar_one() == "N0065-ROUND2"  # survives the commit
            s.rollback()
    # Same pool, worker context: the request's value is gone (transaction-local). A
    # connection that carried a scope is re-bound open ('*'), never left at '' (= nothing).
    for _ in range(3):
        with SessionLocal() as s:
            _require_cip_test(s)
            assert s.execute(show).scalar_one() in (None, "*")
            s.rollback()


def test_db_async_session_keeps_scope_across_commit() -> None:
    import asyncio

    from app.db.session import AsyncSessionLocal

    show = text("select current_setting('cip.product_lines', true)")

    async def go() -> tuple[str, str | None, str | None]:
        async with AsyncSessionLocal() as s:
            db = (await s.execute(text("select current_database()"))).scalar_one()
            if db != "cip_test":
                return db, None, None
            await s.execute(text("SET TRANSACTION READ ONLY"))
            before = (await s.execute(show)).scalar_one()
            await s.commit()
            await s.execute(text("SET TRANSACTION READ ONLY"))
            after = (await s.execute(show)).scalar_one()
            await s.rollback()
            return db, before, after

    with _request_scope(frozenset({"N0065-ASYNC"}), frozenset()):
        db, before, after = asyncio.run(go())
    if db != "cip_test":
        pytest.skip(f"runs on cip_test only (current_database()={db})")
    assert before == after == "N0065-ASYNC"
