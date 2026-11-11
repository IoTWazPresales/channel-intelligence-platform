"""Five product-page shapes on the general HTML reader. No custom reader, no real site names.

Each shape stands in for one site that still uses the general reader. A page that names a
different seller is competition. A page that names no seller keeps the site's own seller.
"""

from __future__ import annotations

from app.services.listing_capture.adapters import configured_adapter, seller_role_label
from app.services.listing_capture.adapters.html_page import parse, quality_fields, seller_from_page
from listing_site_fixtures import html_site, own_seller

CUSTOMER = 41
OWN = "North Counter"


def _site():
    return html_site(first_party=OWN, sellers=[own_seller(CUSTOMER, OWN)])


def _label(page: str) -> str | None:
    site = _site()
    parsed = parse(page, site=site, parser_version="test")
    assert parsed.parse_status == "ok"
    assert len(parsed.offers) == 1
    assert parsed.offers[0]["is_buy_box"] is True
    seller = parsed.offers[0]["seller_name"]
    assert quality_fields(page, site=site)["seller_name"] == seller
    return seller_role_label(site.is_own_seller(CUSTOMER, name=seller))


def test_general_reader_is_the_only_reader_these_shapes_need():
    site = _site()
    module = configured_adapter(site)
    assert module is not None
    assert module.ADAPTER_KEY == "html_page"


def test_currency_then_price_names_a_competing_seller():
    page = (
        '<meta property="og:title" content="Glide 14">'
        '{"@type":"Offer","priceCurrency":"ZAR","price":1299.00,'
        '"seller":{"name":"Harbour Stall"},"availability":"https://schema.org/InStock"}'
    )
    site = _site()
    parsed = parse(page, site=site, parser_version="test")
    assert parsed.parse_status == "ok"
    assert parsed.price == 1299.0
    assert parsed.availability == "in_stock"
    assert parsed.offers[0]["seller_name"] == "Harbour Stall"
    assert seller_from_page(page) == "Harbour Stall"
    assert _label(page) == "Competition"


def test_price_then_currency_matches_the_own_seller_ignoring_case_and_space():
    page = '"seller":{"display_name":"  north   COUNTER "},"price":88.50,"priceCurrency":"ZAR"'
    assert seller_from_page(page) == "north   COUNTER"
    assert _label(page) == "Own"


def test_visible_rand_amount_with_a_string_seller_is_competition():
    page = '<div>Now R 2,450</div><script>{"seller":"Other Stall"}</script>'
    site = _site()
    parsed = parse(page, site=site, parser_version="test")
    assert parsed.price == 2450.0
    assert parsed.flags.get("method") == "html_zar"
    assert parsed.offers[0]["seller_name"] == "Other Stall"
    assert _label(page) == "Competition"


def test_bare_price_with_no_page_seller_stays_the_own_seller():
    page = "<html><title>Shelf</title>899.00</html>"
    assert seller_from_page(page) is None
    site = _site()
    parsed = parse(page, site=site, parser_version="test")
    assert parsed.parse_status == "ok"
    assert parsed.offers[0]["seller_name"] == OWN
    assert quality_fields(page, site=site)["seller_name"] == OWN
    assert _label(page) == "Own"


def test_a_page_with_no_price_fails_on_the_general_reader():
    page = "<html><title>Sold out</title><p>Ask in store</p></html>"
    parsed = parse(page, site=_site(), parser_version="test")
    assert parsed.parse_status == "parse_failed"
    assert parsed.flags.get("reason") == "no_price_found"
    assert not getattr(parsed, "offers", None)


def test_json_escaped_seller_names_are_decoded_before_own_or_competition():
    own_page = '"seller":{"name":"North\\u00a0Counter"},"price":1299.00,"priceCurrency":"ZAR"'
    assert seller_from_page(own_page) == "North\u00a0Counter"
    assert _label(own_page) == "Own"
    other_page = '"seller":"Harbour\\u0020Stall","price":88.50,"priceCurrency":"ZAR"'
    assert seller_from_page(other_page) == "Harbour Stall"
    assert _label(other_page) == "Competition"
