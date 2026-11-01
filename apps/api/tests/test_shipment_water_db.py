"""On the water: voyage columns through evidence, observation and fact, and the manual port conditions.

Needs migration 20261101_0049 on the test database. Every test rolls back.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.models.shipment_water import WATER_FIELDS, PortCondition
from app.services.imports.shipment_evidence_observations import _line_to_observation_values
from app.services.imports.shipment_inbound_facts import _upsert_single_evidence_row

UNSHIP = "acza_workbook_unship"


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        assert session.execute(text("SELECT current_database()")).scalar() != "cip"
        if session.get(Tenant, "default") is None:
            session.add(Tenant(id="default", name="Default"))
            session.flush()
        yield session
    finally:
        session.rollback()
        session.close()


def _job(db) -> ImportJob:
    token = uuid.uuid4().hex[:12]
    template = ImportTemplate(slug=f"otw-{token}", display_name="on the water", pipeline_handler="inbound_shipments")
    db.add(template)
    db.flush()
    source = SourceDefinition(import_template_id=int(template.id), code=f"otw-{token}", name="on the water", source_kind="file")
    db.add(source)
    db.flush()
    job = ImportJob(
        tenant_id="default", source_id=int(source.id), template_slug="inbound_shipments", status="completed", stage="loaded",
        file_name="ACZA Shipped Unshipped 20261027.xlsx", completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    db.add(job)
    db.flush()
    return job


def _line(db, job: ImportJob, **water) -> ShipmentEvidenceLine:
    base = dict(
        import_job_id=int(job.id), source_sheet="Unship", source_row_number=1, report_type=UNSHIP, line_state="open_order",
        source_key=f"{UNSHIP}:{uuid.uuid4().hex}", raw_source_row={}, order_no=f"SO{uuid.uuid4().hex[:6]}", order_line="1",
        item_code="ITEM-1", quantity=10, product_resolution_status="unresolved", distributor_resolution_status="unresolved",
    )
    row = ShipmentEvidenceLine(**{**base, **water})
    db.add(row)
    db.flush()
    return row


VOYAGE = dict(
    on_board_date=date(2026, 9, 2), port_eta_date=date(2026, 10, 20), port_ata_date=None,
    shipping_method="KGILsha-WWP-Sea--", forwarder_code="KGIL", origin_hub="sha", ship_way="SEA", deliver_port="ZADUR",
)


def test_the_voyage_columns_travel_from_evidence_to_observation_and_fact(db):
    job = _job(db)
    line = _line(db, job, **VOYAGE)

    obs_values = _line_to_observation_values(
        line, valid_from=datetime(2026, 10, 28, tzinfo=timezone.utc), observed_at=datetime(2026, 10, 28, tzinfo=timezone.utc)
    )
    for name in WATER_FIELDS:
        assert obs_values[name] == getattr(line, name), name
    db.add(ShipmentEvidenceObservation(**obs_values))
    db.flush()

    tbl = FactInboundShipment.__table__
    _upsert_single_evidence_row(db, tbl, line, tenant_id="default")
    fact = db.scalar(select(FactInboundShipment).where(FactInboundShipment.shipment_evidence_line_id == line.id))
    assert fact is not None
    for name in WATER_FIELDS:
        assert getattr(fact, name) == getattr(line, name), name
    assert fact.eta_date is None  # the coalesced delivery date is a different field: port ETA never lands in it

    # The next report moves the vessel: the fact follows the line, and there is still one fact.
    line.port_eta_date = date(2026, 11, 3)
    line.port_ata_date = date(2026, 11, 2)
    db.flush()
    _upsert_single_evidence_row(db, tbl, line, tenant_id="default")
    db.expire_all()
    facts = db.scalars(select(FactInboundShipment).where(FactInboundShipment.shipment_evidence_line_id == line.id)).all()
    assert len(facts) == 1
    assert (facts[0].port_eta_date, facts[0].port_ata_date) == (date(2026, 11, 3), date(2026, 11, 2))


def test_a_line_without_voyage_headers_leaves_the_columns_empty(db):
    line = _line(db, _job(db))
    assert all(getattr(line, name) is None for name in WATER_FIELDS)
    _upsert_single_evidence_row(db, FactInboundShipment.__table__, line, tenant_id="default")
    fact = db.scalar(select(FactInboundShipment).where(FactInboundShipment.shipment_evidence_line_id == line.id))
    assert all(getattr(fact, name) is None for name in WATER_FIELDS)


def test_the_newest_port_condition_row_is_current_and_rows_cannot_be_changed(db):
    port = f"ZT{uuid.uuid4().hex[:3].upper()}"
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            PortCondition(tenant_id="default", port_code=port, delay_days=15, note="congestion", entered_by="Warren", entered_at=now - timedelta(days=2)),
            PortCondition(tenant_id="default", port_code=port, delay_days=9, note="easing", entered_by="Warren", entered_at=now),
            PortCondition(tenant_id="other", port_code=port, delay_days=30, entered_by="Someone", entered_at=now),
        ]
    )
    db.flush()
    current = db.scalar(
        select(PortCondition)
        .where(PortCondition.tenant_id == "default", PortCondition.port_code == port)
        .order_by(PortCondition.entered_at.desc(), PortCondition.id.desc())
        .limit(1)
    )
    assert float(current.delay_days) == 9 and current.note == "easing"

    for statement in ("UPDATE port_condition SET delay_days = 1", "DELETE FROM port_condition"):
        try:
            with db.begin_nested():
                changed = db.execute(text(statement)).rowcount
            assert changed == 0, f"{statement} changed {changed} rows"
        except DBAPIError:
            pass  # refused outright: the role has no UPDATE or DELETE privilege
    assert db.scalar(text("SELECT count(*) FROM port_condition WHERE port_code = :p"), {"p": port}) == 3
