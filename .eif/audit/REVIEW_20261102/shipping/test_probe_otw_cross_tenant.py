"""GOV-008 probe: On the water and port conditions across two tenants, cip_test only, one rolled-back outer transaction.

Tenant A has a vessel at sea and a port condition. Tenant B has one line at sea whose observation history shares a
line_identity_key string with an observation of tenant A (identity keys carry no tenant). B must see none of A.
Run from apps/api:  .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <this file>
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import engine
from app.main import app
from app.models.facts import FactInboundShipment
from app.models.iam import AppUser, Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.models.shipment_water import PortCondition

AS_OF = "2026-10-28"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def two(monkeypatch):
    monkeypatch.setattr(get_settings(), "cip_auth_mode", "session")
    tag = secrets.token_hex(5)
    pw = secrets.token_urlsafe(24)
    async with engine.connect() as conn:
        outer = await conn.begin()
        assert (await conn.execute(text("select current_database()"))).scalar_one() == "cip_test"
        seed = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        previous = app.dependency_overrides.get(get_db)

        async def db_for_request():
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as s:
                yield s

        app.dependency_overrides[get_db] = db_for_request
        try:
            ta, tb = f"g8a-{tag}", f"g8b-{tag}"
            for t in (ta, tb):
                seed.add(Tenant(id=t, name="GOV-008 cross-tenant"))
            await seed.flush()
            for t, role in ((ta, "admin"), (tb, "admin"), (tb, "viewer")):
                seed.add(AppUser(tenant_id=t, email=f"{role}-{t}@example.invalid", display_name=f"{role} {t}", role=role, password_hash=hash_password(pw)))
            tpl = ImportTemplate(slug=f"g8x-{tag}", display_name="g8x", pipeline_handler="inbound_shipments")
            seed.add(tpl)
            await seed.flush()
            src = SourceDefinition(import_template_id=int(tpl.id), code=f"g8x-{tag}", name="g8x", source_kind="file")
            seed.add(src)
            await seed.flush()
            jobs = {}
            for t in (ta, tb):
                j = ImportJob(tenant_id=t, source_id=int(src.id), template_slug="inbound_shipments", status="completed", stage="loaded",
                              file_name="ACZA Shipped Unshipped 20261027.xlsx", completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc))
                seed.add(j)
                jobs[t] = j
            ja_old = ImportJob(tenant_id=ta, source_id=int(src.id), template_slug="inbound_shipments", status="completed", stage="loaded",
                               file_name="ACZA Shipped Unshipped 20260901.xlsx", completed_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
            seed.add(ja_old)
            await seed.flush()
            shared_key = f"order:SHARED|{tag}"
            n = 0

            async def add(t, *, qty, eta, ident):
                nonlocal n
                n += 1
                line = ShipmentEvidenceLine(import_job_id=int(jobs[t].id), source_sheet="Shipped", source_row_number=n, report_type="acza_workbook_shipped",
                                            line_state="shipped", source_key=f"g8x-{tag}-{n}", raw_source_row={}, order_no=f"SO{n}", order_line="1",
                                            item_code=f"IT{n}", quantity=qty, product_resolution_status="unresolved", distributor_resolution_status="unresolved")
                seed.add(line)
                await seed.flush()
                f = FactInboundShipment(tenant_id=t, import_job_id=int(jobs[t].id), source_key=f"g8x-{tag}-{n}", fact_upsert_key=f"g8x-fk-{tag}-{n}",
                                        shipment_evidence_line_id=int(line.id), source_row_number=n, report_type="acza_workbook_shipped", line_state="shipped",
                                        raw_source_row={}, order_no=f"SO{n}", order_line="1", item_code=f"IT{n}", quantity=qty, amount=qty * 10.0,
                                        currency_code="USD", ship_way="SEA", on_board_date=date(2026, 9, 19), port_eta_date=date.fromisoformat(eta),
                                        origin_hub="ckg", forwarder_code="COSCO", deliver_port="ZADUR", ship_confirm_date=date(2026, 9, 18),
                                        product_resolution_status="unresolved", distributor_resolution_status="unresolved", status="scheduled")
                seed.add(f)
                await seed.flush()
                when = datetime(2026, 10, 27, 8, tzinfo=timezone.utc)
                seed.add(ShipmentEvidenceObservation(line_identity_key=ident, import_job_id=int(jobs[t].id), source_key=f"g8x-{tag}-{n}-o",
                                                     source_row_hash=hashlib.sha1(f"{tag}-{n}".encode()).hexdigest(), evidence_line_id=int(line.id),
                                                     valid_from=when, observed_at=when, source_row_number=n, report_type="acza_workbook_shipped",
                                                     line_state="shipped", raw_source_row={}, quantity=qty, port_eta_date=date.fromisoformat(eta),
                                                     on_board_date=date(2026, 9, 19), product_resolution_status="unresolved",
                                                     distributor_resolution_status="unresolved"))
                await seed.flush()
                return f

            await add(ta, qty=500, eta="2026-11-05", ident=f"a-only-{tag}")
            # Tenant B's line; its identity key string also occurs in an OLDER observation of tenant A with an earlier ETA.
            await add(tb, qty=7, eta="2026-11-30", ident=shared_key)
            old_when = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
            seed.add(ShipmentEvidenceObservation(line_identity_key=shared_key, import_job_id=int(ja_old.id), source_key=f"g8x-{tag}-a-old",
                                                 source_row_hash=hashlib.sha1(f"{tag}-aold".encode()).hexdigest(), evidence_line_id=None,
                                                 valid_from=old_when, observed_at=old_when, source_row_number=99, report_type="acza_workbook_shipped",
                                                 line_state="shipped", raw_source_row={}, quantity=1, port_eta_date=date(2026, 10, 1),
                                                 on_board_date=date(2026, 9, 1), product_resolution_status="unresolved",
                                                 distributor_resolution_status="unresolved"))
            seed.add(PortCondition(tenant_id=ta, port_code="ZADUR", delay_days=12, note="A only", entered_by="A admin"))
            await seed.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                h = {}
                for t, role in ((ta, "admin"), (tb, "admin"), (tb, "viewer")):
                    r = await client.post("/api/v1/auth/login", json={"email": f"{role}-{t}@example.invalid", "password": pw})
                    assert r.status_code == 200, r.text
                    h[(t, role)] = {"Authorization": f"Bearer {r.json()['token']}"}
                yield client, h, ta, tb
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
            await seed.close()
            await outer.rollback()


@pytest.mark.anyio
async def test_tenant_b_sees_none_of_tenant_a(two):
    client, h, ta, tb = two
    a = (await client.get("/api/v1/shipping/on-the-water", params={"as_of": AS_OF}, headers=h[(ta, "admin")])).json()
    bview = (await client.get("/api/v1/shipping/on-the-water", params={"as_of": AS_OF}, headers=h[(tb, "viewer")])).json()
    print("\nB viewer at_sea (product_id NULL rows; viewer product-line scope):", bview["tiles"]["at_sea"]["units"])
    b = (await client.get("/api/v1/shipping/on-the-water", params={"as_of": AS_OF}, headers=h[(tb, "admin")])).json()
    print("\nA at_sea:", a["tiles"]["at_sea"]["units"], "| B admin at_sea:", b["tiles"]["at_sea"]["units"])
    print("B vessels:", [(v["units"], v["slip_days"], v["history"]) for v in b["vessels"]])
    print("B port_rows conditions:", [(r["code"], r.get("condition")) for r in b["port_rows"]])
    assert a["tiles"]["at_sea"]["units"] == 500
    assert b["tiles"]["at_sea"]["units"] == 7
    assert all(r.get("condition") is None for r in b["port_rows"]), "tenant A's port condition leaked to B"
    lst = (await client.get("/api/v1/shipping/port-conditions", headers=h[(tb, "viewer")])).json()
    print("B port-conditions list:", lst)
    assert lst["items"] == [] and lst["current"] == []
    # A's vessel key used by B on the grid returns nothing.
    akey = a["vessels"][0]["key"]
    rl = (await client.get("/api/v1/shipping/lines", params={"vessel": akey, "limit": 50}, headers=h[(tb, "viewer")])).json()
    print("B lines for A's vessel key:", len(rl["items"]), "(B's own vessel shares the key shape:", akey, ")")
    # B admin posts; A's current condition is unchanged.
    r = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "ZADUR", "delay_days": 1}, headers=h[(tb, "admin")])
    assert r.status_code == 201
    a_list = (await client.get("/api/v1/shipping/port-conditions", headers=h[(ta, "admin")])).json()
    print("A current after B's post:", a_list["current"])
    assert a_list["current"][0]["delay_days"] == 12
    # The history leak: B's slip/first ETA computed from tenant A's observation sharing the identity key string.
    bv = b["vessels"][0]
    print("B vessel history (A's old observation had ETA 2026-10-01):", bv["history"], "slip", bv["slip_days"])


@pytest.mark.anyio
async def test_port_condition_input_edges(two):
    client, h, ta, tb = two
    cases = {
        "nan": {"port_code": "ZADUR", "delay_days": float("nan")},
        "negative": {"port_code": "ZADUR", "delay_days": -1},
        "too_big": {"port_code": "ZADUR", "delay_days": 366},
        "unknown_port": {"port_code": "XXX", "delay_days": 3},
        "long_note": {"port_code": "ZADUR", "delay_days": 3, "note": "x" * 1001},
        "spaces_code": {"port_code": "  zadur ", "delay_days": 3},
    }
    for label, body in cases.items():
        try:
            r = await client.post("/api/v1/shipping/port-conditions", json=body, headers=h[(ta, "admin")])
            print(f"\n{label}: {r.status_code} {r.text[:160]}")
        except Exception as exc:  # noqa: BLE001 - NaN is not valid JSON on the wire
            print(f"\n{label}: client refused to send ({type(exc).__name__}: {exc})")
    raw = await client.post("/api/v1/shipping/port-conditions", content=b'{"port_code":"ZADUR","delay_days":NaN}',
                            headers={**h[(ta, "admin")], "Content-Type": "application/json"})
    print("raw NaN body:", raw.status_code, raw.text[:200])
    inf = await client.post("/api/v1/shipping/port-conditions", content=b'{"port_code":"ZADUR","delay_days":Infinity}',
                            headers={**h[(ta, "admin")], "Content-Type": "application/json"})
    print("raw Infinity body:", inf.status_code, inf.text[:200])
    anon = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "ZADUR", "delay_days": 1})
    anon_get = await client.get("/api/v1/shipping/on-the-water")
    print("anonymous POST:", anon.status_code, "| anonymous GET on-the-water:", anon_get.status_code)
