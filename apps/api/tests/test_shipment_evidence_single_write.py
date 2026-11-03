"""D4: the loader writes a shipment row's payload once, on the observation. The line keeps job scope and steward state.

Each database test rolls back. Fictional tenants only.
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_evidence_observations import append_observations_for_job_lines
from app.services.imports.shipment_evidence_rows import (
    EVIDENCE_LINES_WITH_PAYLOAD_SQL,
    PAYLOAD_COLUMNS,
    EvidenceRow,
    MissingEvidencePayload,
    load_evidence_rows,
)
from app.services.imports.shipment_inbound_facts import upsert_inbound_shipment_facts_for_job
from tests.shipment_evidence_fixtures import add_evidence_line

_HEADERS = [
    "Bill To",
    "PO",
    "Model Name",
    "Item",
    "QTY",
    "Unit Price",
    "Schedule Ship Date",
    "CRAD",
    "Shipway",
    "Delivery",
    "Order Number",
]


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        assert session.execute(text("SELECT current_database()")).scalar() != "cip"
        if session.get(Tenant, "default") is None:
            session.add(Tenant(id="default", name="Default"))
            session.flush()
        session.info["tenant"] = "default"
        yield session
    finally:
        session.rollback()
        session.close()


def _workbook() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Unship"
    ws.append(_HEADERS)
    ws.append(
        [
            "ACME PARTS",
            "PO-FICTION-1",
            "Model North",
            "ITEM-NORTH",
            4,
            12.5,
            date(2026, 10, 1),
            date(2026, 10, 15),
            "SEA",
            None,
            "SO-NORTH",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import_job(db, monkeypatch, *, file_name: str = "ACZA Shipped Unshipped 20990115.xlsx"):
    import pandas as pd

    from app.services.imports.shipment_evidence_import import process_shipment_evidence_import
    from app.services.imports.shipment_field_mapping import build_initial_shipment_field_mapping

    token = uuid.uuid4().hex[:12]
    template = ImportTemplate(slug=f"d4-{token}", display_name="d4", pipeline_handler="inbound_shipments")
    db.add(template)
    db.flush()
    source = SourceDefinition(
        import_template_id=int(template.id), code=f"d4-{token}", name="d4", source_kind="file"
    )
    db.add(source)
    db.flush()
    job = ImportJob(
        tenant_id="default",
        source_id=int(source.id),
        template_slug="inbound_shipments",
        status="completed",
        stage="loaded",
        file_name=file_name,
        completed_at=datetime(2099, 1, 16, tzinfo=timezone.utc),
    )
    db.add(job)
    db.flush()
    blob = _workbook()
    mapping = build_initial_shipment_field_mapping(_HEADERS, None)
    job.field_mapping = mapping
    db.add(RawFileMetadata(job_id=int(job.id), storage_key=f"imports/test/{token}.xlsx", byte_size=len(blob)))
    db.flush()

    class _Store:
        def read(self, _key: str) -> bytes:
            return blob

    monkeypatch.setattr(
        "app.services.imports.shipment_evidence_import.get_storage_backend",
        lambda: _Store(),
    )
    blocking = process_shipment_evidence_import(db, job, pd.DataFrame(), mapping)
    if blocking:
        errors = db.scalars(select(ImportRowResult).where(ImportRowResult.job_id == int(job.id))).all()
        pytest.fail("; ".join(f"{row.code}: {row.message}" for row in errors))
    return job


def _fact_signature(db, job_id: int) -> list[tuple]:
    rows = db.scalars(
        select(FactInboundShipment)
        .where(FactInboundShipment.import_job_id == int(job_id))
        .order_by(FactInboundShipment.source_key)
    ).all()
    out = []
    for fact in rows:
        out.append(
            (
                fact.source_key,
                fact.fact_upsert_key,
                fact.report_type,
                fact.line_state,
                fact.order_no,
                fact.customer_po,
                fact.item_code,
                fact.sales_model_name,
                fact.bill_to_raw,
                float(fact.quantity or 0),
                float(fact.unit_price or 0),
                fact.ship_confirm_date,
                fact.schedule_ship_date,
                str(fact.tenant_id),
            )
        )
    return out


def test_validate_writes_payload_only_on_the_observation(db, monkeypatch):
    job = _import_job(db, monkeypatch)
    lines = db.scalars(select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == int(job.id))).all()
    assert len(lines) == 1
    line = lines[0]
    for col in ("report_type", "line_state", "raw_source_row", "item_code", "customer_po", "quantity", "bill_to_raw"):
        assert getattr(line, col) is None, col
    obs = db.scalar(
        select(ShipmentEvidenceObservation).where(ShipmentEvidenceObservation.evidence_line_id == line.id)
    )
    assert obs is not None
    assert obs.report_type == "acza_workbook_unship"
    assert obs.line_state == "open_order"
    assert obs.item_code == "ITEM-NORTH"
    assert obs.customer_po == "PO-FICTION-1"
    assert float(obs.quantity) == 4
    assert obs.bill_to_raw == "ACME PARTS"
    assert line.crad_date == date(2026, 10, 15)
    nullable = db.execute(
        text(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'shipment_evidence_line' AND column_name = 'report_type'
            """
        )
    ).scalar_one()
    assert nullable == "YES"


def test_apply_twice_does_not_change_facts(db, monkeypatch):
    job = _import_job(db, monkeypatch)
    first = upsert_inbound_shipment_facts_for_job(db, int(job.id))
    signature = _fact_signature(db, int(job.id))
    assert first == 1 and signature == [
        (
            "acza_workbook_unship:unship|SO-NORTH|ITEM-NORTH",
            "acza_workbook_unship:unship|SO-NORTH|ITEM-NORTH",
            "acza_workbook_unship",
            "open_order",
            "SO-NORTH",
            "PO-FICTION-1",
            "ITEM-NORTH",
            "Model North",
            "ACME PARTS",
            4.0,
            12.5,
            None,
            date(2026, 10, 1),
            "default",
        )
    ]
    second = upsert_inbound_shipment_facts_for_job(db, int(job.id))
    assert second == 1
    assert _fact_signature(db, int(job.id)) == signature
    assert db.scalar(
        select(ShipmentEvidenceObservation.id).where(ShipmentEvidenceObservation.import_job_id == int(job.id))
    ) is not None


def _bare_job(db, name: str) -> ImportJob:
    token = uuid.uuid4().hex[:12]
    template = ImportTemplate(slug=f"d4b-{token}", display_name="d4", pipeline_handler="inbound_shipments")
    db.add(template)
    db.flush()
    source = SourceDefinition(
        import_template_id=int(template.id), code=f"d4b-{token}", name="d4", source_kind="file"
    )
    db.add(source)
    db.flush()
    job = ImportJob(
        tenant_id="default",
        source_id=int(source.id),
        template_slug="inbound_shipments",
        status="completed",
        stage="loaded",
        file_name=name,
        completed_at=datetime(2099, 1, 16, tzinfo=timezone.utc),
    )
    db.add(job)
    db.flush()
    return job


def test_same_hash_refreshes_customer_po_and_voyage_without_a_second_observation(db):
    job = _bare_job(db, "d4-refresh.xlsx")
    line = add_evidence_line(
        db,
        import_job_id=int(job.id),
        source_key="d4-refresh",
        source_row_number=1,
        report_type="acza_workbook_unship",
        line_state="open_order",
        raw_source_row={"note": "first"},
        customer_po="PO-OLD",
        item_code="ITEM-NORTH",
        quantity=4,
        order_no="SO-NORTH",
        order_line="1",
        port_eta_date=date(2099, 2, 1),
    )
    row = load_evidence_rows(db, where=(ShipmentEvidenceLine.id == int(line.id),))[0]
    payload = {col: getattr(row, col) for col in PAYLOAD_COLUMNS}
    payload["customer_po"] = "PO-NEW"
    payload["port_eta_date"] = date(2099, 3, 1)
    payload["raw_source_row"] = {"note": "second"}
    append_observations_for_job_lines(db, job, [EvidenceRow(line, payload)])
    observations = db.scalars(
        select(ShipmentEvidenceObservation).where(ShipmentEvidenceObservation.evidence_line_id == int(line.id))
    ).all()
    assert len(observations) == 1
    assert observations[0].customer_po == "PO-NEW"
    assert observations[0].port_eta_date == date(2099, 3, 1)
    assert observations[0].raw_source_row == {"note": "second"}
    again = load_evidence_rows(db, where=(ShipmentEvidenceLine.id == int(line.id),))[0]
    assert again.customer_po == "PO-NEW"
    assert again.port_eta_date == date(2099, 3, 1)


def test_apply_refuses_a_line_with_no_observation(db):
    job = _bare_job(db, "d4-empty.xlsx")
    add_evidence_line(
        db,
        import_job_id=int(job.id),
        source_key="d4-empty",
        observe=False,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    with pytest.raises(MissingEvidencePayload):
        upsert_inbound_shipment_facts_for_job(db, int(job.id))


def test_payload_relation_runs_on_postgres(db):
    line = add_evidence_line(
        db,
        import_job_id=_import_anchor(db),
        source_key=f"d4-sql-{uuid.uuid4().hex[:8]}",
        report_type="acza_workbook_unship",
        line_state="open_order",
        item_code="ITEM-SQL",
        quantity=2,
        customer_po="PO-SQL",
        raw_source_row={},
    )
    found = db.execute(
        text(
            f"""
            SELECT l.item_code, l.customer_po, l.quantity, l.report_type
            FROM {EVIDENCE_LINES_WITH_PAYLOAD_SQL} l
            WHERE l.id = :id
            """
        ),
        {"id": int(line.id)},
    ).one()
    assert found.item_code == "ITEM-SQL"
    assert found.customer_po == "PO-SQL"
    assert float(found.quantity) == 2
    assert found.report_type == "acza_workbook_unship"
    # The line table itself was not given those values.
    stored = db.get(ShipmentEvidenceLine, int(line.id))
    assert stored.item_code is None and stored.customer_po is None


def _import_anchor(db) -> int:
    return int(_bare_job(db, "d4-anchor.xlsx").id)
