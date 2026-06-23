"""Tests for paginated shipment mapping candidate list filters."""

from __future__ import annotations

from app.schemas.shipment_mapping_candidates import ShipmentMappingCandidatesListParams
from app.services.imports.shipment_mapping_candidates_list import _apply_list_filters
from app.models.import_distributor_si import ImportEntityMappingCandidate
from sqlalchemy import select


def test_apply_list_filters_entity_distributor_compiles():
    q = select(ImportEntityMappingCandidate)
    params = ShipmentMappingCandidatesListParams(entity="distributor", status="open")
    filtered = _apply_list_filters(q, params)
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "shipment_distributor" in compiled
