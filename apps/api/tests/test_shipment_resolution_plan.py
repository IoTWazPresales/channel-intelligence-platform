"""Tests for shipment resolution plan builder."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_resolution_plan import (
    merge_shipment_resolution_plan_row_for_apply,
    plan_shipment_candidate_sync,
)


def test_plan_shipment_terminal_candidate():
    job = SimpleNamespace(source=None, template_slug="inbound_shipments")
    cand = ImportEntityMappingCandidate(
        id=1,
        import_job_id=9,
        entity_type=SHIPMENT_DISTRIBUTOR_ENTITY,
        normalized_key="acme",
        row_count=1,
        status="resolved",
        context={"party": "bill_to"},
    )
    row = plan_shipment_candidate_sync(None, cand, job, refs=None, historical_index={})
    assert row["ready"] is False
    assert row["suggested_action"] == "none"


def test_plan_shipment_special_category_blocks():
    job = SimpleNamespace(source=None, template_slug="inbound_shipments")
    cand = ImportEntityMappingCandidate(
        id=2,
        import_job_id=9,
        entity_type=SHIPMENT_CUSTOMER_ENTITY,
        normalized_key="noise",
        row_count=1,
        status="needs_review",
        context={"special_category": "noise_only"},
    )
    row = plan_shipment_candidate_sync(None, cand, job, refs=None, historical_index={})
    assert row["ready"] is False
    assert "special_category" in str(row.get("resolution_blockers"))


def test_merge_previously_resolved_requires_confirm():
    cand = ImportEntityMappingCandidate(
        id=3,
        import_job_id=9,
        entity_type=SHIPMENT_CUSTOMER_ENTITY,
        normalized_key="resq",
        row_count=1,
        status="needs_review",
        context={},
    )
    base = {
        "ready": False,
        "suggested_action": "map_customer",
        "suggested_target_id": 99,
        "historical_resolution": {"label": "previously_resolved"},
        "resolution_blockers": ["previously_resolved_confirm"],
    }
    merged = merge_shipment_resolution_plan_row_for_apply(cand=cand, base=base, ov=None)
    assert merged["ready"] is False
    merged2 = merge_shipment_resolution_plan_row_for_apply(
        cand=cand, base=base, ov={"confirm_previously_resolved": True}
    )
    assert merged2["ready"] is True
