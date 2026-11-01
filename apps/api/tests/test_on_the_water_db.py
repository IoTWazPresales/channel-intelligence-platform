"""On the water through the API on cip_test: one isolated tenant, one rolled-back transaction.

Covers the SPEC acceptance list for the data: vessel grouping, position, slip from the observations, the four
totals, sea only, the currency rule, needs a look, the current port condition, the grid filter by vessel.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import engine
from app.main import app
from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment
from app.models.iam import AppUser, Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation

AS_OF = "2026-10-28"
SHIPPED = "acza_workbook_shipped"
UNSHIP = "acza_workbook_unship"


def _d(s: str) -> date:
    return date.fromisoformat(s)


@pytest.fixture
async def water(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "cip_auth_mode", "session")
    tag = secrets.token_hex(5)
    tenant = f"otw-{tag}"
    pw = secrets.token_urlsafe(24)
    async with engine.connect() as conn:
        outer = await conn.begin()
        if (await conn.execute(text("select current_database()"))).scalar_one() != "cip_test":
            await outer.rollback()
            pytest.skip("cip_test only")
        seed = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        previous = app.dependency_overrides.get(get_db)

        async def db_for_request():
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                yield session

        app.dependency_overrides[get_db] = db_for_request
        try:
            seed.add(Tenant(id=tenant, name="On the water fixture"))
            await seed.flush()
            seed.add(AppUser(tenant_id=tenant, email=f"admin-{tag}@example.invalid", display_name="Fixture admin", role="admin", password_hash=hash_password(pw)))
            seed.add(AppUser(tenant_id=tenant, email=f"viewer-{tag}@example.invalid", display_name="Fixture viewer", role="viewer", password_hash=hash_password(pw)))
            dist_a = DimDistributor(tenant_id=tenant, code=f"OTWA{tag}"[:32], name="Mustek")
            dist_b = DimDistributor(tenant_id=tenant, code=f"OTWB{tag}"[:32], name="Rectron")
            seed.add_all([dist_a, dist_b])
            template = ImportTemplate(slug=f"otw-{tag}", display_name="otw", pipeline_handler="inbound_shipments")
            seed.add(template)
            await seed.flush()
            source = SourceDefinition(import_template_id=int(template.id), code=f"otw-{tag}", name="otw", source_kind="file")
            seed.add(source)
            await seed.flush()
            jobs = {}
            for label, fname in (("old", "ACZA Shipped Unshipped 20260929.xlsx"), ("new", "ACZA Shipped Unshipped 20261027.xlsx")):
                job = ImportJob(tenant_id=tenant, source_id=int(source.id), template_slug="inbound_shipments", status="completed", stage="loaded",
                                file_name=fname, completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc))
                seed.add(job)
                jobs[label] = job
            await seed.flush()

            n = 0

            async def add(*, state="shipped", report=SHIPPED, qty=10, amount=100.0, currency="USD", ship_way="SEA", on_board=None, eta=None, ata=None, pod=None,
                          hub="ckg", fwd="COSCO", port="ZAJNB", dist=dist_a, model="P1503", delivery=None, exwork=None, confirm=None,
                          first_eta=None, history=True, vessel=None, voyage=None):
                nonlocal n
                n += 1
                line = ShipmentEvidenceLine(
                    import_job_id=int(jobs["new"].id), source_sheet="Shipped", source_row_number=n, report_type=report, line_state=state,
                    source_key=f"sk-{tag}-{n}", raw_source_row={}, order_no=f"SO{n}", order_line="1", item_code=f"IT{n}", quantity=qty,
                    product_resolution_status="unresolved", distributor_resolution_status="unresolved",
                )
                seed.add(line)
                await seed.flush()
                fact = FactInboundShipment(
                    tenant_id=tenant, import_job_id=int(jobs["new"].id), source_key=f"sk-{tag}-{n}", fact_upsert_key=f"fk-{tag}-{n}",
                    shipment_evidence_line_id=int(line.id), source_row_number=n, report_type=report, line_state=state, raw_source_row={},
                    order_no=f"SO{n}", order_line="1", item_code=f"IT{n}", sales_model_name=model, delivery_no=delivery, quantity=qty,
                    amount=amount, currency_code=currency, ship_way=ship_way, on_board_date=on_board and _d(on_board),
                    port_eta_date=eta and _d(eta), port_ata_date=ata and _d(ata), pod_date=pod and _d(pod), origin_hub=hub, forwarder_code=fwd,
                    deliver_port=port, distributor_id=int(dist.id), ship_confirm_date=confirm and _d(confirm), exwork_date=exwork and _d(exwork),
                    vessel_name=vessel, voyage_no=voyage, product_resolution_status="unresolved", distributor_resolution_status="unresolved",
                    status="received" if pod else "scheduled",
                )
                seed.add(fact)
                await seed.flush()
                if history:
                    key = f"idk-{tag}-{n}"
                    for label, eta_v, ob_v, when in (("old", first_eta or eta, on_board, datetime(2026, 9, 29, 8, tzinfo=timezone.utc)),
                                                     ("new", eta, on_board, datetime(2026, 10, 27, 8, tzinfo=timezone.utc))):
                        seed.add(ShipmentEvidenceObservation(
                            line_identity_key=key, import_job_id=int(jobs[label].id), source_key=f"sk-{tag}-{n}-{label}", source_row_hash=hashlib.sha1(f"{label}-{tag}-{n}".encode()).hexdigest(),
                            evidence_line_id=int(line.id) if label == "new" else None, valid_from=when, observed_at=when, source_row_number=n,
                            report_type=report, line_state=state, raw_source_row={}, quantity=qty, port_eta_date=_d(eta_v) if eta_v else None,
                            on_board_date=_d(ob_v) if ob_v else None, product_resolution_status="unresolved", distributor_resolution_status="unresolved",
                        ))
                    await seed.flush()
                return fact

            # Vessel 1: two lines, two distributors, one ETA that moved 14 days since the 29 Sep report.
            v1a = await add(qty=100, amount=1000, on_board="2026-09-19", eta="2026-11-05", first_eta="2026-10-22", dist=dist_a, model="P1503", delivery="D1")
            v1b = await add(qty=50, amount=500, on_board="2026-09-19", eta="2026-11-05", first_eta="2026-10-22", dist=dist_b, model="X1504", delivery="D2", hub="szx")
            # Vessel 2: named, Europe, EUR.
            v2 = await add(qty=40, amount=200, currency="EUR", on_board="2026-10-20", eta="2026-11-20", hub="nl", fwd="PREMIERE", vessel="MSC Anna", voyage="V9", first_eta="2026-11-20")
            # Vessel 3: overdue into Durban.
            v3 = await add(qty=30, amount=300, on_board="2026-09-01", eta="2026-10-20", port="ZADUR", hub="c", fwd="WWP", first_eta="2026-10-20")
            # Air in transit: counted in the sub-line, not drawn.
            await add(qty=7, amount=70, ship_way="AIR", on_board="2026-10-20", eta="2026-10-30", first_eta="2026-10-30")
            # Arrived, not delivered (two ports); one delivered.
            await add(qty=30, ship_way="SEA", on_board="2026-09-10", eta="2026-10-24", ata="2026-10-25", port="ZAJNB", history=False)
            await add(qty=5, on_board="2026-09-10", eta="2026-10-24", ata="2026-10-26", port="MUPLU", history=False)
            await add(qty=99, on_board="2026-09-10", eta="2026-10-24", ata="2026-10-25", pod="2026-10-27", port="ZAJNB", history=False)
            # Booked, not on board yet.
            await add(state="open_order", qty=12, on_board="2026-11-02", eta="2026-12-10", history=False)
            # Needs a look: open from a Shipped sheet, no ship confirm date, ex-works 27 days old; and one that is not old enough.
            nl1 = await add(state="open_order", qty=9, on_board=None, exwork="2026-10-01", history=True, eta=None, first_eta=None, dist=dist_b)
            await add(state="open_order", qty=4, on_board=None, exwork="2026-10-25", history=False)
            await seed.commit()
            ids = {"v1": sorted([int(v1a.id), int(v1b.id)]), "v2": [int(v2.id)], "v3": [int(v3.id)], "needs_look": [int(nl1.id)]}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                headers = {}
                for role in ("admin", "viewer"):
                    login = await client.post("/api/v1/auth/login", json={"email": f"{role}-{tag}@example.invalid", "password": pw})
                    assert login.status_code == 200, login.text
                    headers[role] = {"Authorization": f"Bearer {login.json()['token']}"}
                yield client, headers, ids
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
            await seed.close()
            await outer.rollback()


async def _get(client, headers, **params):
    r = await client.get("/api/v1/shipping/on-the-water", params={"as_of": AS_OF, **params}, headers=headers["admin"])
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.anyio
async def test_totals_vessels_sea_only_and_currencies(water):
    client, headers, _ids = water
    p = await _get(client, headers)
    t = p["tiles"]
    # Sea only: vessel 1 (150), vessel 2 (40), vessel 3 (30); the air line is in the sub-line.
    assert (t["at_sea"]["units"], t["at_sea"]["lines"], t["at_sea"]["vessels"], t["at_sea"]["air_units"]) == (220, 4, 3, 7)
    assert t["at_sea"]["amount"] == [{"currency": "EUR", "amount": 200.0}, {"currency": "USD", "amount": 1800.0}]  # never summed across currencies
    assert t["at_sea"]["overdue_vessels"] == 1
    assert (t["arrived"]["units"], t["arrived"]["lines"]) == (35, 2) and {r["name"]: r["units"] for r in t["arrived"]["by_port"]} == {"City Deep": 30, "Port Louis": 5}
    assert t["booked"] == {"units": 12, "lines": 1}
    assert p["as_of"] == AS_OF and p["report_date"] == "2026-10-27" and p["report_stale"] is False
    assert p["reports"]["count"] == 2 and p["reports"]["earlier"] == 1


@pytest.mark.anyio
async def test_vessel_grouping_distributors_products_slip_and_position(water):
    client, headers, ids = water
    p = await _get(client, headers)
    by_units = {v["units"]: v for v in p["vessels"]}
    v1 = by_units[150]
    assert v1["lines"] == 2 and v1["inferred"] is True and v1["deliveries"] == 2
    assert {d["name"]: d["units"] for d in v1["distributors"]} == {"Mustek": 100, "Rectron": 50}
    assert [x["name"] for x in v1["products"]] == ["P1503", "X1504"]
    assert v1["amount"] == [{"currency": "USD", "amount": 1500.0}]
    assert v1["slip_days"] == 14  # first reported 22 Oct on 29 Sep, now 5 Nov
    assert v1["history"] == {"first_eta": "2026-10-22", "first_report": "2026-09-29", "current_eta": "2026-11-05", "latest_report": "2026-10-27"}
    assert v1["pct"] == round((date(2026, 10, 28) - date(2026, 9, 19)).days / (date(2026, 11, 5) - date(2026, 9, 19)).days * 100, 1)
    assert p["tiles"]["eta_moved"]["vessels_moved"] == 1 and p["tiles"]["eta_moved"]["max_days"] == 14
    named = by_units[40]
    assert named["inferred"] is False and named["vessel_name"] == "MSC Anna" and named["slip_days"] == 0 and named["lane_id"] == "europe_durban"
    overdue = by_units[30]
    assert overdue["overdue"] is True and (overdue["x"], overdue["y"]) == (33.54, 86.18)
    assert overdue["lane_label"].endswith("Durban")


@pytest.mark.anyio
async def test_needs_a_look_and_the_grid_filters(water):
    client, headers, ids = water
    p = await _get(client, headers)
    n = p["needs_look"]
    assert (n["lines"], n["units"]) == (1, 9) and n["distributors"] == [{"name": "Rectron", "units": 9}]
    # The cohort that the "Open the lines" link uses returns the same line.
    r = await client.get("/api/v1/shipping/lines", params={"cohort": "needs_look", "limit": 50}, headers=headers["admin"])
    assert r.status_code == 200, r.text
    assert sorted(int(x["id"]) for x in r.json()["items"]) == ids["needs_look"]
    # Click on a vessel filters the grid to that vessel's lines (and only those).
    vessels = {v["units"]: v for v in p["vessels"]}
    for units, want in ((150, ids["v1"]), (40, ids["v2"]), (30, ids["v3"])):
        r = await client.get("/api/v1/shipping/lines", params={"vessel": vessels[units]["key"], "limit": 50}, headers=headers["admin"])
        assert r.status_code == 200, r.text
        assert sorted(int(x["id"]) for x in r.json()["items"]) == want
    # The map and the tiles follow the same filter: a distributor filter narrows both.
    mustek = (await client.get("/api/v1/shipping/lines", params={"cohort": "needs_look"}, headers=headers["admin"])).json()["items"][0]["distributor_id"]
    narrowed = await _get(client, headers, distributor_id=mustek)
    assert narrowed["tiles"]["at_sea"]["units"] == 0 or narrowed["tiles"]["at_sea"]["units"] < 220
    # The new line fields are in the grid payload.
    row = (await client.get("/api/v1/shipping/lines", params={"vessel": vessels[150]["key"], "limit": 5}, headers=headers["admin"])).json()["items"][0]
    assert row["on_board_date"] == "2026-09-19" and row["port_eta_date"] == "2026-11-05" and row["ship_way"] == "SEA" and row["deliver_port"] == "ZAJNB"


@pytest.mark.anyio
async def test_port_condition_current_row_and_who_may_enter_one(water):
    client, headers, _ids = water
    assert (await _get(client, headers))["port_rows"]  # ports with cargo are listed even without a figure
    first = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "zadur", "delay_days": 15, "note": "congestion"}, headers=headers["admin"])
    assert first.status_code == 201, first.text
    assert first.json()["port_code"] == "ZADUR" and first.json()["entered_by"] == "Fixture admin"
    second = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "ZADUR", "delay_days": 9, "note": "easing"}, headers=headers["admin"])
    assert second.status_code == 201
    p = await _get(client, headers)
    durban = next(r for r in p["port_rows"] if r["code"] == "ZADUR")
    assert durban["condition"]["delay_days"] == 9 and durban["condition"]["note"] == "easing"  # the newest row is current
    listed = (await client.get("/api/v1/shipping/port-conditions", headers=headers["viewer"])).json()
    assert [i["delay_days"] for i in listed["items"]] == [9, 15] and listed["current"][0]["delay_days"] == 9  # history is kept
    # Only an admin enters a figure.
    denied = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "ZADUR", "delay_days": 1}, headers=headers["viewer"])
    assert denied.status_code == 403
    bad = await client.post("/api/v1/shipping/port-conditions", json={"port_code": "ZA DUR!", "delay_days": 1}, headers=headers["admin"])
    assert bad.status_code == 422


@pytest.mark.anyio
async def test_attention_raises_the_needs_a_look_signal(water, monkeypatch):
    client, headers, _ids = water
    # Pin "today" to the fixture's day so the ex-works ages do not drift with the calendar.
    monkeypatch.setattr("app.services.commercial_tenant_profile.reporting_today", lambda tenant="default": date.fromisoformat(AS_OF))
    r = await client.get("/api/v1/brief/signals", headers=headers["admin"])
    assert r.status_code == 200, r.text
    sig = next((s for s in r.json()["signals"] if s["id"] == "shipment_needs_look"), None)
    assert sig is not None
    assert sig["figures"] == {"lines": 1, "units": 9, "days": 7}
    assert sig["action_href"] == "/supply/shipments?cohort=needs_look" and sig["meta"] == "9 units"
