"""B-3: a customer merge moves customer calendar events to the keeper under forced row security.

cip_test only. One transaction, always rolled back. Migration 20261118_0063 is applied inside
it (downgrade then upgrade, so the UPDATE grant and policy are the edited ones), then rolled
back. The merge runs as a role that is subject to row security (``tests/_rls_role.py``), with
no calendar tenant bound by the caller, which is how the real merge starts.

Before the fix the merge counted 0 rows (forced row security hid them), skipped the table, and
``_assert_zero_loser_refs`` passed over live references.
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
_M63 = "20261118_0063_customer_calendar.py"
_GUC = "cip.customer_calendar_tenant_id"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0063", _VERSIONS / _M63)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, poolclass=NullPool)


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
        try:
            from alembic.operations import Operations
            from alembic.runtime.migration import MigrationContext

            mod = _load_migration()
            with Operations.context(MigrationContext.configure(connection)):
                mod.downgrade()
                mod.upgrade()
            yield connection
        finally:
            tx.rollback()
    finally:
        connection.close()
        eng.dispose()


def _customer(session: Session, tenant: str, tag: str, label: str):
    from app.models.dimensions import DimCustomer

    row = DimCustomer(
        tenant_id=tenant, code=f"CM-{tag}-{label}", name=f"Calendar merge {tag} {label}"
    )
    session.add(row)
    session.flush()
    return row


def _event(conn, tenant: str, customer_id: int, name: str, upload: str) -> None:
    # Row security is forced on the table, so even the owner session must bind the tenant to
    # seed a row. The binding is cleared straight after, so each test starts with nothing bound.
    conn.execute(text("select set_config(:g, :t, true)"), {"g": _GUC, "t": tenant})
    conn.execute(
        text(
            "insert into customer_calendar_event "
            "(tenant_id, customer_id, name, kind, start_date, end_date, upload_id) "
            "values (:t, :c, :n, 'campaign', '2026-03-01', '2026-03-10', :u)"
        ),
        {"t": tenant, "c": customer_id, "n": name, "u": upload},
    )
    conn.execute(text("select set_config(:g, '', true)"), {"g": _GUC})


def _events_by_customer(conn, tenant: str) -> dict[int, list[str]]:
    # Forced row security: bind the tenant to read its rows, then clear the binding again.
    conn.execute(text("select set_config(:g, :t, true)"), {"g": _GUC, "t": tenant})
    rows = conn.execute(
        text(
            "select customer_id, name from customer_calendar_event "
            "where tenant_id = :t order by customer_id, name"
        ),
        {"t": tenant},
    ).all()
    conn.execute(text("select set_config(:g, '', true)"), {"g": _GUC})
    out: dict[int, list[str]] = {}
    for customer_id, name in rows:
        out.setdefault(int(customer_id), []).append(str(name))
    return out


def test_merge_moves_calendar_events_to_the_keeper_and_proves_zero_loser_refs(conn) -> None:
    from app.services.customer_full_repoint import (
        _assert_zero_loser_refs,
        count_customer_fk_refs,
        repoint_customer_footprint_full,
    )
    from app.services.customer_leftover_repair import leftover_fk_counts

    tag = uuid.uuid4().hex[:8]
    tenant = f"cm-t-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    engaged = False
    try:
        keeper = _customer(session, tenant, tag, "keeper")
        loser = _customer(session, tenant, tag, "loser")
        _event(conn, tenant, keeper.id, "keeper own", f"u-{tag}-k")
        _event(conn, tenant, loser.id, "loser one", f"u-{tag}-l")
        _event(conn, tenant, loser.id, "loser two", f"u-{tag}-l")
        session.flush()

        engaged = engage_nonsuperuser_role(conn)
        # Not vacuous: with no tenant bound, forced row security really hides the rows.
        assert conn.execute(text("select current_setting(:g, true)"), {"g": _GUC}).scalar() in (
            None,
            "",
        )
        hidden = conn.execute(
            text("select count(*) from customer_calendar_event where customer_id = :c"),
            {"c": loser.id},
        ).scalar_one()
        assert hidden == 0

        # The merge's own counts are real, and the caller's setting is left as it was.
        assert count_customer_fk_refs(session, loser.id)["customer_calendar_event.customer_id"] == 2
        assert leftover_fk_counts(session, loser.id)["customer_calendar_event.customer_id"] == 2
        assert conn.execute(text("select current_setting(:g, true)"), {"g": _GUC}).scalar() in (
            None,
            "",
        )

        stats = repoint_customer_footprint_full(session, loser_id=loser.id, keeper_id=keeper.id)
        assert stats["table_updates"]["customer_calendar_event.customer_id"] == 2
        _assert_zero_loser_refs(session, loser.id)
        assert "customer_calendar_event.customer_id" not in count_customer_fk_refs(
            session, loser.id
        )
        assert conn.execute(text("select current_setting(:g, true)"), {"g": _GUC}).scalar() in (
            None,
            "",
        )

        release_nonsuperuser_role(conn, engaged)
        engaged = False
        assert _events_by_customer(conn, tenant) == {
            keeper.id: ["keeper own", "loser one", "loser two"]
        }
    finally:
        release_nonsuperuser_role(conn, engaged)
        session.close()


def test_merge_refuses_when_keeper_is_in_another_tenant(conn) -> None:
    from app.services.customer_full_repoint import (
        CustomerFullRepointAbortError,
        repoint_customer_footprint_full,
    )

    tag = uuid.uuid4().hex[:8]
    t_loser, t_keeper = f"cm-l-{tag}", f"cm-k-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    engaged = False
    try:
        keeper = _customer(session, t_keeper, tag, "keeper")
        loser = _customer(session, t_loser, tag, "loser")
        _event(conn, t_loser, loser.id, "loser one", f"u-{tag}")
        session.flush()

        engaged = engage_nonsuperuser_role(conn)
        with pytest.raises(CustomerFullRepointAbortError) as caught:
            repoint_customer_footprint_full(session, loser_id=loser.id, keeper_id=keeper.id)
        assert "tenant" in str(caught.value)

        release_nonsuperuser_role(conn, engaged)
        engaged = False
        assert _events_by_customer(conn, t_loser) == {loser.id: ["loser one"]}
    finally:
        release_nonsuperuser_role(conn, engaged)
        session.close()


def test_update_policy_is_tenant_bound_for_the_app_role(conn) -> None:
    """The new UPDATE policy: nothing bound updates no row; another tenant's rows stay untouched."""
    tag = uuid.uuid4().hex[:8]
    t_a, t_b = f"cm-a-{tag}", f"cm-b-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    engaged = False
    try:
        cust_a = _customer(session, t_a, tag, "A")
        cust_b = _customer(session, t_b, tag, "B")
        _event(conn, t_a, cust_a.id, "a event", f"u-{tag}-a")
        _event(conn, t_b, cust_b.id, "b event", f"u-{tag}-b")
        session.flush()

        engaged = engage_nonsuperuser_role(conn)
        move = text(
            "update customer_calendar_event set updated_at = now() where tenant_id in (:a, :b)"
        )
        assert conn.execute(move, {"a": t_a, "b": t_b}).rowcount == 0  # nothing bound
        conn.execute(text("select set_config(:g, :t, true)"), {"g": _GUC, "t": t_a})
        assert conn.execute(move, {"a": t_a, "b": t_b}).rowcount == 1  # only tenant A's row
    finally:
        release_nonsuperuser_role(conn, engaged)
        session.close()
