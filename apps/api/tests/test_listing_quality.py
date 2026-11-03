"""Listing quality checks from stored snapshot text. No fetch. Fictional sites and sellers."""

import json

from app.services.listing_capture.quality import evaluate_quality
from tests.listing_site_fixtures import html_site, own_seller, rest_site, unconfigured_site

CUSTOMER = 41
OWN_REST = rest_site(sellers=[own_seller(CUSTOMER, "Market B Retail")])
PRODUCT = {"model_name": "Glide 14"}


def _details(**overrides):
    data = {
        "core": {"title": "Northwind Glide 14", "brand": "Northwind"},
        "gallery": {"images": ["a", "b", "c", "d", "e", "f"]},
        "description": {"html": " ".join(["word"] * 150)},
        "product_information": {
            "items": [
                {"display_name": "CPU"},
                {"display_name": "RAM"},
                {"display_name": "Storage"},
                {"display_name": "Screen size"},
                {"display_name": "Operating system"},
            ]
        },
        "reviews": {"count": 4},
        "buybox": {"items": [{"price": 19999, "is_add_to_cart_available": True, "stock_availability": {"status": "In stock"}}]},
    }
    data.update(overrides)
    return data


def test_rest_reader_pass_and_other_seller_flag():
    passed = evaluate_quality(json.dumps(_details()), site=OWN_REST, customer_id=CUSTOMER, product=PRODUCT)
    # No seller on the page: the site's own stock (first_party_seller), which is the customer's seller.
    assert passed["checks"]["buy_box"] == {"status": "pass", "evidence": "Market B Retail"}
    assert passed["checks"]["images"]["status"] == "pass"
    assert passed["flag_count"] == 0

    flagged = evaluate_quality(
        json.dumps(_details(seller_detail={"display_name": "Gadget Hub"})),
        site=OWN_REST,
        customer_id=CUSTOMER,
        product=PRODUCT,
    )
    assert flagged["checks"]["buy_box"]["status"] == "flag"
    assert flagged["checks"]["buy_box"]["evidence"] == "Gadget Hub, not Market B Retail"


def test_own_seller_match_is_exact_not_substring_and_ids_match():
    site = rest_site(sellers=[own_seller(CUSTOMER, "Market B", ids=("S-77",))])
    near = evaluate_quality(
        json.dumps(_details(seller_detail={"display_name": "Market B Retail"})),
        site=site,
        customer_id=CUSTOMER,
        product=PRODUCT,
    )
    assert near["checks"]["buy_box"]["status"] == "flag"
    spaced = evaluate_quality(
        json.dumps(_details(seller_detail={"display_name": "  market   b "})),
        site=site,
        customer_id=CUSTOMER,
        product=PRODUCT,
    )
    assert spaced["checks"]["buy_box"]["status"] == "pass"
    by_id = evaluate_quality(
        json.dumps(_details(seller_detail={"display_name": "Renamed", "seller_id": "S-77"})),
        site=site,
        customer_id=CUSTOMER,
        product=PRODUCT,
    )
    assert by_id["checks"]["buy_box"]["status"] == "pass"


def test_buy_box_is_no_data_until_the_customers_seller_is_configured():
    other_customer = evaluate_quality(json.dumps(_details()), site=OWN_REST, customer_id=99, product=PRODUCT)
    assert other_customer["checks"]["buy_box"]["status"] == "no_data"
    assert "not configured" in other_customer["checks"]["buy_box"]["evidence"]
    assert other_customer["flag_count"] == 0


def test_missing_snapshot_is_no_data_not_a_flag():
    result = evaluate_quality("", site=OWN_REST, customer_id=CUSTOMER, parse_status="parse_failed")
    assert result["flag_count"] == 0
    assert all(row["status"] == "no_data" for row in result["checks"].values())


def test_short_description_and_few_images_flag():
    data = _details()
    data["gallery"] = {"images": ["only-one"]}
    data["description"] = {"html": "too short"}
    data["reviews"] = {"count": 0}
    result = evaluate_quality(json.dumps(data), site=OWN_REST, customer_id=CUSTOMER, product=PRODUCT)
    assert result["checks"]["images"]["status"] == "flag"
    assert result["checks"]["description"]["status"] == "flag"
    assert result["checks"]["reviews"]["status"] == "flag"
    assert "0 reviews" in result["checks"]["reviews"]["evidence"]


def test_html_reader_uses_the_sites_first_party_seller():
    page = (
        '<meta property="og:title" content="Northwind Glide 14 laptop">'
        '{"brand":"Northwind","reviewCount":"3","description":"short"}'
        "cpu ram storage screen windows"
    )
    site = html_site(first_party="Shop A", sellers=[own_seller(CUSTOMER, "Shop A")])
    result = evaluate_quality(page, site=site, customer_id=CUSTOMER, product=PRODUCT, price=999.0, availability="in_stock")
    assert result["checks"]["buy_box"] == {"status": "pass", "evidence": "Shop A"}
    assert result["checks"]["title"]["status"] == "pass"
    assert result["checks"]["key_specs"]["status"] == "pass"
    assert result["checks"]["reviews"]["status"] == "pass"

    no_seller = evaluate_quality(page, site=html_site(first_party=None, sellers=[own_seller(CUSTOMER, "Shop A")]), customer_id=CUSTOMER)
    assert no_seller["checks"]["buy_box"]["status"] == "no_data"


def test_site_without_a_reader_is_not_checked():
    result = evaluate_quality("<html>price</html>", site=unconfigured_site())
    assert result["flag_count"] == 0
    assert result["search_position"] == "deferred"
    assert result["marketplace"] == "shop-c"
    assert all(row["status"] == "no_data" for row in result["checks"].values())
    unknown = evaluate_quality("<html>price</html>", site=None, marketplace="shop-z")
    assert unknown["marketplace"] == "shop-z"
    assert all(row["status"] == "no_data" for row in unknown["checks"].values())
