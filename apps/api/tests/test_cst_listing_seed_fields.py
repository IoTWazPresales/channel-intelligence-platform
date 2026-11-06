"""CST listing_seed feed_profile → listing_* fields (generic, any marketplace)."""

from app.services.imports.cst_d1 import apply_listing_seed_fields


def test_listing_seed_copies_product_token_when_configured():
    row = {"raw_product_token": "B0ABC123", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a", "external_id_from": "raw_product_token"}},
    )
    assert row["listing_external_id"] == "B0ABC123"
    assert row["listing_marketplace"] == "shop-a"


def test_listing_seed_column_wins_over_feed_profile():
    row = {
        "raw_product_token": "B0ABC123",
        "listing_external_id": "OFFER-9",
        "listing_marketplace": "Shop-B",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a", "external_id_from": "raw_product_token"}},
    )
    assert row["listing_external_id"] == "OFFER-9"
    assert row["listing_marketplace"] == "shop-b"


def test_listing_seed_noop_without_marketplace_config():
    row = {"raw_product_token": "SKU1", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(row, {"layout_family": "plain"})
    assert row["listing_external_id"] is None
    assert row["listing_marketplace"] is None


def test_layout_family_does_not_invent_a_marketplace():
    row = {"raw_product_token": "12345678", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(row, {"layout_family": "week_file"})
    assert row["listing_external_id"] is None
    assert row["listing_marketplace"] is None


def test_listing_seed_compacts_spaced_numeric_id_when_configured():
    row = {
        "raw_product_token": "4711387767535",
        "listing_external_id": "222 547 542",
        "listing_marketplace": "shop-a",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a", "compact_spaced_numeric_external_id": True}},
    )
    assert row["listing_external_id"] == "222547542"


def test_spaced_numeric_id_stays_when_compact_is_not_configured():
    """No flag and no prior ids: do not invent a compact. History has to show the shape."""
    row = {
        "listing_external_id": "222 547 542",
        "listing_marketplace": "shop-a",
    }
    apply_listing_seed_fields(row, {"listing_seed": {"marketplace": "shop-a"}})
    assert row["listing_external_id"] == "222 547 542"


def test_absent_flag_compacts_when_prior_ids_are_already_compacted():
    row = {
        "listing_external_id": "222 547 542",
        "listing_marketplace": "shop-a",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a"}},
        prior_external_ids=("222547542", "PLU-KEEP"),
    )
    assert row["listing_external_id"] == "222547542"


def test_absent_flag_keeps_spaces_when_a_prior_numeric_id_kept_spaces():
    row = {
        "listing_external_id": "222 547 542",
        "listing_marketplace": "shop-a",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a"}},
        prior_external_ids=("222 547 541", "333444555"),
    )
    assert row["listing_external_id"] == "222 547 542"


def test_explicit_false_does_not_compact_even_when_prior_ids_are_compacted():
    row = {
        "listing_external_id": "222 547 542",
        "listing_marketplace": "shop-a",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "shop-a", "compact_spaced_numeric_external_id": False}},
        prior_external_ids=("222547542",),
    )
    assert row["listing_external_id"] == "222 547 542"
