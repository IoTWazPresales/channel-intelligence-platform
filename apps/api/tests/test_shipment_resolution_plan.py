"""Tests for shipment resolution plan builder."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    ShipmentEnrichRefs,
    score_shipment_distributor_candidate,
)
from app.services.imports.shipment_resolution_plan import (
    merge_shipment_resolution_plan_row_for_apply,
    plan_shipment_candidate_sync,
)


def test_score_shipment_distributor_display_hint_maps_unique_dim_name():
    dist = SimpleNamespace(id=42, code="RECTRON", name="Rectron")
    refs = ShipmentEnrichRefs(distributors=[dist], customers=[], dist_aliases=[], cust_aliases=[])
    cand = ImportEntityMappingCandidate(
        id=10,
        import_job_id=9,
        entity_type=SHIPMENT_DISTRIBUTOR_ENTITY,
        normalized_key="rectron-za-edu",
        row_count=2,
        status="needs_review",
        context={"suggested_name": "Rectron", "party": "ship_to"},
        sample_raw_values=["RECTRON-ZA-EDU"],
    )
    row = score_shipment_distributor_candidate(None, cand, source_definition_id=1, refs=refs)
    assert row["suggested_action"] == "map_distributor"
    assert row["suggested_entity_id"] == 42
    assert row["match_reason"] == "exact_dim_distributor_name_matches_display_hint"


def test_plan_shipment_historical_corroborated_ready():
    from types import SimpleNamespace

    from app.services.imports.dsi_customer_intelligence import HistoricalCustomerResolution
    from app.services.imports.shipment_resolution_plan import plan_shipment_candidate_sync

    dist = SimpleNamespace(id=7, code="3G", name="3g Mobile")
    cust = SimpleNamespace(id=99, code="TMP-CUST-X", name="3g Mobile")
    refs = ShipmentEnrichRefs(distributors=[dist], customers=[cust], dist_aliases=[], cust_aliases=[])
    cand = ImportEntityMappingCandidate(
        id=11,
        import_job_id=9,
        entity_type=SHIPMENT_CUSTOMER_ENTITY,
        normalized_key="3g mobile",
        row_count=3,
        status="needs_review",
        context={"suggested_name": "3g Mobile"},
        sample_raw_values=["Q3 3G Mobile"],
    )
    job = SimpleNamespace(source=SimpleNamespace(id=1), template_slug="inbound_shipments")
    hist_index = {
        (None, "3g mobile"): HistoricalCustomerResolution(
            customer_id=99,
            import_job_id=100,
            match_reason="steward_map_existing_customer",
            confidence=0.85,
            resolution_kind="shipment_steward_map",
        )
    }
    row = plan_shipment_candidate_sync(None, cand, job, refs=refs, historical_index=hist_index)
    assert row["ready"] is True
    assert row["suggested_action"] == "map_customer"
    assert row["suggested_target_id"] == 99
    assert row["confidence"] == 1.0


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
