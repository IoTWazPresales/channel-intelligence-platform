"""BACKLOG-226 (2026-11-18): seller-only changes and the offer's own seller. No DB."""

from types import SimpleNamespace

from app.services.listing_capture.adapters.html_page import seller_from_json_ld, seller_from_page
from app.services.listing_capture.observation import ParseResult
from app.services.listing_capture.registry import extraction_unchanged


def _prev(**kw):
    base = {
        "parser_version": "v",
        "extracted_price": 1999,
        "extracted_availability": "in_stock",
        "extracted_promo_badge": None,
        "parse_flags": {"method": "json_ld_price"},
        "buy_box_seller": "Own Store",
        "offer_count": 1,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _parsed(seller, *, offers=None):
    return ParseResult(
        parse_status="ok",
        price=1999,
        availability="in_stock",
        flags={"method": "json_ld_price"},
        offers=offers
        if offers is not None
        else [{"seller_name": seller, "price": 1999, "is_buy_box": True}],
    )


def test_same_page_is_still_unchanged():
    assert extraction_unchanged(_prev(), parsed=_parsed("Own Store"), parser_version="v") is True


def test_seller_only_change_is_a_change():
    assert (
        extraction_unchanged(_prev(), parsed=_parsed("Other Trader"), parser_version="v") is False
    )


def test_an_unnamed_seller_does_not_force_a_snapshot():
    # The writer fills the site's own seller in when the reader names none.
    assert extraction_unchanged(_prev(), parsed=_parsed(None), parser_version="v") is True
    assert (
        extraction_unchanged(_prev(), parsed=_parsed(None, offers=[]), parser_version="v") is True
    )


def test_a_new_offer_is_a_change():
    offers = [
        {"seller_name": "Own Store", "price": 1999, "is_buy_box": True},
        {"seller_name": "Other Trader", "price": 2099, "is_buy_box": False},
    ]
    assert (
        extraction_unchanged(
            _prev(), parsed=_parsed("Own Store", offers=offers), parser_version="v"
        )
        is False
    )
    assert (
        extraction_unchanged(
            _prev(offer_count=None), parsed=_parsed("Own Store", offers=offers), parser_version="v"
        )
        is True
    )


_LD = (
    '<script type="application/ld+json">{"@type":"Product","offers":['
    '{"@type":"Offer","price":"2499.00","priceCurrency":"ZAR",'
    '"seller":{"@type":"Organization","url":"https://example.test/a","name":"Trader A"}},'
    '{"@type":"Offer","price":"1999.00","priceCurrency":"ZAR",'
    '"seller":{"@type":"Organization","address":{"name":"Not this"},"name":"Trader B"}}'
    "]}</script>"
)


def test_the_seller_is_the_one_on_the_priced_offer():
    assert seller_from_json_ld(_LD, 1999.0) == "Trader B"
    assert seller_from_json_ld(_LD, 2499.0) == "Trader A"
    assert seller_from_page(_LD, 1999.0) == "Trader B"


def test_no_guess_when_the_offer_is_ambiguous():
    assert seller_from_json_ld(_LD) is None
    assert seller_from_json_ld(_LD, 1234.0) is None
    # The page reader must not fall back to the first "seller" key: that is one of the
    # same ambiguous offers (the first-match defect, BACKLOG-226 item 4).
    assert seller_from_page(_LD) is None
    assert seller_from_page(_LD, 1234.0) is None
    with_embedded = _LD + '<div>{"seller": {"name": "Embedded Seller"}}</div>'
    assert seller_from_page(with_embedded, 1234.0) is None
    assert seller_from_page(with_embedded, 1999.0) == "Trader B"


def test_a_single_offer_names_its_seller_without_a_price():
    one = (
        '<script type="application/ld+json">{"@type":"Offer","price":1999,'
        '"seller":{"@type":"Organization","identifier":"x","name":"Trader C"}}</script>'
    )
    assert seller_from_json_ld(one) == "Trader C"


def test_pages_without_json_ld_keep_the_old_reader():
    page = '<div>{"seller": {"name": "Embedded Seller"}}</div>'
    assert seller_from_page(page) == "Embedded Seller"
    assert seller_from_page(page, 1999.0) == "Embedded Seller"
    broken = '<script type="application/ld+json">{not json</script>{"seller":"Fallback"}'
    assert seller_from_page(broken, 1999.0) == "Fallback"
