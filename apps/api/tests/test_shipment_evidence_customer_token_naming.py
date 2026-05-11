from types import SimpleNamespace

from app.services.imports.shipment_evidence_customer_token_naming import (
    NOISE_ONLY_WORDS,
    adjacent_transpose_typo_duplicate_hint,
    detect_statistical_prefixes,
    grouped_candidate_normalized_key,
    plural_merge_canonical_display,
    suggest_customer_token_name,
    suggested_names_similar_for_duplicate_flag,
)


def test_prefix_family_quarters_meet_coverage_collectively() -> None:
    """Q1–Q4 each fall below per-prefix coverage; digit-family union should still select them."""
    others = [f"other{i}" for i in range(86)]
    qs = [f"Q1 p{i}" for i in range(4)]
    qs += [f"Q2 p{i}" for i in range(4)]
    qs += [f"Q3 p{i}" for i in range(4)]
    qs += [f"Q4 p{i}" for i in range(4)]
    toks = qs + others
    prefs, meta = detect_statistical_prefixes(toks)
    assert any(p.upper().startswith("Q") for p in prefs)
    assert meta.get("prefix_families"), "expected at least one inferred prefix family in audit"


def test_reference_tail_stripped_for_partner_name() -> None:
    r = suggest_customer_token_name(
        "Q1 eShop / Alviva PO: PO000133",
        statistical_prefixes_longest_first=[],
        source_def=None,
    )
    assert "eshop" in r.suggested_name.lower()
    assert "alviva" not in r.suggested_name.lower()


def test_internal_note_comma_long_tail() -> None:
    r = suggest_customer_token_name(
        "Q4 Channel, Non MP samples, not allowed to sell",
        statistical_prefixes_longest_first=[],
        source_def=None,
    )
    assert r.special_category == "internal_note"


def test_plural_merge_canonical_strips_trailing_s() -> None:
    assert plural_merge_canonical_display("Afrocentrics") == "Afrocentric"


def test_plural_merge_does_not_mangle_proper_nouns_or_non_plurals() -> None:
    assert plural_merge_canonical_display("Mauritius") == "Mauritius"
    assert plural_merge_canonical_display("Stylus") == "Stylus"
    assert plural_merge_canonical_display("Homeless") == "Homeless"
    assert plural_merge_canonical_display("Winelands") == "Winelands"
    assert plural_merge_canonical_display("St Charles") == "St Charles"
    assert plural_merge_canonical_display("games") == "game"
    assert plural_merge_canonical_display("schools") == "school"


def test_pool_not_stripped_as_po_reference() -> None:
    r = suggest_customer_token_name(
        "Ally Pool",
        statistical_prefixes_longest_first=[],
        source_def=None,
    )
    assert "pool" in r.suggested_name.lower()


def test_trailing_quarter_token_stripped() -> None:
    r = suggest_customer_token_name(
        "Compuspeed Q1",
        statistical_prefixes_longest_first=[],
        source_def=None,
    )
    assert r.suggested_name.lower() == "compuspeed"


def test_sadc_prefix_candidate_injected_for_coverage() -> None:
    others = [f"other{i}" for i in range(10)]
    toks = [
        "SADC - Compuspeed Q1",
        "SADC - Compuspeed Q2",
        "SADC - Compuspeed Q3",
    ] + others
    prefs, meta = detect_statistical_prefixes(toks)
    assert meta["distinct_token_count"] == len(toks)
    assert any("sadc" in p.lower() for p in prefs)


def test_layer1_prefix_requires_coverage_and_absolute_min() -> None:
    toks = ["P1 Shop A", "P1 Shop B", "P1 Shop C", "P1 Shop D", "P1 Shop E", "P1 Shop F", "P1 Shop G", "other"]
    prefs, meta = detect_statistical_prefixes(toks)
    assert meta["distinct_token_count"] == len(toks)
    assert any(p.upper().startswith("P1") for p in prefs)
    r = suggest_customer_token_name("P1 Shop Z", statistical_prefixes_longest_first=prefs, source_def=None)
    assert "shop" in r.suggested_name.lower()


def test_noise_only_remainder_sets_special_category() -> None:
    r = suggest_customer_token_name("Retail", statistical_prefixes_longest_first=[], source_def=None)
    assert r.special_category == "noise_only"
    assert "retail" in NOISE_ONLY_WORDS


def test_layer2_strip_from_expected_template() -> None:
    sd = SimpleNamespace(
        expected_template={
            "shipment_customer_token": {"strip_leading_prefixes": ["DemoCo — "]},
        }
    )
    r = suggest_customer_token_name(
        "DemoCo — Partner One",
        statistical_prefixes_longest_first=[],
        source_def=sd,
    )
    assert "partner" in r.suggested_name.lower()


def test_grouped_normalized_key_for_noise_is_stable_per_token_set() -> None:
    a = grouped_candidate_normalized_key(
        suggested_name="Retail",
        source_tokens=["t1", "t2"],
        special_category="noise_only",
    )
    b = grouped_candidate_normalized_key(
        suggested_name="Retail",
        source_tokens=["t2", "t1"],
        special_category="noise_only",
    )
    assert a == b
    assert a.startswith("sc:")


def test_adjacent_transpose_typo_detection() -> None:
    assert adjacent_transpose_typo_duplicate_hint("Marko", "Makro")
    assert not adjacent_transpose_typo_duplicate_hint("Marko", "Marco")
    assert not adjacent_transpose_typo_duplicate_hint("Ab", "bA")


def test_annotate_customer_possible_duplicates_typo_suspected_of() -> None:
    from decimal import Decimal

    from app.services.imports.shipment_evidence_customer_token_naming import (
        annotate_shipment_customer_pending_duplicates,
    )

    pending = {
        "nk1": {
            "display_suggested_name": "Marko Wholesale",
            "special_category": None,
            "line_ids": [1],
            "source_tokens": ["a"],
            "samples": ["a"],
            "qty": Decimal(0),
            "amt": Decimal(0),
            "needs_name_review": False,
        },
        "nk2": {
            "display_suggested_name": "Makro Wholesale",
            "special_category": None,
            "line_ids": [2],
            "source_tokens": ["b"],
            "samples": ["b"],
            "qty": Decimal(0),
            "amt": Decimal(0),
            "needs_name_review": False,
        },
    }
    annotate_shipment_customer_pending_duplicates(pending)
    assert "nk2" in (pending["nk1"].get("possible_duplicate_of") or [])
    assert "nk2" in (pending["nk1"].get("typo_suspected_of") or [])
    assert "nk1" in (pending["nk2"].get("possible_duplicate_of") or [])


def test_annotate_skips_pairs_when_normalized_name_too_short() -> None:
    from decimal import Decimal

    from app.services.imports.shipment_evidence_customer_token_naming import (
        _norm_key,
        annotate_shipment_customer_pending_duplicates,
    )

    pending = {
        "nk1": {
            "display_suggested_name": "ShortCo",
            "special_category": None,
            "line_ids": [1],
            "source_tokens": ["a"],
            "samples": ["a"],
            "qty": Decimal(0),
            "amt": Decimal(0),
            "needs_name_review": False,
        },
        "nk2": {
            "display_suggested_name": "ShortCe",
            "special_category": None,
            "line_ids": [2],
            "source_tokens": ["b"],
            "samples": ["b"],
            "qty": Decimal(0),
            "amt": Decimal(0),
            "needs_name_review": False,
        },
    }
    assert len(_norm_key("ShortCo")) < 8
    annotate_shipment_customer_pending_duplicates(pending)
    assert not pending["nk1"].get("possible_duplicate_of")
