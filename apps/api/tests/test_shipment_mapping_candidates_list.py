"""Tests for paginated shipment mapping candidate list filters."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.schemas.shipment_mapping_candidates import ShipmentMappingCandidatesListParams
from app.services.imports.shipment_mapping_candidates_list import (
    _apply_list_filters,
    _serialize_candidate,
    context_for_list_payload,
)


def test_apply_list_filters_entity_distributor_compiles():
    q = select(ImportEntityMappingCandidate)
    params = ShipmentMappingCandidatesListParams(entity="distributor", status="open")
    filtered = _apply_list_filters(q, params)
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "shipment_distributor" in compiled


def test_context_for_list_payload_omits_line_ids_keeps_other_keys():
    raw = {
        "line_ids": [1, 2, 3],
        "party": "bill_to",
        "suggested_name": "Acme",
        "suggested_action": "map_existing",
        "needs_name_review": True,
    }
    slim = context_for_list_payload(raw)
    assert slim is not None
    assert "line_ids" not in slim
    assert slim["party"] == "bill_to"
    assert slim["suggested_name"] == "Acme"
    assert slim["suggested_action"] == "map_existing"
    assert slim["needs_name_review"] is True
    # Does not mutate source
    assert raw["line_ids"] == [1, 2, 3]


def test_context_for_list_payload_none_and_non_dict():
    assert context_for_list_payload(None) is None
    assert context_for_list_payload("x") is None  # type: ignore[arg-type]
    assert context_for_list_payload({}) == {}


def test_serialize_candidate_omits_context_line_ids_keeps_row_count():
    now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    r = SimpleNamespace(
        id=10,
        import_job_id=5,
        source_definition_id=None,
        entity_type="shipment_distributor",
        normalized_key="acme",
        dealer_group_token=None,
        row_count=3,
        total_units=3.0,
        total_reported_value=30.0,
        sample_raw_values=["ACME"],
        suggested_entity_id=7,
        match_reason="exact",
        confidence_score=0.9,
        status="needs_review",
        context={
            "line_ids": [11, 12, 13],
            "party": "ship_to",
            "suggested_action": "map_existing",
        },
        created_at=now,
        updated_at=now,
    )
    item = _serialize_candidate(
        r,  # type: ignore[arg-type]
        dist_names={7: {"distributor_code": "D1", "distributor_name": "Dist One"}},
        cust_names={},
    )
    assert item["row_count"] == 3
    assert isinstance(item["context"], dict)
    assert "line_ids" not in item["context"]
    assert item["context"]["party"] == "ship_to"
    assert item["suggested_action"] == "map_existing"
    assert item["suggested_distributor_code"] == "D1"
    # ORM/source context untouched
    assert r.context["line_ids"] == [11, 12, 13]
