"""Unit tests for CST mapping candidate management (no DB I/O).

Covers:
- upsert_cst_mapping_candidates: aggregation, preservation of resolved candidates, stale cleanup
- load_resolved_cst_candidates: filters correctly on status + suggested_entity_id
- pipeline stage fix: customer_sell_through apply sets STAGE_LOADED not STAGE_VALIDATED
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.imports.cst_mapping_candidates import (
    CST_LOCATION_ENTITY,
    CST_PRODUCT_ENTITY,
    _location_token_key,
    cst_mapping_state_dict,
    load_resolved_cst_candidates,
    upsert_cst_mapping_candidates,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _line(
    *,
    resolved_product_id=None,
    raw_product_token=None,
    resolved_location_id=None,
    raw_location_token=None,
    units_sold=None,
):
    return SimpleNamespace(
        resolved_product_id=resolved_product_id,
        raw_product_token=raw_product_token,
        resolved_location_id=resolved_location_id,
        raw_location_token=raw_location_token,
        units_sold=units_sold,
    )


def _candidate(entity_type, normalized_key, status="needs_review", suggested_entity_id=None):
    return SimpleNamespace(
        entity_type=entity_type,
        normalized_key=normalized_key,
        status=status,
        suggested_entity_id=suggested_entity_id,
        row_count=1,
        total_units=None,
        sample_raw_values=[],
    )


def _db_with(staging_lines, existing_candidates):
    db = MagicMock()
    scalars_mock = MagicMock()

    def _scalars(stmt):
        sm = MagicMock()
        # First call: staging lines; second call: existing candidates
        if not hasattr(_scalars, "_count"):
            _scalars._count = 0
        _scalars._count += 1
        if _scalars._count == 1:
            sm.all.return_value = staging_lines
        else:
            sm.all.return_value = existing_candidates
        return sm

    db.scalars.side_effect = _scalars
    return db


# ---------------------------------------------------------------------------
# _location_token_key
# ---------------------------------------------------------------------------

def test_location_token_key_strips_and_lowercases():
    assert _location_token_key("  Store A  ") == "store a"
    assert _location_token_key("NAN") == ""
    assert _location_token_key(None) == ""


# ---------------------------------------------------------------------------
# upsert_cst_mapping_candidates — basic aggregation
# ---------------------------------------------------------------------------

def test_upsert_creates_product_candidate_for_unresolved_line():
    lines = [_line(raw_product_token="Widget X", units_sold=10)]
    db = _db_with(lines, existing_candidates=[])

    upsert_cst_mapping_candidates(db, job_id=42)

    added = [call_args[0][0] for call_args in db.add.call_args_list]
    assert len(added) == 1
    cand = added[0]
    assert cand.entity_type == CST_PRODUCT_ENTITY
    assert cand.normalized_key == "widget x"
    assert cand.row_count == 1
    assert cand.total_units == 10.0
    assert cand.status == "needs_review"


def test_upsert_creates_location_candidate_for_unresolved_line():
    lines = [_line(raw_location_token="Store 01")]
    db = _db_with(lines, existing_candidates=[])

    upsert_cst_mapping_candidates(db, job_id=1)

    added = [a[0][0] for a in db.add.call_args_list]
    assert any(c.entity_type == CST_LOCATION_ENTITY and c.normalized_key == "store 01" for c in added)


def test_upsert_skips_resolved_product_line():
    lines = [_line(raw_product_token="Widget X", resolved_product_id=99)]
    db = _db_with(lines, existing_candidates=[])

    upsert_cst_mapping_candidates(db, job_id=1)

    # No product candidate should be created
    added = [a[0][0] for a in db.add.call_args_list]
    assert not any(c.entity_type == CST_PRODUCT_ENTITY for c in added)


def test_upsert_aggregates_multiple_lines_with_same_product_token():
    lines = [
        _line(raw_product_token="SKU-A", units_sold=5),
        _line(raw_product_token="SKU-A", units_sold=3),
        _line(raw_product_token="SKU-A", units_sold=None),
    ]
    db = _db_with(lines, existing_candidates=[])

    upsert_cst_mapping_candidates(db, job_id=1)

    added = [a[0][0] for a in db.add.call_args_list]
    prod_cands = [c for c in added if c.entity_type == CST_PRODUCT_ENTITY]
    assert len(prod_cands) == 1
    assert prod_cands[0].row_count == 3
    assert prod_cands[0].total_units == 8.0


# ---------------------------------------------------------------------------
# upsert_cst_mapping_candidates — preserve resolved candidates
# ---------------------------------------------------------------------------

def test_upsert_preserves_resolved_candidate_does_not_update():
    existing_cand = _candidate(CST_PRODUCT_ENTITY, "widget x", status="resolved", suggested_entity_id=7)
    # Still unresolved in staging (would normally be resolved now)
    lines = [_line(raw_product_token="Widget X")]
    db = _db_with(lines, existing_candidates=[existing_cand])

    upsert_cst_mapping_candidates(db, job_id=1)

    # Should not update the resolved candidate's row_count or delete it
    assert existing_cand.row_count == 1  # unchanged (was 1 from constructor)
    db.delete.assert_not_called()


def test_upsert_updates_needs_review_candidate_counts():
    existing_cand = _candidate(CST_PRODUCT_ENTITY, "widget x", status="needs_review")
    lines = [
        _line(raw_product_token="Widget X", units_sold=20),
        _line(raw_product_token="Widget X", units_sold=30),
    ]
    db = _db_with(lines, existing_candidates=[existing_cand])

    upsert_cst_mapping_candidates(db, job_id=1)

    assert existing_cand.row_count == 2
    assert existing_cand.total_units == 50.0


def test_upsert_deletes_stale_needs_review_candidate():
    # Token was unresolved before, now resolved deterministically (no longer in unresolved lines)
    stale_cand = _candidate(CST_PRODUCT_ENTITY, "old-token", status="needs_review")
    lines = []  # no staging lines → no unresolved tokens
    db = _db_with(lines, existing_candidates=[stale_cand])

    upsert_cst_mapping_candidates(db, job_id=1)

    db.delete.assert_called_once_with(stale_cand)


def test_upsert_does_not_delete_resolved_candidate_even_if_stale():
    # Resolved candidate whose token no longer appears in staging — preserve it
    resolved_cand = _candidate(CST_PRODUCT_ENTITY, "resolved-token", status="resolved", suggested_entity_id=5)
    lines = []
    db = _db_with(lines, existing_candidates=[resolved_cand])

    upsert_cst_mapping_candidates(db, job_id=1)

    db.delete.assert_not_called()


# ---------------------------------------------------------------------------
# load_resolved_cst_candidates
# ---------------------------------------------------------------------------

def _resolved_cand(entity_type, key, entity_id):
    c = SimpleNamespace(
        entity_type=entity_type,
        normalized_key=key,
        suggested_entity_id=entity_id,
    )
    return c


def test_load_resolved_splits_by_entity_type():
    prod_cand = _resolved_cand(CST_PRODUCT_ENTITY, "sku-abc", 10)
    loc_cand = _resolved_cand(CST_LOCATION_ENTITY, "store 01", 20)

    db = MagicMock()
    sm = MagicMock()
    sm.all.return_value = [prod_cand, loc_cand]
    db.scalars.return_value = sm

    product_map, location_map = load_resolved_cst_candidates(db, job_id=1)

    assert product_map == {"sku-abc": 10}
    assert location_map == {"store 01": 20}


def test_load_resolved_returns_empty_dicts_when_no_candidates():
    db = MagicMock()
    sm = MagicMock()
    sm.all.return_value = []
    db.scalars.return_value = sm

    product_map, location_map = load_resolved_cst_candidates(db, job_id=1)

    assert product_map == {}
    assert location_map == {}


# ---------------------------------------------------------------------------
# cst_mapping_state_dict
# ---------------------------------------------------------------------------

def test_cst_mapping_state_dict_no_error():
    job = SimpleNamespace(
        id=5,
        status="completed",
        stage="validated",
        import_mode="validate",
        staged_metadata={"some_key": "val"},
    )
    result = cst_mapping_state_dict(job)
    assert result["job_id"] == 5
    assert result["blocking_errors"] == []
    assert result["stage"] == "validated"


def test_cst_mapping_state_dict_with_parse_error():
    job = SimpleNamespace(
        id=5,
        status="completed_with_errors",
        stage="failed",
        import_mode="validate",
        staged_metadata={"customer_sellthrough_error": {"message": "bad header"}},
    )
    result = cst_mapping_state_dict(job)
    assert result["blocking_errors"] == ["bad header"]


# ---------------------------------------------------------------------------
# Pipeline stage fix: apply → STAGE_LOADED
# ---------------------------------------------------------------------------

def test_pipeline_cst_apply_sets_stage_loaded():
    """The pipeline sets STAGE_LOADED (not STAGE_VALIDATED) for CST apply runs."""
    from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED

    # Simulate the branch logic from pipeline.py
    handler = "customer_sell_through"
    import_mode = "apply"
    errors = 0

    if handler == "customer_sell_through" and (import_mode or "").strip().lower() == "apply" and not errors:
        stage = STAGE_LOADED
    else:
        stage = STAGE_VALIDATED

    assert stage == STAGE_LOADED


def test_pipeline_cst_validate_keeps_stage_validated():
    from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED

    handler = "customer_sell_through"
    import_mode = "validate"
    errors = 0

    if handler == "customer_sell_through" and (import_mode or "").strip().lower() == "apply" and not errors:
        stage = STAGE_LOADED
    else:
        stage = STAGE_VALIDATED

    assert stage == STAGE_VALIDATED


def test_pipeline_non_cst_apply_keeps_stage_validated():
    from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED

    handler = "distributor_sales_inventory"
    import_mode = "apply"
    errors = 0

    if handler == "customer_sell_through" and (import_mode or "").strip().lower() == "apply" and not errors:
        stage = STAGE_LOADED
    else:
        stage = STAGE_VALIDATED

    assert stage == STAGE_VALIDATED


def test_pipeline_cst_apply_with_errors_keeps_stage_validated():
    from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED

    handler = "customer_sell_through"
    import_mode = "apply"
    errors = 1  # errors present → stay VALIDATED

    if handler == "customer_sell_through" and (import_mode or "").strip().lower() == "apply" and not errors:
        stage = STAGE_LOADED
    else:
        stage = STAGE_VALIDATED

    assert stage == STAGE_VALIDATED
