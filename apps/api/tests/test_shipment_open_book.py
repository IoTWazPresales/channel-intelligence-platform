"""Open-book close and confirmed-ship rules. Each database test rolls back."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.platform_audit import PlatformAuditEvent
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_change_events import derive_change_events
from app.services.imports.shipment_evidence_line_identity import stable_line_identity_key_from_fields
from app.services.imports.shipment_invoice_graduation import (
    is_blank_invoice_shipped_obs,
    process_invoice_graduation_after_job,
)
from app.services.imports.shipment_open_book import (
    close_open_book_for_job,
    line_state_for_shipped_sheet,
    write_shipment_facts_and_close_book,
)
from app.services.imports.shipment_report_date import report_date_from_file_name

UNSHIP = "acza_workbook_unship"
SHIPPED = "acza_workbook_shipped"


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        current = session.execute(text("SELECT current_database()")).scalar()
        assert current != "cip"
        if session.get(Tenant, "default") is None:
            session.add(Tenant(id="default", name="Default"))
            session.flush()
        yield session
    finally:
        session.rollback()
        session.close()


def test_report_date_is_the_single_file_token():
    assert report_date_from_file_name("ACZA Shipped Unshipped 20260911.xlsx") == date(2026, 9, 11)
    assert report_date_from_file_name("ACZA Shipped Unshipped 20260818_P2.xlsx") == date(2026, 8, 18)
    assert report_date_from_file_name("shipped 2020-2023.xlsx") is None
    assert report_date_from_file_name("ACZA 20260901 and 20260911.xlsx") is None
    assert report_date_from_file_name(None) is None


def test_shipped_sheet_without_a_confirm_on_or_before_the_report_stays_open():
    report = date(2026, 9, 11)
    assert (
        line_state_for_shipped_sheet("shipped", ship_confirm_date=None, report_date=report)
        == "open_order"
    )
    assert (
        line_state_for_shipped_sheet("shipped", ship_confirm_date=date(2026, 9, 12), report_date=report)
        == "open_order"
    )
    assert (
        line_state_for_shipped_sheet("shipped", ship_confirm_date=date(2026, 9, 11), report_date=report)
        == "shipped"
    )
    assert (
        line_state_for_shipped_sheet("shipped", ship_confirm_date=date(2026, 9, 1), report_date=report)
        == "shipped"
    )
    assert (
        line_state_for_shipped_sheet("shipped", ship_confirm_date=date(2026, 9, 1), report_date=None)
        == "shipped"
    )
    assert (
        line_state_for_shipped_sheet("open_order", ship_confirm_date=None, report_date=report)
        == "open_order"
    )


def _job(db, file_name: str, *, status: str = "completed") -> ImportJob:
    token = uuid.uuid4().hex[:12]
    template = ImportTemplate(
        slug=f"ob-{token}",
        display_name="open book",
        pipeline_handler="inbound_shipments",
    )
    db.add(template)
    db.flush()
    source = SourceDefinition(
        import_template_id=int(template.id),
        code=f"ob-{token}",
        name="open book",
        source_kind="file",
    )
    db.add(source)
    db.flush()
    job = ImportJob(
        tenant_id="default",
        source_id=int(source.id),
        template_slug="inbound_shipments",
        status=status,
        stage="loaded" if status == "completed" else "validated",
        file_name=file_name,
        completed_at=datetime(2026, 9, 20, tzinfo=timezone.utc) if status == "completed" else None,
    )
    db.add(job)
    db.flush()
    return job


def _line(
    db,
    job: ImportJob,
    *,
    report_type: str,
    line_state: str,
    source_key: str,
    order_no: str,
    item_code: str,
    quantity: float,
    sheet: str,
    ship_confirm_date: date | None = None,
    est_pod_date: date | None = None,
    delivery_no: str | None = None,
) -> ShipmentEvidenceLine:
    row = ShipmentEvidenceLine(
        import_job_id=int(job.id),
        source_sheet=sheet,
        source_row_number=1,
        report_type=report_type,
        line_state=line_state,
        source_key=source_key,
        raw_source_row={},
        order_no=order_no,
        order_line="1",
        delivery_no=delivery_no,
        item_code=item_code,
        quantity=quantity,
        ship_confirm_date=ship_confirm_date,
        est_pod_date=est_pod_date,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    db.add(row)
    db.flush()
    return row


def _fact(
    db,
    job: ImportJob,
    *,
    report_type: str,
    line_state: str,
    source_key: str,
    order_no: str,
    item_code: str,
    quantity: float,
    ship_confirm_date: date | None = None,
    est_pod_date: date | None = None,
) -> FactInboundShipment:
    row = FactInboundShipment(
        tenant_id="default",
        import_job_id=int(job.id),
        source_key=source_key,
        fact_upsert_key=source_key,
        source_row_number=1,
        report_type=report_type,
        line_state=line_state,
        raw_source_row={},
        order_no=order_no,
        order_line="1",
        item_code=item_code,
        quantity=quantity,
        ship_confirm_date=ship_confirm_date,
        est_pod_date=est_pod_date,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
        status="scheduled",
    )
    db.add(row)
    db.flush()
    return row


def _open_qty(db, order_no: str, item_code: str) -> float:
    value = db.scalar(
        select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
            FactInboundShipment.order_no == order_no,
            FactInboundShipment.item_code == item_code,
            func.lower(FactInboundShipment.line_state) == "open_order",
        )
    )
    return float(value or 0)


def test_line_absent_from_the_next_report_closes(db):
    earlier = _job(db, "ACZA Shipped Unshipped 20260901.xlsx")
    gone = _fact(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"unship-{uuid.uuid4().hex}",
        order_no="SO-GONE",
        item_code="ITEM-GONE",
        quantity=4,
    )
    _line(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=gone.source_key,
        order_no="SO-GONE",
        item_code="ITEM-GONE",
        quantity=4,
        sheet="Unship",
    )
    newer = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    _line(
        db,
        newer,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"stay-{uuid.uuid4().hex}",
        order_no="SO-STAY",
        item_code="ITEM-STAY",
        quantity=1,
        sheet="Unship",
    )

    closed = close_open_book_for_job(db, newer)
    db.refresh(gone)
    assert gone.line_state == "closed_disappeared"
    assert any(int(row["id"]) == int(gone.id) for row in closed)
    obs = db.scalar(
        select(ShipmentEvidenceObservation).where(
            ShipmentEvidenceObservation.source_key == f"closed:{int(gone.id)}"
        )
    )
    assert obs is not None
    assert obs.import_job_id == int(newer.id)
    assert obs.line_state == "closed_disappeared"
    assert obs.raw_source_row["open_book_report_date"] == "2026-09-11"
    assert obs.raw_source_row["open_book_closed_by_job_id"] == int(newer.id)
    audit = db.scalar(
        select(PlatformAuditEvent).where(
            PlatformAuditEvent.action == "open_book_close",
            PlatformAuditEvent.target_id == str(newer.id),
        )
    )
    assert audit is not None
    assert int(gone.id) in {int(row["fact_id"]) for row in audit.detail_json["facts"]}


def test_older_report_loaded_late_closes_and_reopens_nothing(db):
    earlier = _job(db, "ACZA Shipped Unshipped 20260901.xlsx")
    key = f"unship-{uuid.uuid4().hex}"
    fact = _fact(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=key,
        order_no="SO-OLD",
        item_code="ITEM-OLD",
        quantity=3,
    )
    _line(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=key,
        order_no="SO-OLD",
        item_code="ITEM-OLD",
        quantity=3,
        sheet="Unship",
    )
    newer = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    _line(
        db,
        newer,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"stay-{uuid.uuid4().hex}",
        order_no="SO-KEEP",
        item_code="ITEM-KEEP",
        quantity=1,
        sheet="Unship",
    )
    close_open_book_for_job(db, newer)
    db.refresh(fact)
    assert fact.line_state == "closed_disappeared"

    late = _job(db, "ACZA Shipped Unshipped 20260801.xlsx", status="validated")
    _line(
        db,
        late,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=key,
        order_no="SO-OLD",
        item_code="ITEM-OLD",
        quantity=3,
        sheet="Unship",
    )
    result = write_shipment_facts_and_close_book(db, late)
    assert result["skipped_reason"] == "older_report_date"
    assert result["fact_rows"] == 0
    assert result["closed"] == 0
    db.refresh(fact)
    assert fact.line_state == "closed_disappeared"
    assert fact.import_job_id == int(earlier.id)
    late_facts = db.scalar(
        select(func.count()).select_from(FactInboundShipment).where(
            FactInboundShipment.import_job_id == int(late.id)
        )
    )
    assert int(late_facts or 0) == 0


def test_undated_shipped_row_loads_open_and_the_unship_fact_closes_once(db):
    earlier = _job(db, "ACZA Shipped Unshipped 20260901.xlsx")
    old_key = f"unship-{uuid.uuid4().hex}"
    old = _fact(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=old_key,
        order_no="SO-UNDATED",
        item_code="ITEM-UNDATED",
        quantity=10,
    )
    _line(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=old_key,
        order_no="SO-UNDATED",
        item_code="ITEM-UNDATED",
        quantity=10,
        sheet="Unship",
    )
    newer = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    _line(
        db,
        newer,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"other-{uuid.uuid4().hex}",
        order_no="SO-OTHER",
        item_code="ITEM-OTHER",
        quantity=1,
        sheet="Unship",
    )
    stored = line_state_for_shipped_sheet("shipped", ship_confirm_date=None, report_date=date(2026, 9, 11))
    shipped_key = f"shipped-open-{uuid.uuid4().hex}"
    _line(
        db,
        newer,
        report_type=SHIPPED,
        line_state=stored,
        source_key=shipped_key,
        order_no="SO-UNDATED",
        item_code="ITEM-UNDATED",
        quantity=10,
        sheet="Shipped",
    )
    # The importer stores this line_state on the evidence row. The fact uses that
    # row's own source_key, so it does not overwrite the earlier Unship fact.
    _fact(
        db,
        newer,
        report_type=SHIPPED,
        line_state=stored,
        source_key=shipped_key,
        order_no="SO-UNDATED",
        item_code="ITEM-UNDATED",
        quantity=10,
    )
    close_open_book_for_job(db, newer)
    db.refresh(old)
    assert stored == "open_order"
    assert old.line_state == "closed_disappeared"
    assert _open_qty(db, "SO-UNDATED", "ITEM-UNDATED") == 10
    current = db.scalars(
        select(FactInboundShipment).where(
            FactInboundShipment.order_no == "SO-UNDATED",
            FactInboundShipment.item_code == "ITEM-UNDATED",
            func.lower(FactInboundShipment.line_state) == "open_order",
        )
    ).all()
    assert len(current) == 1
    assert int(current[0].import_job_id) == int(newer.id)
    assert current[0].report_type == SHIPPED


def test_next_report_with_a_confirm_date_moves_the_line_to_shipped(db):
    report = date(2026, 9, 18)
    held = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    open_key = f"shipped-open-{uuid.uuid4().hex}"
    held_fact = _fact(
        db,
        held,
        report_type=SHIPPED,
        line_state="open_order",
        source_key=open_key,
        order_no="SO-CONFIRM",
        item_code="ITEM-CONFIRM",
        quantity=10,
    )
    _line(
        db,
        held,
        report_type=SHIPPED,
        line_state="open_order",
        source_key=open_key,
        order_no="SO-CONFIRM",
        item_code="ITEM-CONFIRM",
        quantity=10,
        sheet="Shipped",
    )
    nxt = _job(db, "ACZA Shipped Unshipped 20260918.xlsx")
    stored = line_state_for_shipped_sheet(
        "shipped", ship_confirm_date=date(2026, 9, 15), report_date=report
    )
    assert stored == "shipped"
    confirmed_key = f"shipped-{uuid.uuid4().hex}"
    _line(
        db,
        nxt,
        report_type=SHIPPED,
        line_state=stored,
        source_key=confirmed_key,
        order_no="SO-CONFIRM",
        item_code="ITEM-CONFIRM",
        quantity=10,
        sheet="Shipped",
        ship_confirm_date=date(2026, 9, 15),
        delivery_no="D-CONFIRM",
    )
    _fact(
        db,
        nxt,
        report_type=SHIPPED,
        line_state=stored,
        source_key=confirmed_key,
        order_no="SO-CONFIRM",
        item_code="ITEM-CONFIRM",
        quantity=10,
        ship_confirm_date=date(2026, 9, 15),
    )
    close_open_book_for_job(db, nxt)
    db.refresh(held_fact)
    assert held_fact.line_state == "closed_shipped"
    assert _open_qty(db, "SO-CONFIRM", "ITEM-CONFIRM") == 0
    shipped_qty = db.scalar(
        select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
            FactInboundShipment.order_no == "SO-CONFIRM",
            FactInboundShipment.item_code == "ITEM-CONFIRM",
            func.lower(FactInboundShipment.line_state) == "shipped",
        )
    )
    assert float(shipped_qty or 0) == 10


def _slip_observations(db, job: ImportJob, *, key: str, order_no: str, item_code: str) -> tuple[int, int]:
    first = ShipmentEvidenceObservation(
        line_identity_key=key,
        import_job_id=int(job.id),
        source_key=f"obs-{uuid.uuid4().hex}",
        source_row_hash=hashlib.sha256(f"a-{key}".encode()).hexdigest()[:40],
        valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        source_row_number=1,
        report_type=UNSHIP,
        line_state="open_order",
        raw_source_row={},
        order_no=order_no,
        order_line="1",
        item_code=item_code,
        quantity=6,
        est_pod_date=date(2026, 10, 11),
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    second = ShipmentEvidenceObservation(
        line_identity_key=key,
        import_job_id=int(job.id),
        source_key=f"obs-{uuid.uuid4().hex}",
        source_row_hash=hashlib.sha256(f"b-{key}".encode()).hexdigest()[:40],
        valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
        observed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        source_row_number=1,
        report_type=UNSHIP,
        line_state="open_order",
        raw_source_row={},
        order_no=order_no,
        order_line="1",
        item_code=item_code,
        quantity=6,
        est_pod_date=date(2026, 10, 18),
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    db.add(first)
    db.add(second)
    db.flush()
    return int(first.id), int(second.id)


def test_shipped_and_vanished_lines_close_without_changing_date_slips(db):
    earlier = _job(db, "ACZA Shipped Unshipped 20260901.xlsx")
    ship_key = stable_line_identity_key_from_fields(
        line_state="open_order", order_no="SO-SHIP", order_line="1", item_code="ITEM-SHIP"
    )
    vanish_key = stable_line_identity_key_from_fields(
        line_state="open_order", order_no="SO-VANISH", order_line="1", item_code="ITEM-VANISH"
    )
    ship_prior, ship_later = _slip_observations(
        db, earlier, key=ship_key, order_no="SO-SHIP", item_code="ITEM-SHIP"
    )
    vanish_prior, vanish_later = _slip_observations(
        db, earlier, key=vanish_key, order_no="SO-VANISH", item_code="ITEM-VANISH"
    )
    ship_fact = _fact(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"unship-ship-{uuid.uuid4().hex}",
        order_no="SO-SHIP",
        item_code="ITEM-SHIP",
        quantity=6,
        est_pod_date=date(2026, 10, 18),
    )
    vanish_fact = _fact(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"unship-vanish-{uuid.uuid4().hex}",
        order_no="SO-VANISH",
        item_code="ITEM-VANISH",
        quantity=6,
        est_pod_date=date(2026, 10, 18),
    )
    _line(
        db,
        earlier,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=ship_fact.source_key,
        order_no="SO-SHIP",
        item_code="ITEM-SHIP",
        quantity=6,
        sheet="Unship",
    )
    twin = _fact(
        db,
        earlier,
        report_type=SHIPPED,
        line_state="shipped",
        source_key=f"shipped-twin-{uuid.uuid4().hex}",
        order_no="SO-SHIP",
        item_code="ITEM-SHIP",
        quantity=6,
        ship_confirm_date=date(2026, 9, 10),
    )
    newer = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    _line(
        db,
        newer,
        report_type=UNSHIP,
        line_state="open_order",
        source_key=f"stay-{uuid.uuid4().hex}",
        order_no="SO-STAY",
        item_code="ITEM-STAY",
        quantity=1,
        sheet="Unship",
    )
    close_open_book_for_job(db, newer)
    db.refresh(ship_fact)
    db.refresh(vanish_fact)
    db.refresh(twin)
    assert ship_fact.line_state == "closed_shipped"
    assert vanish_fact.line_state == "closed_disappeared"
    assert twin.line_state == "shipped"

    for key, prior_id, later_id, kind in (
        (ship_key, ship_prior, ship_later, "closed_shipped"),
        (vanish_key, vanish_prior, vanish_later, "closed_disappeared"),
    ):
        events = derive_change_events(db, line_identity_key=key, limit=100)
        slips = [event for event in events if event.event_type == "date_slip"]
        assert len(slips) == 1
        assert slips[0].details["days_moved"] == 7
        assert slips[0].prior_observation_id == prior_id
        assert slips[0].observation_id == later_id
        closes = [event for event in events if event.event_type == kind]
        assert len(closes) == 1
        assert closes[0].details["report_date"] == "2026-09-11"


def test_invoice_graduation_leaves_an_open_observation_in_place(db):
    earlier = _job(db, "ACZA Shipped Unshipped 20260901.xlsx")
    newer = _job(db, "ACZA Shipped Unshipped 20260911.xlsx")
    open_obs = ShipmentEvidenceObservation(
        line_identity_key="order:ACZA|SO-GRAD|1|ITEM-GRAD",
        import_job_id=int(earlier.id),
        source_key=f"open-{uuid.uuid4().hex}",
        source_row_hash=hashlib.sha256(b"open-grad").hexdigest()[:40],
        valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        source_row_number=1,
        report_type=UNSHIP,
        line_state="open_order",
        raw_source_row={},
        operating_unit="ACZA",
        order_no="SO-GRAD",
        order_line="1",
        item_code="ITEM-GRAD",
        quantity=2,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    shipped_obs = ShipmentEvidenceObservation(
        line_identity_key="ship:ACZA|D9|ITEM-GRAD|99|1",
        import_job_id=int(newer.id),
        source_key=f"ship-{uuid.uuid4().hex}",
        source_row_hash=hashlib.sha256(b"ship-grad").hexdigest()[:40],
        valid_from=datetime(2026, 9, 11, tzinfo=timezone.utc),
        observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        source_row_number=1,
        report_type=SHIPPED,
        line_state="shipped",
        raw_source_row={},
        operating_unit="ACZA",
        order_no="SO-GRAD",
        order_line="1",
        delivery_no="D9",
        invoice_line="1",
        item_code="ITEM-GRAD",
        quantity=2,
        ship_confirm_date=date(2026, 9, 10),
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )
    db.add(open_obs)
    db.add(shipped_obs)
    db.flush()
    assert is_blank_invoice_shipped_obs(open_obs) is False
    process_invoice_graduation_after_job(db, newer)
    db.refresh(open_obs)
    assert open_obs.superseded_by_id is None
    assert open_obs.line_state == "open_order"
