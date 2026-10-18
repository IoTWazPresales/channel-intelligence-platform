"""N-0111 (Warren 2026-10-19): a row's product identifiers resolve in the platform order
Part number -> Barcode -> Sales model, then the customer's own product code through the customer's aliases.

Exact / normalised-exact only; one match wins only if unambiguous; identifiers that disagree on one
row are a conflict, never a guess. Pure: a hand-built Product Master index, no database.
"""

from __future__ import annotations

from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
from app.services.imports.product_resolution_standard import (
    RESULT_AMBIGUOUS,
    RESULT_CONFLICT,
    RESULT_RESOLVED,
    RESULT_UNMATCHED,
    SLOT_ANY,
    SLOT_BARCODE,
    SLOT_CUSTOMER_CODE,
    SLOT_PART_NUMBER,
    SLOT_SALES_MODEL,
    TIER_CONFLICT,
    resolve_product_by_identifiers,
    resolve_product_id_single_match,
)


def _index(**kw) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id={},
        steward_alias_by_key={},
    )
    base.update(kw)
    return ProductResolutionIndex(**base)


# Product 1: part 90NB1, EAN 4711000000011, UPC 711000000012, model X1. Product 2: part 90NB2, model X2.
IDX = _index(
    sku_to_id={"sku-1": 1, "sku-2": 2},
    part_number_to_ids={"90nb1": (1,), "90nb2": (2,), "shared-pn": (1, 2)},
    ean_to_ids={"4711000000011": (1,), "4711000000028": (2,), "dup-ean": (1, 2)},
    upc_to_ids={"711000000012": (1,), "711000000029": (2,)},
    sales_model_name_to_ids={"x1": (1,), "x2": (2,), "x-shared": (1, 2)},
    marketing_name_to_ids={"fancy one": (1,)},
)


def test_all_three_identifiers_agreeing_resolve_on_the_part_number_tier() -> None:
    m = resolve_product_by_identifiers(
        IDX, {SLOT_PART_NUMBER: "90NB1", SLOT_BARCODE: "4711000000011", SLOT_SALES_MODEL: "X1"}
    )
    assert (m.result, m.product_id, m.tier) == (RESULT_RESOLVED, 1, "part_number")
    assert [o.status for o in m.outcomes] == ["unique", "unique", "unique"]
    assert [o.slot for o in m.outcomes] == [SLOT_PART_NUMBER, SLOT_BARCODE, SLOT_SALES_MODEL]


def test_a_barcode_matches_product_master_ean_or_upc() -> None:
    by_ean = resolve_product_by_identifiers(IDX, {SLOT_BARCODE: "4711000000011"})
    by_upc = resolve_product_by_identifiers(IDX, {SLOT_BARCODE: "711000000012"})
    assert (by_ean.product_id, by_ean.tier) == (1, "ean")
    assert (by_upc.product_id, by_upc.tier) == (1, "upc")
    # Excel's trailing .0 on a number cell is the same barcode.
    assert resolve_product_by_identifiers(IDX, {SLOT_BARCODE: "711000000012.0"}).product_id == 1


def test_a_sales_model_alone_resolves_and_marketing_name_is_matched_too() -> None:
    assert resolve_product_by_identifiers(IDX, {SLOT_SALES_MODEL: "x2"}).tier == "sales_model_name"
    m = resolve_product_by_identifiers(IDX, {SLOT_SALES_MODEL: "Fancy One"})
    assert (m.product_id, m.tier) == (1, "marketing_name")


def test_the_platform_order_picks_the_first_slot_that_matches() -> None:
    # Part number unknown, barcode known: the barcode wins; the unmatched part number is not a conflict.
    m = resolve_product_by_identifiers(IDX, {SLOT_PART_NUMBER: "NOPE", SLOT_BARCODE: "4711000000028"})
    assert (m.result, m.product_id, m.tier) == (RESULT_RESOLVED, 2, "ean")
    assert [o.status for o in m.outcomes] == ["no_match", "unique"]


def test_identifiers_pointing_at_different_products_are_a_conflict_not_a_guess() -> None:
    m = resolve_product_by_identifiers(IDX, {SLOT_PART_NUMBER: "90NB1", SLOT_BARCODE: "4711000000028"})
    assert (m.result, m.product_id, m.tier) == (RESULT_CONFLICT, None, TIER_CONFLICT)
    assert {o.product_ids for o in m.outcomes} == {(1,), (2,)}
    # Barcode (EAN of one, UPC of the other) and sales model disagreeing is also a conflict.
    m2 = resolve_product_by_identifiers(IDX, {SLOT_BARCODE: "711000000012", SLOT_SALES_MODEL: "x2"})
    assert m2.result == RESULT_CONFLICT and m2.product_id is None


def test_an_ambiguous_slot_is_passed_over_and_the_next_slot_decides_when_it_is_consistent() -> None:
    m = resolve_product_by_identifiers(IDX, {SLOT_PART_NUMBER: "shared-pn", SLOT_BARCODE: "4711000000011"})
    assert (m.result, m.product_id, m.tier) == (RESULT_RESOLVED, 1, "ean")
    assert m.outcomes[0].status == "ambiguous" and m.outcomes[0].product_ids == (1, 2)


def test_an_ambiguous_slot_that_excludes_the_winner_is_a_conflict() -> None:
    idx = _index(
        part_number_to_ids={"pn-12": (1, 2)},
        ean_to_ids={"4700000000003": (3,)},
        products_by_id={},
    )
    m = resolve_product_by_identifiers(idx, {SLOT_PART_NUMBER: "pn-12", SLOT_BARCODE: "4700000000003"})
    assert (m.result, m.product_id) == (RESULT_CONFLICT, None)


def test_only_ambiguous_matches_stay_unresolved() -> None:
    m = resolve_product_by_identifiers(IDX, {SLOT_BARCODE: "dup-ean"})
    assert (m.result, m.product_id) == (RESULT_AMBIGUOUS, None)
    # A barcode that is the EAN of one product and the UPC of another is ambiguous too.
    idx = _index(ean_to_ids={"123": (1,)}, upc_to_ids={"123": (2,)})
    assert resolve_product_by_identifiers(idx, {SLOT_BARCODE: "123"}).result == RESULT_AMBIGUOUS


def test_nothing_fuzzy_ever_matches() -> None:
    for slot, token in (
        (SLOT_PART_NUMBER, "90NB1-X"),
        (SLOT_BARCODE, "471100000001"),
        (SLOT_SALES_MODEL, "X1-CM"),  # the DSI channel-suffix peel is not used here
        (SLOT_SALES_MODEL, "x"),
    ):
        m = resolve_product_by_identifiers(IDX, {slot: token})
        assert (m.result, m.product_id) == (RESULT_UNMATCHED, None), (slot, token)


def test_the_customers_own_code_resolves_only_through_the_customers_aliases() -> None:
    aliases = {"art-7": 2}
    lookup = lambda token: aliases.get(token.lower())  # noqa: E731
    m = resolve_product_by_identifiers(IDX, {SLOT_CUSTOMER_CODE: "ART-7"}, customer_code_alias=lookup)
    assert (m.result, m.product_id, m.tier) == (RESULT_RESOLVED, 2, "customer_alias")
    # A customer code that equals a Product Master SKU is NOT matched to Product Master.
    m = resolve_product_by_identifiers(IDX, {SLOT_CUSTOMER_CODE: "sku-1"}, customer_code_alias=lookup)
    assert (m.result, m.product_id) == (RESULT_UNMATCHED, None)
    # Without an alias lookup it never resolves.
    assert resolve_product_by_identifiers(IDX, {SLOT_CUSTOMER_CODE: "ART-7"}).product_id is None


def test_a_customer_alias_that_disagrees_with_the_identifiers_is_a_conflict() -> None:
    lookup = lambda token: 2  # noqa: E731
    m = resolve_product_by_identifiers(
        IDX, {SLOT_PART_NUMBER: "90NB1", SLOT_CUSTOMER_CODE: "ART-7"}, customer_code_alias=lookup
    )
    assert (m.result, m.product_id) == (RESULT_CONFLICT, None)
    agree = resolve_product_by_identifiers(
        IDX, {SLOT_PART_NUMBER: "90NB2", SLOT_CUSTOMER_CODE: "ART-7"}, customer_code_alias=lookup
    )
    assert (agree.result, agree.product_id, agree.tier) == (RESULT_RESOLVED, 2, "part_number")


def test_blank_identifiers_are_ignored_and_a_row_with_none_is_unmatched() -> None:
    m = resolve_product_by_identifiers(IDX, {SLOT_PART_NUMBER: "  ", SLOT_BARCODE: None, SLOT_SALES_MODEL: "x1"})
    assert (m.result, m.product_id) == (RESULT_RESOLVED, 1) and len(m.outcomes) == 1
    assert resolve_product_by_identifiers(IDX, {}).result == RESULT_UNMATCHED


def test_the_older_any_identifier_slot_uses_the_standard_tiers() -> None:
    for token, pid in (("sku-2", 2), ("90NB1", 1), ("4711000000011", 1), ("711000000029", 2), ("x2", 2)):
        m = resolve_product_by_identifiers(IDX, {SLOT_ANY: token})
        assert (m.result, m.product_id) == (RESULT_RESOLVED, pid), token
        # Same answer as the standard single-match function the older layouts use.
        assert resolve_product_id_single_match(IDX, token) == pid
