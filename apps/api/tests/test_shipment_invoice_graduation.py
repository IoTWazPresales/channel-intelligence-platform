"""Unit tests for invoice-line mint graduation (quantity-gated supersession)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_invoice_graduation import (
    STEWARD_FLAG_PARTIAL,
    apply_lineage_graduation,
    evaluate_lineage_graduation,
    has_partial_graduation_flag,
    is_blank_invoice_shipped_obs,
    is_numbered_invoice_shipped_obs,
    process_lineages_for_graduation,
    steward_flags,
)
from app.services.imports.shipment_change_events import derive_change_events


def _obs(
    *,
    id: int,
    key: str,
    qty: float,
    invoice_line: str | None = None,
    order_no: str = "O1",
    order_line: str = "1.1",
    item: str = "ITEM1",
    ou: str | None = None,
    delivery: str | None = None,
    job_id: int = 1,
    valid_from: datetime | None = None,
) -> ShipmentEvidenceObservation:
    t = valid_from or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ShipmentEvidenceObservation(
        id=id,
        line_identity_key=key,
        import_job_id=job_id,
        source_key=f"sk-{id}",
        source_row_hash=f"hash{id:040d}",
        valid_from=t,
        observed_at=t,
        source_row_number=1,
        report_type="acza_workbook_shipped",
        line_state="shipped",
        raw_source_row={},
        operating_unit=ou,
        order_no=order_no,
        order_line=order_line,
        item_code=item,
        delivery_no=delivery,
        invoice_line=invoice_line,
        quantity=qty,
        product_resolution_status="unresolved",
        distributor_resolution_status="unresolved",
    )


def test_blank_and_numbered_classifiers():
    blank = _obs(id=1, key="order:O1|1.1|ITEM1", qty=10, invoice_line=None)
    numbered = _obs(
        id=2,
        key="ship:ACZA|D1|ITEM1|99|1",
        qty=10,
        invoice_line="1",
        ou="ACZA",
        delivery="D1",
    )
    assert is_blank_invoice_shipped_obs(blank)
    assert not is_numbered_invoice_shipped_obs(blank)
    assert is_numbered_invoice_shipped_obs(numbered)
    assert not is_blank_invoice_shipped_obs(numbered)


def test_full_graduation_qty_gate():
    blank = [_obs(id=1, key="order:O1|1.1|ITEM1", qty=48)]
    numbered = [_obs(id=2, key="ship:ACZA|D1|ITEM1|99|1", qty=48, invoice_line="1", ou="ACZA", delivery="D1")]
    v = evaluate_lineage_graduation(blank, numbered)
    assert v.outcome == "full"
    assert v.blank_qty == 48
    assert v.numbered_qty == 48


def test_partial_graduation_qty_mismatch():
    blank = [_obs(id=1, key="order:O1|1.1|ITEM1", qty=48)]
    numbered = [_obs(id=2, key="ship:ACZA|D1|ITEM1|99|1", qty=40, invoice_line="1", ou="ACZA", delivery="D1")]
    v = evaluate_lineage_graduation(blank, numbered)
    assert v.outcome == "partial"


def test_multi_split_numbered_lines_full_graduation():
    blank = [_obs(id=1, key="order:O1|1.1|ITEM1", qty=100)]
    numbered = [
        _obs(id=2, key="ship:ACZA|D1|ITEM1|99|1", qty=60, invoice_line="1", ou="ACZA", delivery="D1"),
        _obs(id=3, key="ship:ACZA|D1|ITEM1|99|2", qty=40, invoice_line="2", ou="ACZA", delivery="D1"),
    ]
    v = evaluate_lineage_graduation(blank, numbered)
    assert v.outcome == "full"
    assert len(v.numbered_keys) == 2


def test_apply_full_supersedes_all_blank_history_versions():
    """Supersede every bitemporal version of each blank identity key, not only the current winner."""
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    blank_key = "order:O1|1.1|ITEM1"
    blank_v1 = _obs(id=10, key=blank_key, qty=20, valid_from=t0)
    blank_v2 = _obs(id=12, key=blank_key, qty=20, valid_from=t1)
    numbered_obs = _obs(
        id=11,
        key="ship:ACZA|D1|ITEM1|5|1",
        qty=20,
        invoice_line="1",
        ou="ACZA",
        delivery="D1",
    )
    v = evaluate_lineage_graduation([blank_v2], [numbered_obs])
    assert v.outcome == "full"

    class _FakeSession:
        def flush(self):
            return None

        def scalars(self, stmt):
            return _FakeResult([blank_v1, blank_v2])

        def execute(self, *_args, **_kwargs):
            return _FakeScalarResult([blank_v2.id])

    class _FakeScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return [(i,) for i in self._rows]

    out = apply_lineage_graduation(_FakeSession(), v, [blank_v2], dry_run=False)
    assert blank_v1.superseded_by_id == 11
    assert blank_v2.superseded_by_id == 11
    assert out["superseded_observations"] == 2


def test_apply_full_supersedes_blank_observation():
    blank_obs = _obs(id=10, key="order:O1|1.1|ITEM1", qty=20)
    numbered_obs = _obs(
        id=11,
        key="ship:ACZA|D1|ITEM1|5|1",
        qty=20,
        invoice_line="1",
        ou="ACZA",
        delivery="D1",
    )
    v = evaluate_lineage_graduation([blank_obs], [numbered_obs])
    assert v.outcome == "full"

    class _FakeSession:
        def flush(self):
            return None

        def scalars(self, stmt):
            return _FakeResult([blank_obs])

        def execute(self, *_args, **_kwargs):
            return _FakeScalarResult([blank_obs.id])

    class _FakeScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return [(i,) for i in self._rows]

    out = apply_lineage_graduation(_FakeSession(), v, [blank_obs], dry_run=False)
    assert blank_obs.superseded_by_id == 11
    assert out["outcome"] == "full"


def test_apply_partial_sets_steward_flag():
    blank_obs = _obs(id=20, key="order:O1|1.1|ITEM1", qty=50)
    numbered_obs = _obs(
        id=21,
        key="ship:ACZA|D1|ITEM1|5|1",
        qty=30,
        invoice_line="1",
        ou="ACZA",
        delivery="D1",
    )
    v = evaluate_lineage_graduation([blank_obs], [numbered_obs])
    assert v.outcome == "partial"

    class _FakeSession:
        def flush(self):
            return None

        def scalars(self, stmt):
            return _FakeResult([blank_obs])

        def execute(self, *_args, **_kwargs):
            return _FakeScalarResult([blank_obs.id])

    class _FakeScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return [(i,) for i in self._rows]

    apply_lineage_graduation(_FakeSession(), v, [blank_obs], dry_run=False)
    assert STEWARD_FLAG_PARTIAL in steward_flags(blank_obs)
    assert has_partial_graduation_flag(blank_obs)
    assert blank_obs.superseded_by_id is None


def test_revalidate_no_op_when_already_superseded():
    blank_obs = _obs(id=30, key="order:O1|1.1|ITEM1", qty=10)
    blank_obs.superseded_by_id = 99
    numbered = [_obs(id=31, key="ship:ACZA|D1|ITEM1|1|1", qty=10, invoice_line="1", ou="ACZA", delivery="D1")]
    v = evaluate_lineage_graduation([blank_obs], numbered)
    assert v.outcome == "none"


def test_invoice_mint_change_event():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    blank_key = "order:O99|1.1|ITEM9"
    ship_key = "ship:ACZA|D9|ITEM9|PO9|1"
    blank_obs = _obs(
        id=1,
        key=blank_key,
        qty=10,
        order_no="O99",
        item="ITEM9",
        valid_from=t0,
    )
    ship_obs = _obs(
        id=2,
        key=ship_key,
        qty=10,
        order_no="O99",
        item="ITEM9",
        invoice_line="1",
        ou=None,
        delivery="D9",
        valid_from=t1,
    )

    class _FakeDB:
        def scalars(self, stmt):
            return _FakeResult([blank_obs, ship_obs])

    events = derive_change_events(_FakeDB(), limit=100)
    mint = [e for e in events if e.details.get("graduation_kind") == "invoice_mint"]
    assert len(mint) == 1
    assert mint[0].prior_observation_id == 1
    assert mint[0].observation_id == 2


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


@pytest.mark.skipif(
    not __import__("os").environ.get("ALLOW_TESTS_ON_DEV_DB"),
    reason="Set ALLOW_TESTS_ON_DEV_DB=1 for cip integration graduation test",
)
def test_process_lineages_integration_on_cip():
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if dbname != "cip":
            pytest.skip("cip only")
        assert process_lineages_for_graduation(db, set(), dry_run=True) == []
