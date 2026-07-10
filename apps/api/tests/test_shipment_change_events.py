"""Tests for shipment change-event derivation (Plan D phase 4)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_change_events import derive_change_events, order_grain_key


def _obs(
    *,
    id: int,
    key: str,
    job_id: int,
    line_state: str,
    valid_from: datetime,
    qty: float = 10,
    est_pod: date | None = None,
    pod: date | None = None,
    ou: str = "ACZA",
    order_no: str = "O1",
    order_line: str = "1",
    item: str = "ITEM1",
    delivery: str | None = None,
) -> ShipmentEvidenceObservation:
    return ShipmentEvidenceObservation(
        id=id,
        line_identity_key=key,
        import_job_id=job_id,
        source_key=f"sk-{id}",
        source_row_hash=f"hash{id:040d}",
        valid_from=valid_from,
        observed_at=valid_from,
        source_row_number=1,
        report_type="acza_workbook_shipped" if line_state == "shipped" else "acza_workbook_unship",
        line_state=line_state,
        raw_source_row={},
        operating_unit=ou,
        order_no=order_no,
        order_line=order_line,
        item_code=item,
        delivery_no=delivery,
        quantity=qty,
        est_pod_date=est_pod,
        pod_date=pod,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )


def test_order_grain_key_normalizes():
    assert order_grain_key(operating_unit="ACZA", order_no="123", order_line="1", item_code="X") == "order:ACZA|123|1|X"


def test_date_slip_and_qty_change_from_chain():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    key = "ship:ACZA|D1|ITEM1|PO1|1"
    prior = _obs(id=1, key=key, job_id=10, line_state="shipped", valid_from=t0, qty=5, est_pod=date(2026, 3, 1))
    curr = _obs(
        id=2,
        key=key,
        job_id=20,
        line_state="shipped",
        valid_from=t1,
        qty=8,
        est_pod=date(2026, 3, 15),
        delivery="D1",
    )

    class _FakeDB:
        def scalars(self, stmt):
            return _FakeResult([prior, curr])

    events = derive_change_events(_FakeDB(), line_identity_key=key, limit=100)
    types = {e.event_type for e in events}
    assert "date_slip" in types
    assert "qty_change" in types
    slip = next(e for e in events if e.event_type == "date_slip")
    assert slip.details["days_moved"] == 14


def test_pod_reversal_does_not_emit_ungraduate():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    key = "ship:ACZA|D1|ITEM1|PO1|1"
    prior = _obs(id=1, key=key, job_id=10, line_state="shipped", valid_from=t0, pod=date(2026, 1, 15), delivery="D1")
    curr = _obs(id=2, key=key, job_id=20, line_state="shipped", valid_from=t1, pod=None, delivery="D1")

    class _FakeDB:
        def scalars(self, stmt):
            return _FakeResult([prior, curr])

    events = derive_change_events(_FakeDB(), line_identity_key=key, limit=100)
    rev = [e for e in events if e.event_type == "pod_reversal"]
    assert len(rev) == 1
    assert rev[0].details.get("steward_flag") is True
    assert not any(e.event_type == "graduated" for e in events)


def test_graduated_open_to_shipped_lineage():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    open_key = "order:ACZA|O99|1|ITEM9"
    ship_key = "ship:ACZA|D9|ITEM9|PO9|1"
    open_obs = _obs(id=1, key=open_key, job_id=5, line_state="open_order", valid_from=t0, ou="ACZA", order_no="O99", item="ITEM9")
    ship_obs = _obs(
        id=2,
        key=ship_key,
        job_id=6,
        line_state="shipped",
        valid_from=t1,
        ou="ACZA",
        order_no="O99",
        item="ITEM9",
        delivery="D9",
    )

    class _FakeDB:
        def scalars(self, stmt):
            return _FakeResult([open_obs, ship_obs])

    events = derive_change_events(_FakeDB(), limit=100)
    grad = [e for e in events if e.event_type == "graduated"]
    assert len(grad) == 1
    assert grad[0].details["order_grain_key"] == "order:ACZA|O99|1|ITEM9"


def test_split_lines_independent_chains():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    k1 = "ship:ACZA|D1|ITEM1|PO1|1"
    k2 = "ship:ACZA|D1|ITEM1|PO1|2"
    rows = [
        _obs(id=1, key=k1, job_id=1, line_state="shipped", valid_from=t0, qty=1, delivery="D1"),
        _obs(id=2, key=k1, job_id=2, line_state="shipped", valid_from=t1, qty=3, delivery="D1"),
        _obs(id=3, key=k2, job_id=1, line_state="shipped", valid_from=t0, qty=2, delivery="D1"),
        _obs(id=4, key=k2, job_id=2, line_state="shipped", valid_from=t1, qty=4, delivery="D1"),
    ]

    class _FakeDB:
        def scalars(self, stmt):
            return _FakeResult(rows)

    events = derive_change_events(_FakeDB(), limit=100)
    by_key = {k: [e for e in events if e.line_identity_key == k] for k in (k1, k2)}
    assert len(by_key[k1]) >= 1
    assert len(by_key[k2]) >= 1
    assert by_key[k1][0].line_identity_key != by_key[k2][0].line_identity_key


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items
