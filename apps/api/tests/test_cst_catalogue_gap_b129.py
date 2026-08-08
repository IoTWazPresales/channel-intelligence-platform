"""BACKLOG-129 — CST catalogue-gap ignore + worklist source."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.cst_mapping_candidates import (
    CST_PRODUCT_ENTITY,
    ignore_cst_candidate_sync,
)
from app.services.imports.product_master_gap_worklist import _deep_link


def test_ignore_cst_product_stamps_ignore_no_catalogue(monkeypatch) -> None:
    cand = SimpleNamespace(
        id=42,
        import_job_id=797,
        entity_type=CST_PRODUCT_ENTITY,
        status="needs_review",
        context={},
        normalized_key="4711636028608",
        row_count=1,
        total_units=1,
        sample_raw_values=["4711636028608"],
        suggested_entity_id=None,
        match_reason=None,
        confidence_score=None,
        created_at=None,
        updated_at=None,
    )
    session = MagicMock()
    session.get.return_value = cand

    def _flush():
        return None

    session.flush.side_effect = _flush
    out = ignore_cst_candidate_sync(session, 797, 42)
    assert cand.status == "ignored"
    assert cand.context.get("steward_ignore_reason_code") == "ignore_no_catalogue"
    assert cand.context.get("catalogue_gap") is True
    assert out["status"] == "ignored"


def test_cst_gap_deep_link() -> None:
    link = _deep_link("cst", {797})
    assert link["href"] == "/admin/imports?job=797"
    assert "CST" in link["label"]
