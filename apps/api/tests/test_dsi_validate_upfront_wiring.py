"""DSI validate upfront wiring (no DB): single cache build, tx-closing heartbeat, sub-phase labels."""

from __future__ import annotations

from pathlib import Path

from app.services.imports.distributor_sales_inventory import dsi_validate_sub_phase_label

_DSI_SRC = Path(__file__).resolve().parents[1] / "app/services/imports/distributor_sales_inventory.py"


def test_resolution_cache_ready_sub_phase_label() -> None:
    assert dsi_validate_sub_phase_label("resolution_cache_ready") == "Resolving primary distributor"


def test_unknown_sub_phase_degrades_to_title_case() -> None:
    # Frontend never breaks on an unmapped sub-phase — it title-cases the key.
    assert dsi_validate_sub_phase_label("some_new_phase") == "Some New Phase"
    assert dsi_validate_sub_phase_label(None) is None


def test_upfront_builds_cache_once_and_passes_it_to_resolve_primary() -> None:
    """Validate upfront builds the resolution cache once and reuses it for the primary scan."""
    text = _DSI_SRC.read_text(encoding="utf-8")
    build_idx = text.find(
        "res_cache = _build_resolution_cache(db, source_def_id, on_sub_phase=_upfront_progress)"
    )
    assert build_idx != -1, "upfront resolution-cache build call not found"
    call_idx = text.find(
        "primary_dist_id = resolve_primary_distributor_id_from_dataframe(", build_idx
    )
    assert call_idx != -1, "resolve_primary call not found after cache build"
    snippet = text[call_idx : call_idx + 200]
    assert "res_cache=res_cache" in snippet, "prebuilt res_cache must be passed (no second build)"


def test_tx_closing_heartbeat_between_cache_build_and_primary_scan() -> None:
    """The alias/open-channel read tx is committed before the CPU-bound primary scan (idle-in-tx fix)."""
    text = _DSI_SRC.read_text(encoding="utf-8")
    build_idx = text.find(
        "res_cache = _build_resolution_cache(db, source_def_id, on_sub_phase=_upfront_progress)"
    )
    close_idx = text.find('_upfront_progress("resolution_cache_ready")', build_idx)
    call_idx = text.find(
        "primary_dist_id = resolve_primary_distributor_id_from_dataframe(", build_idx
    )
    assert build_idx != -1 and close_idx != -1 and call_idx != -1
    # Ordering: build cache -> commit/close tx -> primary scan
    assert build_idx < close_idx < call_idx
