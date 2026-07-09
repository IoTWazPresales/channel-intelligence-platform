"""BACKLOG-072 — catalogue gap scan/preview/apply (unit tests, no DB writes)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
from app.services.imports.product_master_gap_resolve import (
    apply_gap_resolve,
    match_token_to_product,
    preview_gap_resolve,
)


def _idx(**kwargs) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    base.update(kwargs)
    return ProductResolutionIndex(**base)


def _session_returning(*batches):
    """Session.scalars(...).all() returns successive batches."""
    session = MagicMock()
    queue = list(batches)

    def _scalars(_stmt):
        result = MagicMock()
        batch = queue.pop(0) if queue else []
        result.all.return_value = batch
        result.first.return_value = batch[0] if batch else None
        return result

    session.scalars.side_effect = _scalars
    session.scalar.return_value = None
    session.execute.return_value = MagicMock()
    return session


@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_match_tier_sku_exact(mock_idx: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"abc-1": 42})
    session = MagicMock()
    m = match_token_to_product(session, "ABC-1")
    assert m["matched"] is True
    assert m["product_id"] == 42
    assert m["match_tier"] == "pm_tier"
    assert m["token"] == "ABC-1"


@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_match_no_fuzzy_substring(mock_idx: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"abcdef": 7})
    session = MagicMock()
    m = match_token_to_product(session, "abc")
    assert m["matched"] is False
    assert m["reason"] == "no_tier_match"


@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_match_steward_alias_wins(mock_idx: MagicMock) -> None:
    mock_idx.return_value = _idx(
        sku_to_id={"tok": 1},
        steward_alias_by_key={"tok": 99},
    )
    m = match_token_to_product(MagicMock(), "TOK")
    assert m["matched"] is True
    assert m["product_id"] == 99
    assert m["match_tier"] == "steward_alias"


@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_match_ambiguous_sales_model(mock_idx: MagicMock) -> None:
    mock_idx.return_value = _idx(sales_model_name_to_ids={"model-x": (1, 2)})
    m = match_token_to_product(MagicMock(), "model-x")
    assert m["matched"] is False


@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_preview_counts_and_dsi_facts_flag(mock_idx: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"gap-sku": 10})
    ship = SimpleNamespace(
        id=1,
        import_job_id=100,
        product_resolution_token="GAP-SKU",
        item_code=None,
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        customer_item=None,
        mpor_item_no=None,
    )
    cand = SimpleNamespace(
        normalized_key="GAP-SKU",
        import_job_id=200,
        status="needs_review",
    )
    claim = SimpleNamespace(
        source_model_token="GAP-SKU",
        import_job_id=300,
        product_id=None,
    )
    session = _session_returning([ship], [cand], [claim])
    out = preview_gap_resolve(session, ["GAP-SKU"])
    item = out["items"][0]
    assert item["matched"] is True
    assert item["counts"]["shipment"] == 1
    assert item["counts"]["dsi_staging"] == 1
    assert item["counts"]["cpor_claim"] == 1
    assert item["counts"]["dsi_facts"] == 0
    assert "dsi_facts_repoint_deferred" in item["flags"]
    assert set(item["affected_job_ids"]) == {100, 200, 300}


@patch("app.services.imports.product_master_gap_resolve.invalidate_product_resolution_index_cache")
@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_apply_requires_confirm(mock_idx: MagicMock, _inv: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"x": 1})
    out = apply_gap_resolve(MagicMock(), tokens=["X"], confirm=False)
    assert out["ok"] is False
    assert out["error"] == "confirm_required"


@patch("app.services.imports.product_master_gap_resolve.invalidate_product_resolution_index_cache")
@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_apply_repoints_and_skips_dsi_facts(mock_idx: MagicMock, mock_inv: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"gap-sku": 10})
    ship = SimpleNamespace(
        id=11,
        import_job_id=100,
        product_resolution_token="GAP-SKU",
        item_code=None,
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        customer_item=None,
        mpor_item_no=None,
    )
    cand = SimpleNamespace(
        id=5,
        normalized_key="GAP-SKU",
        import_job_id=200,
        status="needs_review",
        suggested_entity_id=None,
        match_reason=None,
        context={},
    )
    staging = SimpleNamespace(
        raw_product_token="GAP-SKU",
        resolved_product_id=None,
        import_job_id=200,
    )
    claim = SimpleNamespace(
        source_model_token="GAP-SKU",
        import_job_id=300,
        product_id=None,
    )

    # preview: ship, dsi, claim; repoint_ship; repoint_dsi cands+staging; repoint_cpor
    session = _session_returning(
        [ship],
        [cand],
        [claim],
        [ship],
        [cand],
        [staging],
        [claim],
    )
    out = apply_gap_resolve(
        session,
        tokens=["GAP-SKU"],
        confirm=True,
        write_alias=True,
        actor="test",
    )
    assert out["ok"] is True
    assert out["summary"]["repointed"] == 1
    item = out["items"][0]
    assert item["updated"]["shipment_lines"] == 1
    assert item["updated"]["dsi_staging_candidates"] == 1
    assert item["updated"]["cpor_claim_lines"] == 1
    assert item["updated"]["dsi_facts"] == 0
    assert "dsi_facts_repoint_deferred" in item["flags"]
    assert cand.status == "resolved"
    assert cand.suggested_entity_id == 10
    assert claim.product_id == 10
    assert staging.resolved_product_id == 10
    assert session.add.call_count >= 1
    mock_inv.assert_called()


@patch("app.services.imports.product_master_gap_resolve.invalidate_product_resolution_index_cache")
@patch("app.services.imports.product_master_gap_resolve.get_product_resolution_index")
def test_apply_idempotent_when_already_resolved(mock_idx: MagicMock, _inv: MagicMock) -> None:
    mock_idx.return_value = _idx(sku_to_id={"gap-sku": 10})
    session = _session_returning([], [], [], [], [], [])
    out = apply_gap_resolve(session, tokens=["GAP-SKU"], confirm=True, write_alias=False)
    assert out["ok"] is True
    item = out["items"][0]
    assert item["action"] == "repointed"
    assert item["updated"]["shipment_lines"] == 0
    assert item["updated"]["dsi_staging_candidates"] == 0
    assert item["updated"]["cpor_claim_lines"] == 0


def test_apply_never_imports_dim_product_create() -> None:
    """Guard: module must not auto-create dim_product."""
    import app.services.imports.product_master_gap_resolve as mod

    src = inspect.getsource(mod)
    assert "DimProduct(" not in src
    assert "auto_create" not in src.lower()
