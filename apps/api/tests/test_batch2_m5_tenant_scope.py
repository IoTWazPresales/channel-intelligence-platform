"""GOV-008 review 2 Nov, M5: shipment identity is tenant-scoped.

(a) the On the water history query takes first-seen and first ETA only from the fact's own tenant;
(b) tenant B's shipped load can never delete tenant A's fact (probe P8), with the old global constraint (fails loudly) and
    with migration 20261102_0051 (both tenants hold the fact).

cip_test only; every test rolls back (Postgres DDL is transactional).
"""

from __future__ import annotations

import hashlib
import importlib.util
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, select, text

from app.api.v1.endpoints.shipping_water import _HISTORY_SQL
from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports import shipment_inbound_facts as facts_mod
from tests.shipment_evidence_fixtures import add_evidence_line

API_DIR = Path(__file__).resolve().parents[1]
SHIPPED = "acza_workbook_shipped"


def _migration():
    path = API_DIR / "alembic" / "versions" / "20261102_0051_fact_upsert_key_per_tenant.py"
    spec = importlib.util.spec_from_file_location("m0051", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        tag = uuid.uuid4().hex[:8]
        counter = {"n": 0}

        def tenant(label: str) -> str:
            t = f"m5-{label}-{tag}"
            db.add(Tenant(id=t, name="M5 fixture"))
            db.flush()
            return t

        def job(t: str, file_name: str = "ACZA Shipped Unshipped 20261027.xlsx") -> ImportJob:
            tok = uuid.uuid4().hex[:10]
            tpl = ImportTemplate(slug=f"m5-{tok}", display_name="m5", pipeline_handler="inbound_shipments")
            db.add(tpl)
            db.flush()
            src = SourceDefinition(import_template_id=int(tpl.id), code=f"m5-{tok}", name="m5", source_kind="file")
            db.add(src)
            db.flush()
            j = ImportJob(tenant_id=t, source_id=int(src.id), template_slug="inbound_shipments", status="completed",
                          stage="loaded", file_name=file_name, completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc))
            db.add(j)
            db.flush()
            return j

        def evidence(j: ImportJob, *, qty: float, delivery: str) -> ShipmentEvidenceLine:
            counter["n"] += 1
            return add_evidence_line(
                db,
                import_job_id=int(j.id), source_sheet="Shipped", source_row_number=counter["n"], report_type=SHIPPED,
                line_state="shipped", source_key=f"m5-{tag}-{counter['n']}-{uuid.uuid4().hex[:6]}", raw_source_row={},
                order_no="SO-M5", order_line="1", item_code="IT-M5", quantity=qty, operating_unit="OU-M5",
                delivery_no=delivery, invoice_line="1", ship_confirm_date=date(2026, 10, 1),
                product_resolution_status="unresolved", distributor_resolution_status="unresolved",
            )

        def observation(j: ImportJob, line, *, identity: str, eta: date, when: datetime) -> ShipmentEvidenceObservation:
            counter["n"] += 1
            o = ShipmentEvidenceObservation(
                line_identity_key=identity, import_job_id=int(j.id), source_key=f"m5-o-{tag}-{counter['n']}",
                source_row_hash=hashlib.sha1(f"{tag}-{counter['n']}".encode()).hexdigest(),
                evidence_line_id=int(line.id) if line is not None else None, valid_from=when, observed_at=when,
                source_row_number=counter["n"], report_type=SHIPPED, line_state="shipped", raw_source_row={}, quantity=1,
                port_eta_date=eta, product_resolution_status="unresolved", distributor_resolution_status="unresolved",
            )
            db.add(o)
            db.flush()
            return o

        yield db, tenant, job, evidence, observation
        db.rollback()


def _facts(db, t, delivery):
    return db.execute(select(FactInboundShipment.id, FactInboundShipment.quantity)
                      .where(FactInboundShipment.tenant_id == t, FactInboundShipment.delivery_no == delivery)).all()


def _load_same_line_for_both_tenants(db, tenant, job, evidence):
    ta, tb = tenant("a"), tenant("b")
    ja, jb = job(ta), job(tb)
    delivery = f"D-{uuid.uuid4().hex[:6]}"
    evidence(ja, qty=40, delivery=delivery)
    facts_mod.upsert_inbound_shipment_facts_for_job(db, int(ja.id))
    la = db.scalars(select(FactInboundShipment).where(FactInboundShipment.tenant_id == ta, FactInboundShipment.delivery_no == delivery)).one()
    evidence(jb, qty=3, delivery=delivery)
    return ta, tb, jb, delivery, la


# ------------------------------------------------------------------------------------------------------ (a) history


def test_history_query_never_takes_another_tenants_observation(world):
    db, tenant, job, evidence, observation = world
    ta, tb = tenant("a"), tenant("b")
    ja, jb = job(ta, "ACZA Shipped Unshipped 20260901.xlsx"), job(tb)
    shared = f"order:SHARED|{uuid.uuid4().hex[:6]}"
    # Tenant A saw the identity first (ETA 1 Oct, 1 Sep); tenant B's own line was first seen on 27 Oct with ETA 30 Nov.
    observation(ja, None, identity=shared, eta=date(2026, 10, 1), when=datetime(2026, 9, 1, 8, tzinfo=timezone.utc))
    line_b = evidence(jb, qty=7, delivery="D-HIST")
    observation(jb, line_b, identity=shared, eta=date(2026, 11, 30), when=datetime(2026, 10, 27, 8, tzinfo=timezone.utc))
    fact_b = FactInboundShipment(
        tenant_id=tb, import_job_id=int(jb.id), source_key=line_b.source_key, fact_upsert_key=f"m5-hist-{uuid.uuid4().hex}",
        shipment_evidence_line_id=int(line_b.id), source_row_number=1, report_type=SHIPPED, line_state="shipped",
        raw_source_row={}, order_no="SO-M5", order_line="1", item_code="IT-M5", quantity=7, delivery_no="D-HIST",
        product_resolution_status="unresolved", distributor_resolution_status="unresolved", status="scheduled",
    )
    db.add(fact_b)
    db.flush()
    rows = db.execute(_HISTORY_SQL, {"ids": [int(fact_b.id)]}).all()
    seen_jobs = {int(r.import_job_id) for r in rows}
    assert seen_jobs == {int(jb.id)}, "history must come from the fact's own tenant only"
    eta = next(r for r in rows if r.kind == "eta")
    assert eta.d == date(2026, 11, 30)


def test_history_query_still_finds_the_same_tenants_earlier_observation(world):
    """Control: the tenant filter must not remove a tenant's own earlier report."""
    db, tenant, job, evidence, observation = world
    ta = tenant("a")
    j_old, j_new = job(ta, "ACZA Shipped Unshipped 20260901.xlsx"), job(ta)
    ident = f"order:OWN|{uuid.uuid4().hex[:6]}"
    observation(j_old, None, identity=ident, eta=date(2026, 10, 1), when=datetime(2026, 9, 1, 8, tzinfo=timezone.utc))
    line = evidence(j_new, qty=7, delivery="D-OWN")
    observation(j_new, line, identity=ident, eta=date(2026, 11, 30), when=datetime(2026, 10, 27, 8, tzinfo=timezone.utc))
    fact = FactInboundShipment(
        tenant_id=ta, import_job_id=int(j_new.id), source_key=line.source_key, fact_upsert_key=f"m5-own-{uuid.uuid4().hex}",
        shipment_evidence_line_id=int(line.id), source_row_number=1, report_type=SHIPPED, line_state="shipped",
        raw_source_row={}, order_no="SO-M5", order_line="1", item_code="IT-M5", quantity=7, delivery_no="D-OWN",
        product_resolution_status="unresolved", distributor_resolution_status="unresolved", status="scheduled",
    )
    db.add(fact)
    db.flush()
    rows = db.execute(_HISTORY_SQL, {"ids": [int(fact.id)]}).all()
    first_eta = next(r for r in rows if r.kind == "eta")
    assert first_eta.d == date(2026, 10, 1) and int(first_eta.import_job_id) == int(j_old.id)


# ---------------------------------------------------------------------------------------------- (b) fact upsert key


def test_p8_other_tenants_load_never_deletes_this_tenants_fact_on_the_old_constraint(world):
    db, tenant, job, evidence, _ = world
    constraint = db.scalar(text(
        "select pg_get_constraintdef(oid) from pg_constraint where conname = 'uq_fact_inbound_shipment_fact_upsert_key'"))
    if "tenant_id" in constraint:
        pytest.skip("this database already carries 0051")
    ta, tb, jb, delivery, fact_a = _load_same_line_for_both_tenants(db, tenant, job, evidence)
    assert float(fact_a.quantity) == 40
    with pytest.raises(Exception):  # the global constraint refuses tenant B's identical key
        with db.begin_nested():
            facts_mod.upsert_inbound_shipment_facts_for_job(db, int(jb.id))
    assert [(r.id, float(r.quantity)) for r in _facts(db, ta, delivery)] == [(fact_a.id, 40.0)], "tenant A's fact must survive"


def test_p8_both_tenants_hold_their_own_fact_after_0051(world):
    db, tenant, job, evidence, _ = world
    ops = Operations.context(MigrationContext.configure(db.connection()))
    with ops:
        _migration().upgrade()
    ta, tb, jb, delivery, fact_a = _load_same_line_for_both_tenants(db, tenant, job, evidence)
    key_a = fact_a.fact_upsert_key
    facts_mod.upsert_inbound_shipment_facts_for_job(db, int(jb.id))
    assert [(r.id, float(r.quantity)) for r in _facts(db, ta, delivery)] == [(fact_a.id, 40.0)]
    b = _facts(db, tb, delivery)
    assert len(b) == 1 and float(b[0].quantity) == 3
    assert db.scalar(select(FactInboundShipment.fact_upsert_key).where(FactInboundShipment.id == b[0].id)) == key_a
    # A reload by tenant A replaces only A's own fact.
    facts_mod.upsert_inbound_shipment_facts_for_job(db, int(db.scalar(select(ImportJob.id).where(ImportJob.tenant_id == ta))))
    assert len(_facts(db, ta, delivery)) == 1 and len(_facts(db, tb, delivery)) == 1


def test_0051_downgrade_refuses_when_two_tenants_hold_one_key(world):
    db, tenant, job, evidence, _ = world
    ops = Operations.context(MigrationContext.configure(db.connection()))
    with ops:
        _migration().upgrade()
    ta, tb, jb, delivery, fact_a = _load_same_line_for_both_tenants(db, tenant, job, evidence)
    facts_mod.upsert_inbound_shipment_facts_for_job(db, int(jb.id))
    with pytest.raises(Exception):
        with db.begin_nested():
            with ops:
                _migration().downgrade()
    assert db.scalar(select(func.count()).where(FactInboundShipment.fact_upsert_key == fact_a.fact_upsert_key)) == 2
