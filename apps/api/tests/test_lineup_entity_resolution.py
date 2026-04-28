"""Unit tests for case-scoped lineup entity resolution helpers (no DB)."""

from app.models.commercial_lineup import CommercialLineupLine
from app.services.commercial_planner.lineup_entity_resolution import (
    normalize_entity_token,
    refresh_diagnostics_after_entity_update,
)


def test_normalize_entity_token_collapses_whitespace_and_case():
    assert normalize_entity_token("  Acme  Retail  ") == "acme retail"
    assert normalize_entity_token(None) == ""


def test_refresh_diagnostics_clears_unknown_customer_when_id_set():
    ln = CommercialLineupLine(
        case_id=1,
        customer_token="BigBox",
        customer_id=99,
        product_id=1,
        distributor_id=2,
        row_status="imported",
    )
    ln.diagnostic_codes = ["unknown_customer", "manual_case_resolution_customer"]
    refresh_diagnostics_after_entity_update(ln)
    assert "unknown_customer" not in (ln.diagnostic_codes or [])
    assert "manual_case_resolution_customer" in (ln.diagnostic_codes or [])


def test_refresh_diagnostics_unknown_distributor_from_raw_payload():
    ln = CommercialLineupLine(
        case_id=1,
        customer_id=1,
        product_id=1,
        distributor_id=None,
        raw_row_payload={"distributor_token": "Summit"},
        row_status="imported",
    )
    ln.diagnostic_codes = None
    refresh_diagnostics_after_entity_update(ln)
    assert "unknown_distributor" in (ln.diagnostic_codes or [])
