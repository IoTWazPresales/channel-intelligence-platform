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


# Codex review of PR #104 (B1): two external offers at the parsed price must not become Own.
_TWO_AT_ONE_PRICE = (
    '<script type="application/ld+json">{"@type":"Product","offers":['
    '{"@type":"Offer","price":"1999.00","seller":{"@type":"Organization","name":"Trader A"}},'
    '{"@type":"Offer","price":"1999.00","seller":{"@type":"Organization","name":"Trader B"}}'
    "]}</script>"
)


def _configured_site():
    return SimpleNamespace(sellers=(SimpleNamespace(inferred=False),), first_party_seller="Own Store")


def test_an_ambiguous_page_seller_is_unknown_not_own():
    from app.services.listing_capture.adapters.html_page import (
        buy_box_seller,
        buy_box_seller_info,
        seller_or_first_party,
    )

    site = _configured_site()
    assert buy_box_seller_info(_TWO_AT_ONE_PRICE, site, 1999.0) == (None, True)
    assert buy_box_seller(_TWO_AT_ONE_PRICE, site, 1999.0) is None
    assert buy_box_seller_info(_TWO_AT_ONE_PRICE, site, 2499.0) == (None, True)
    # Discovery uses the same rule.
    assert seller_or_first_party(_TWO_AT_ONE_PRICE, 1999.0, "Own Store") is None
    # A page that names no seller still reads as the site's own seller.
    assert buy_box_seller_info("<html>no seller</html>", site, 1999.0) == ("Own Store", False)
    assert seller_or_first_party("<html>no seller</html>", 1999.0, "Own Store") == "Own Store"
    # A clear seller is kept.
    assert buy_box_seller_info(_LD, site, 1999.0) == ("Trader B", False)
    # Not configured (inferred identity): unchanged, the own seller.
    inferred = SimpleNamespace(sellers=(SimpleNamespace(inferred=True),), first_party_seller="Own Store")
    assert buy_box_seller_info(_TWO_AT_ONE_PRICE, inferred, 1999.0) == ("Own Store", False)


def test_the_writer_does_not_fill_in_the_own_seller_for_an_unknown_seller():
    from app.services.listing_capture.registry import _attach_offers

    site = SimpleNamespace(first_party_seller="Own Store", tenant_id="t")
    unknown = [{"seller_name": None, "seller_unknown": True, "price": 1999, "is_buy_box": True}]
    _attach_offers(None, SimpleNamespace(id=None), SimpleNamespace(customer_id=1), site, _parsed(None, offers=unknown), None)
    assert unknown[0]["seller_name"] is None
    plain = [{"seller_name": None, "price": 1999, "is_buy_box": True}]
    _attach_offers(None, SimpleNamespace(id=None), SimpleNamespace(customer_id=1), site, _parsed(None, offers=plain), None)
    assert plain[0]["seller_name"] == "Own Store"


def test_an_unknown_seller_after_a_named_one_is_a_change():
    unknown = [{"seller_name": None, "seller_unknown": True, "price": 1999, "is_buy_box": True}]
    assert extraction_unchanged(_prev(), parsed=_parsed(None, offers=unknown), parser_version="v") is False
    assert (
        extraction_unchanged(_prev(buy_box_seller=None), parsed=_parsed(None, offers=unknown), parser_version="v")
        is True
    )


def test_an_unknown_seller_keeps_unknown_ownership_through_persistence():
    """Codex review of PR #104, round 2 (B1): stored ownership and the API label stay unknown."""
    from app.services.listing_capture.adapters import SiteConfig, SiteSeller
    from app.services.listing_capture.registry import _attach_offers, observation_to_dict

    site = SiteConfig(
        site_key="shop-a",
        display_name="Shop A",
        first_party_seller="Own Store",
        tenant_id="t",
        sellers=(SiteSeller(customer_id=1, names=("Own Store",)),),
    )

    class _Session:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

    def run(offer):
        from app.models.listing_capture import ListingObservation
        from app.models.listing_offer import ListingOffer

        session = _Session()
        obs = ListingObservation(id=1, listing_id=5, parser_version="v", parse_status="ok")
        _attach_offers(session, obs, SimpleNamespace(id=5, customer_id=1), site, _parsed(None, offers=[offer]), None)
        stored = [row for row in session.added if isinstance(row, ListingOffer)]
        return stored[0], obs

    offer, obs = run({"seller_name": None, "seller_unknown": True, "price": 1999, "is_buy_box": True})
    assert offer.is_own_seller is None
    assert obs.buy_box_own is None
    assert observation_to_dict(obs)["buy_box_label"] not in ("Competition", "Own")
    # Control: a named outside seller is still Competition, the own seller still Own.
    offer, obs = run({"seller_name": "Other Trader", "price": 1999, "is_buy_box": True})
    assert offer.is_own_seller is False and obs.buy_box_own is False
    assert observation_to_dict(obs)["buy_box_label"] == "Competition"
    offer, obs = run({"seller_name": "Own Store", "price": 1999, "is_buy_box": True})
    assert obs.buy_box_own is True


def test_a_same_amount_offer_in_another_currency_is_not_the_priced_offer():
    """Codex review of PR #104, round 3 (B3): the parsed price is in the reader's currency, so
    an equal amount in another currency must not make the seller ambiguous."""
    from app.services.listing_capture.observation import PARSED_PRICE_CURRENCY

    other = "USD" if PARSED_PRICE_CURRENCY.upper() != "USD" else "EUR"
    page = (
        '<script type="application/ld+json">{"@type":"Product","offers":['
        '{"@type":"Offer","priceCurrency":"%s","price":"1999.00","seller":{"@type":"Organization","name":"Seller A"}},'
        '{"@type":"Offer","priceCurrency":"%s","price":"1999.00","seller":{"@type":"Organization","name":"Seller B"}}'
        "]}</script>" % (PARSED_PRICE_CURRENCY, other)
    )
    assert seller_from_json_ld(page, 1999.0) == "Seller A"
    assert seller_from_page(page, 1999.0) == "Seller A"
    # An offer without a currency is still a candidate, so the answer stays unknown.
    no_currency = page.replace('"priceCurrency":"%s",' % other, "")
    assert seller_from_json_ld(no_currency, 1999.0) is None
