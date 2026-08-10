"""CST listing_seed feed_profile → listing_* fields (generic, any marketplace)."""

from app.services.imports.cst_d1 import apply_listing_seed_fields


def test_listing_seed_copies_product_token_when_configured():
    row = {"raw_product_token": "B0ABC123", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "amazon", "external_id_from": "raw_product_token"}},
    )
    assert row["listing_external_id"] == "B0ABC123"
    assert row["listing_marketplace"] == "amazon"


def test_listing_seed_column_wins_over_feed_profile():
    row = {
        "raw_product_token": "B0ABC123",
        "listing_external_id": "OFFER-9",
        "listing_marketplace": "Takealot",
    }
    apply_listing_seed_fields(
        row,
        {"listing_seed": {"marketplace": "amazon", "external_id_from": "raw_product_token"}},
    )
    assert row["listing_external_id"] == "OFFER-9"
    assert row["listing_marketplace"] == "takealot"


def test_listing_seed_noop_without_marketplace_config():
    row = {"raw_product_token": "SKU1", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(row, {"layout_family": "plain"})
    assert row["listing_external_id"] is None
    assert row["listing_marketplace"] is None


def test_listing_seed_defaults_from_takealot_layout_family():
    row = {"raw_product_token": "12345678", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(row, {"layout_family": "takealot_week"})
    assert row["listing_external_id"] == "12345678"
    assert row["listing_marketplace"] == "takealot"


def test_listing_seed_defaults_from_evetech_layout_family():
    row = {"raw_product_token": "EV-9", "listing_external_id": None, "listing_marketplace": None}
    apply_listing_seed_fields(row, {"layout_family": "evetech_sales_report"})
    assert row["listing_external_id"] == "EV-9"
    assert row["listing_marketplace"] == "evetech"


def test_takealot_listing_external_id_strips_spaces():
    row = {
        "raw_product_token": "4711387767535",
        "listing_external_id": "222 547 542",
        "listing_marketplace": "takealot",
    }
    apply_listing_seed_fields(row, {"layout_family": "takealot_week"})
    assert row["listing_external_id"] == "222547542"
