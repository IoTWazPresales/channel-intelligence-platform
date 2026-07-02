"""Canonical lineup period keys and active-case filters."""

from datetime import date

from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_period_canonical import (
    display_period_label_from_period_start,
    is_active_lineup_case,
    period_filter_matches_period_start,
    quarter_key_from_period_start,
)


def test_period_filter_matches_across_label_formats():
    case_start = date(2026, 4, 1)
    assert period_filter_matches_period_start("26Q2", case_start)
    assert period_filter_matches_period_start("2026 Q2", case_start)
    assert period_filter_matches_period_start("2026-Q2", case_start)
    assert not period_filter_matches_period_start("26Q1", case_start)


def test_display_period_label_majority_format():
    assert display_period_label_from_period_start(date(2026, 4, 1)) == "2026 Q2"
    assert quarter_key_from_period_start(date(2026, 4, 1)) == "26Q2"


def test_case_coverage_key_uses_business_unit_over_inferred_product_line():
    from app.services.commercial_planner.lineup_period_canonical import case_coverage_key

    case = CommercialLineupCase(
        id=1,
        business_unit="NB",
        product_line="NR",
        inferred_period_start=date(2026, 4, 1),
        import_intent="x",
        source_context="y",
    )
    assert case_coverage_key(case) == {(2026, 2, "NB")}


def test_canonical_case_line_code_prefers_business_unit():
    from app.services.commercial_planner.lineup_period_canonical import canonical_case_line_code

    case = CommercialLineupCase(
        id=1,
        business_unit="PF",
        product_line="NR",
        import_intent="x",
        source_context="y",
    )
    assert canonical_case_line_code(case) == "PF"


def test_is_active_lineup_case_excludes_superseded():
    active = CommercialLineupCase(
        id=1,
        commercial_status="draft_imported",
        superseded_by_case_id=None,
        import_intent="x",
        source_context="y",
    )
    shell = CommercialLineupCase(
        id=2,
        commercial_status="superseded",
        superseded_by_case_id=99,
        import_intent="x",
        source_context="y",
    )
    assert is_active_lineup_case(active)
    assert not is_active_lineup_case(shell)
