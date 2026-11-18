"""Customer promotion calendar (20261118_0063): migration, tenant isolation, upload apply, timeline.

cip_test only (skips on any other database). One transaction per test, always rolled back; the
migration's own upgrade() / downgrade() are applied inside it, so the tables need not exist before.
Written for the coordinator to run on ``cip_test`` one suite at a time; it was NOT run by the lane
that wrote it.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_M63 = "20261118_0063_customer_calendar.py"
_TABLES = ("customer_calendar_mapping_profile", "customer_calendar_event")

_CSV = (
    "Retailer,Campaign Name,Type,Start,End\n"
    "{a},Autumn push,Campaign,2026-03-10,2026-03-20\n"
    "{a},Brand month,Pillar,2026-04-01,2026-04-30\n"
    "{unknown},Ghost sale,Campaign,2026-03-01,2026-03-02\n"
    "{a},Backwards,Campaign,2026-05-10,2026-05-01\n"
)


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
            yield connection
        finally:
            tx.rollback()
    finally:
        connection.close()
        eng.dispose()


@pytest.fixture()
def migrated(conn):
    """The two tables, created by the migration's own upgrade() inside the test transaction."""
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    mod = _load_migration()
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        mod.downgrade()
        mod.upgrade()
    return mod, ctx


def _exists(conn, table: str) -> bool:
    return conn.execute(
        text("select to_regclass(:t) is not null"), {"t": f"public.{table}"}
    ).scalar_one()


def _bind(conn, tenant: str) -> None:
    conn.execute(
        text("select set_config('cip.customer_calendar_tenant_id', :t, true)"), {"t": tenant}
    )


def _customer(session: Session, tenant: str, tag: str, label: str):
    from app.models.dimensions import DimCustomer

    row = DimCustomer(
        tenant_id=tenant, code=f"CAL-{tag}-{label}", name=f"Calendar Test {tag} {label}"
    )
    session.add(row)
    session.flush()
    return row


# --------------------------------------------------------------------------- migration


def test_migration_creates_both_tables_with_row_security_policies_and_checks(
    conn, migrated
) -> None:
    from alembic.operations import Operations

    mod, ctx = migrated
    for table in _TABLES:
        assert _exists(conn, table)
        rls = conn.execute(
            text("select relrowsecurity, relforcerowsecurity from pg_class where relname = :t"),
            {"t": table},
        ).one()
        assert (bool(rls[0]), bool(rls[1])) == (True, True)
    pols = {
        (str(t), str(c))
        for t, c in conn.execute(
            text("select tablename, cmd from pg_policies where tablename in :t").bindparams(
                bindparam("t", expanding=True)
            ),
            {"t": list(_TABLES)},
        ).all()
    }
    assert ("customer_calendar_event", "SELECT") in pols
    assert ("customer_calendar_event", "INSERT") in pols
    assert ("customer_calendar_event", "DELETE") in pols
    assert ("customer_calendar_event", "UPDATE") not in pols
    assert {c for t, c in pols if t == "customer_calendar_mapping_profile"} == {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }

    tag = uuid.uuid4().hex[:8]
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        cust = _customer(session, "default", tag, "A")
        # Row security is tenant-bound; bind the tenant so only the CHECK can refuse the row.
        _bind(conn, "default")
        # end >= start is enforced by the database
        sp = conn.begin_nested()
        with pytest.raises(DBAPIError, match="ck_customer_calendar_event_dates"):
            conn.execute(
                text(
                    "insert into customer_calendar_event "
                    "(customer_id, name, kind, start_date, end_date, upload_id) "
                    "values (:c, 'x', 'campaign', '2026-03-10', '2026-03-01', 'u')"
                ),
                {"c": cust.id},
            )
        sp.rollback()
        # kind is campaign | pillar | other
        sp = conn.begin_nested()
        with pytest.raises(DBAPIError, match="ck_customer_calendar_event_kind"):
            conn.execute(
                text(
                    "insert into customer_calendar_event "
                    "(customer_id, name, kind, start_date, end_date, upload_id) "
                    "values (:c, 'x', 'banana', '2026-03-01', '2026-03-02', 'u')"
                ),
                {"c": cust.id},
            )
        sp.rollback()
    finally:
        session.close()

    # downgrade drops both tables; upgrade twice is idempotent
    with Operations.context(ctx):
        mod.downgrade()
    assert not any(_exists(conn, t) for t in _TABLES)
    with Operations.context(ctx):
        mod.upgrade()
        mod.upgrade()
    assert all(_exists(conn, t) for t in _TABLES)


def test_row_security_isolates_tenants_for_the_app_role(conn, migrated) -> None:
    from tests._rls_role import engage_nonsuperuser_role, release_nonsuperuser_role

    tag = uuid.uuid4().hex[:8]
    t_a, t_b = f"cal-a-{tag}", f"cal-b-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    engaged = False
    try:
        cust_a = _customer(session, t_a, tag, "A")
        cust_b = _customer(session, t_b, tag, "B")
        insert = text(
            "insert into customer_calendar_event "
            "(tenant_id, customer_id, name, kind, start_date, end_date, upload_id) "
            "values (:t, :c, :n, 'campaign', '2026-03-01', '2026-03-02', 'u')"
        )
        for tenant, cust in ((t_a, cust_a), (t_b, cust_b)):
            _bind(conn, tenant)
            conn.execute(insert, {"t": tenant, "c": cust.id, "n": f"event-{tenant}"})

        engaged = engage_nonsuperuser_role(conn)
        count_sql = text("select name from customer_calendar_event where upload_id = 'u'")
        _bind(conn, t_a)
        assert [r[0] for r in conn.execute(count_sql).all()] == [f"event-{t_a}"]
        _bind(conn, t_b)
        assert [r[0] for r in conn.execute(count_sql).all()] == [f"event-{t_b}"]
        # No tenant bound: nothing is visible and nothing can be written.
        _bind(conn, "")
        assert conn.execute(count_sql).all() == []
        sp = conn.begin_nested()
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(insert, {"t": t_a, "c": cust_a.id, "n": "unbound"})
        sp.rollback()
        # A bound tenant cannot write another tenant's row.
        _bind(conn, t_a)
        sp = conn.begin_nested()
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(insert, {"t": t_b, "c": cust_b.id, "n": "cross-tenant"})
        sp.rollback()
    finally:
        release_nonsuperuser_role(conn, engaged)
        session.close()


# --------------------------------------------------------------------------- upload


def test_apply_is_idempotent_and_never_creates_customers_or_crosses_tenants(conn, migrated) -> None:
    from app.models.customer_calendar import CustomerCalendarEvent
    from app.models.dimensions import DimCustomer
    from app.services.cpor.customer_calendar.pipeline import apply_upload, preview_upload
    from sqlalchemy import func, select

    tag = uuid.uuid4().hex[:8]
    t_a, t_b = f"cal-a-{tag}", f"cal-b-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        cust_a = _customer(session, t_a, tag, "A")
        # A customer with the same name in another tenant must not receive tenant A's events.
        other = DimCustomer(tenant_id=t_b, code=f"CAL-{tag}-B", name=cust_a.name)
        session.add(other)
        session.flush()
        n_customers = session.scalar(select(func.count()).select_from(DimCustomer))

        data = _CSV.format(a=cust_a.name, unknown="Nobody Matches This").encode("utf-8")
        prev = preview_upload(session, t_a, filename="Cal 2026.csv", data=data)
        assert prev["will_insert"] == 2
        assert prev["will_replace"] == 0
        assert [c["customer_id"] for c in prev["customers"]] == [cust_a.id]
        assert prev["unresolved_customers"] == [{"token": "Nobody Matches This", "rows": 1}]
        assert [e["code"] for e in prev["row_errors"]] == ["end_before_start"]
        assert prev["upload_id"] == "cal-2026.csv"

        first = apply_upload(session, t_a, filename="Cal 2026.csv", data=data, actor="tester")
        assert (first["inserted"], first["replaced"]) == (2, 0)
        again = apply_upload(session, t_a, filename="Cal 2026.csv", data=data, actor="tester")
        assert (again["inserted"], again["replaced"]) == (2, 2)

        def count(tenant: str) -> int:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(CustomerCalendarEvent)
                    .where(CustomerCalendarEvent.tenant_id == tenant)
                )
            )

        assert count(t_a) == 2
        assert count(t_b) == 0
        assert (
            session.scalar(select(func.count()).select_from(DimCustomer)) == n_customers
        )  # no master created

        # A different upload id does not replace the first one.
        apply_upload(
            session, t_a, filename="Cal 2026.csv", data=data, upload_id="second", actor="tester"
        )
        assert count(t_a) == 4

        # Naming one customer for the whole file works without a customer column.
        plain = b"Name,Start\nOpen day,2026-06-01\n"
        out = apply_upload(session, t_a, filename="plain.csv", data=plain, customer_id=cust_a.id)
        assert out["inserted"] == 1
        # ... and another tenant's customer id is refused.
        from app.services.cpor.customer_calendar.pipeline import CalendarUploadError

        with pytest.raises(CalendarUploadError) as exc:
            apply_upload(session, t_a, filename="plain.csv", data=plain, customer_id=other.id)
        assert exc.value.code == "customer_not_found"
    finally:
        session.close()


def test_profile_crud_is_tenant_scoped(conn, migrated) -> None:
    from app.services.cpor.customer_calendar.pipeline import (
        CalendarUploadError,
        delete_profile,
        list_profiles,
        save_profile,
    )
    from app.services.cpor.customer_calendar.profiles import default_calendar_profile

    tag = uuid.uuid4().hex[:8]
    t_a, t_b = f"cal-a-{tag}", f"cal-b-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        assert [p.profile_code for p in list_profiles(session, t_a)] == [
            "customer_calendar_default_v1"
        ]
        body = default_calendar_profile()
        body.update(
            profile_code="custom", display_name="Custom", header_row_index=2, is_default=True
        )
        row = save_profile(session, t_a, body, actor="tester")
        assert row.is_default is True and row.header_row_index == 2
        assert len(list_profiles(session, t_a)) == 2
        # same code is allowed in another tenant, not twice in one
        save_profile(session, t_b, body, actor="tester")
        with pytest.raises(CalendarUploadError) as dup:
            save_profile(session, t_a, body, actor="tester")
        assert dup.value.status == 409
        with pytest.raises(CalendarUploadError) as bad:
            save_profile(
                session, t_a, {**body, "profile_code": "bad", "column_map_json": {"name": ["N"]}}
            )
        assert bad.value.status == 422
        # tenant B cannot delete tenant A's profile
        with pytest.raises(CalendarUploadError) as nf:
            delete_profile(session, t_b, row.id)
        assert nf.value.status == 404
        delete_profile(session, t_a, row.id)
    finally:
        session.close()


# --------------------------------------------------------------------------- timeline


def _case(
    session: Session,
    tenant: str,
    customer_id: int,
    tag: str,
    label: str,
    start: date,
    end: date,
    **extra,
):
    from app.models.cpor import CporCase

    row = CporCase(
        case_code=f"CAL-{tag}-{label}",
        tenant_id=tenant,
        customer_id=customer_id,
        promotion_type="test",
        window_start=start,
        window_end=end,
        status=extra.pop("status", "active"),
        **extra,
    )
    session.add(row)
    session.flush()
    return row


def test_timeline_lists_open_promotions_events_and_clashes_only(conn, migrated) -> None:
    from app.models.cpor import CporCaseLine
    from app.models.customer_calendar import CustomerCalendarEvent
    from app.models.dimensions import DimProduct
    from app.services.cpor.customer_calendar.timeline import build_timeline

    tag = uuid.uuid4().hex[:8]
    tenant = f"cal-t-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        cust = _customer(session, tenant, tag, "A")
        other_cust = _customer(session, tenant, tag, "B")
        live = _case(session, tenant, cust.id, tag, "live", date(2026, 3, 1), date(2026, 3, 15))
        later = _case(session, tenant, cust.id, tag, "later", date(2026, 6, 1), date(2026, 6, 10))
        _case(
            session,
            tenant,
            cust.id,
            tag,
            "cancelled",
            date(2026, 3, 1),
            date(2026, 3, 15),
            status="cancelled",
        )
        _case(
            session,
            tenant,
            cust.id,
            tag,
            "fixture",
            date(2026, 3, 1),
            date(2026, 3, 15),
            intelligence_exclude=True,
        )
        replaced = _case(session, tenant, cust.id, tag, "old", date(2026, 3, 1), date(2026, 3, 15))
        replaced.superseded_by_case_id = live.id
        voided = _case(session, tenant, cust.id, tag, "voided", date(2026, 3, 1), date(2026, 3, 15))
        _case(session, tenant, other_cust.id, tag, "otherc", date(2026, 3, 1), date(2026, 3, 15))
        product = DimProduct(
            sku=f"CAL-{tag}", name="Calendar fixture", is_active=True, product_line=f"CAL-{tag}"
        )
        session.add(product)
        session.flush()
        session.add(
            CporCaseLine(
                case_id=voided.id,
                product_id=product.id,
                window_start=date(2026, 3, 1),
                window_end=date(2026, 3, 15),
                srp=1,
                vat_rate=0,
                dealer_margin_pct=0,
                estimate_qty=0,
                remark="x [voided]",
            )
        )
        _bind(conn, tenant)
        for name, kind, start, end, cid in (
            ("Spring pillar", "pillar", date(2026, 3, 10), date(2026, 3, 31), cust.id),
            ("Far event", "campaign", date(2026, 9, 1), date(2026, 9, 5), cust.id),
            (
                "Other customer event",
                "campaign",
                date(2026, 3, 1),
                date(2026, 3, 31),
                other_cust.id,
            ),
        ):
            session.add(
                CustomerCalendarEvent(
                    tenant_id=tenant,
                    customer_id=cid,
                    name=name,
                    kind=kind,
                    start_date=start,
                    end_date=end,
                    upload_id="u1",
                )
            )
        session.flush()

        out = build_timeline(session, tenant, customer_id=cust.id)
        assert out is not None
        assert out["customer"]["id"] == cust.id
        assert [p["case_code"] for p in out["promotions"]] == [live.case_code, later.case_code]
        assert [e["name"] for e in out["calendar_events"]] == ["Spring pillar", "Far event"]
        assert len(out["clashes"]) == 1
        clash = out["clashes"][0]
        assert clash["case_id"] == live.id
        assert clash["event_name"] == "Spring pillar"
        assert (clash["overlap_start"], clash["overlap_end"], clash["overlap_days"]) == (
            "2026-03-10",
            "2026-03-15",
            6,
        )

        # the date range narrows both lists
        narrow = build_timeline(
            session,
            tenant,
            customer_id=cust.id,
            date_from=date(2026, 5, 1),
            date_to=date(2026, 7, 1),
        )
        assert [p["case_code"] for p in narrow["promotions"]] == [later.case_code]
        assert narrow["calendar_events"] == [] and narrow["clashes"] == []

        # another tenant cannot read this customer's timeline
        assert build_timeline(session, f"cal-x-{tag}", customer_id=cust.id) is None
    finally:
        session.close()


# --------------------------------------------------------------------------- endpoints


def test_endpoints_preview_apply_and_timeline(conn, migrated) -> None:
    from app.api.v1.endpoints import cpor_customer_calendar as ep
    from app.core.security import get_current_user
    from app.main import app
    from fastapi.testclient import TestClient

    tag = uuid.uuid4().hex[:8]
    tenant = f"cal-e-{tag}"
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    user = {"id": 1, "email": "cal-test@example.invalid", "role": "admin", "tenant_id": tenant}

    def _db():
        yield session

    app.dependency_overrides[ep._sync_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[ep._require_calendar_writer] = lambda: user
    try:
        cust = _customer(session, tenant, tag, "A")
        case = _case(session, tenant, cust.id, tag, "live", date(2026, 3, 1), date(2026, 3, 15))
        client = TestClient(app)
        csv_bytes = _CSV.format(a=cust.name, unknown="Nobody").encode("utf-8")
        files = {"file": ("cal.csv", csv_bytes, "text/csv")}

        r = client.post("/api/v1/customer-calendar/upload/preview", files=files)
        assert r.status_code == 200, r.text
        assert r.json()["will_insert"] == 2

        r = client.post(
            "/api/v1/customer-calendar/upload/apply", files=files, data={"confirm": "false"}
        )
        assert r.status_code == 400
        r = client.post(
            "/api/v1/customer-calendar/upload/apply", files=files, data={"confirm": "true"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 2

        r = client.get("/api/v1/customer-calendar/timeline", params={"customer_id": cust.id})
        assert r.status_code == 200, r.text
        body = r.json()
        assert [p["case_id"] for p in body["promotions"]] == [case.id]
        assert len(body["calendar_events"]) == 2
        assert [c["event_name"] for c in body["clashes"]] == ["Autumn push"]

        r = client.get("/api/v1/customer-calendar/timeline", params={"customer_id": 0})
        assert r.status_code == 422
        r = client.get(
            "/api/v1/customer-calendar/timeline",
            params={"customer_id": cust.id, "from": "2026-05-01", "to": "2026-04-01"},
        )
        assert r.status_code == 422
        r = client.get("/api/v1/customer-calendar/profiles")
        assert r.status_code == 200
        assert r.json()["profiles"][0]["profile_code"] == "customer_calendar_default_v1"
    finally:
        app.dependency_overrides.pop(ep._sync_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(ep._require_calendar_writer, None)
        session.close()
