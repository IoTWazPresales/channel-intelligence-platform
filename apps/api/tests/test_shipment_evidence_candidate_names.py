from app.services.imports.shipment_evidence_candidate_names import (
    suggested_name_for_customer_token,
    suggested_name_for_distributor_token,
)


def test_distributor_region_code_tail_stripped() -> None:
    assert "mustek" in suggested_name_for_distributor_token("MUSTEK-ZA-BB").lower()
    assert "za" not in suggested_name_for_distributor_token("PINNACLE-ZA-IR").lower()
    assert "brandhouse" in suggested_name_for_distributor_token("BRANDHOUSE-MU-C").lower()


def test_distributor_suffix_stripped_and_title() -> None:
    out = suggested_name_for_distributor_token("ACME INC")
    assert "INC" not in out.upper()
    assert "acme" in out.lower()


def test_customer_title_case_fallback_without_job_statistics() -> None:
    """Single-token calls have no statistical prefix (coverage thresholds), so Layer 3 title-cases."""
    out = suggested_name_for_customer_token("acme trading")
    assert "acme" in out.lower()


def test_customer_layer1_when_prefixes_supplied() -> None:
    from app.services.imports.shipment_evidence_customer_token_naming import (
        detect_statistical_prefixes,
        suggest_customer_token_name,
    )

    toks = ["Q2 Shop A", "Q2 Shop B", "Q2 Shop C", "Q2 Shop D", "Q2 Shop E", "Q2 Shop F", "Q2 Shop G", "other"]
    prefs, _ = detect_statistical_prefixes(toks)
    r = suggest_customer_token_name("Q2 Shop Z", statistical_prefixes_longest_first=prefs, source_def=None)
    assert "shop" in r.suggested_name.lower()
