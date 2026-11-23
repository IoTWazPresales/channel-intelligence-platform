"""Structured page facts and the existing identity adapter. No network or database."""

import json
import socket
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.listing_capture.identity import (
    barcode_key,
    corroboration,
    model_key,
)
from app.services.listing_capture.identity import (
    page_facts_from_html as identity_facts,
)
from app.services.listing_capture.web_discovery.gtin import normalize_gtin
from app.services.listing_capture.web_discovery.page_facts import PageFacts, page_facts_from_html

FIXTURES = Path(__file__).parent / "fixtures" / "web_discovery"
URL = "https://shop.example.test/view/item"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _ld(data):
    return '<script type="application/ld+json">' + json.dumps(data) + "</script>"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Page fact extraction must not use the network")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.mark.parametrize(
    ("filename", "gtin", "sku", "mpn", "name", "amount", "currency", "availability", "path"),
    [
        (
            "product_jsonld.html",
            "4006381333931",
            "STOCK-77",
            "WID-100",
            "Widget One",
            "1299.95",
            "USD",
            "https://schema.org/InStock",
            "/products/widget",
        ),
        (
            "product_microdata.html",
            "036000291452",
            "STOCK-88",
            "WID-200",
            "Widget Two",
            "1299.95",
            "EUR",
            "https://schema.org/OutOfStock",
            "/products/widget-two",
        ),
        (
            "product_opengraph.html",
            "96385074",
            "STOCK-99",
            "WID-300",
            "Widget Three",
            "99.50",
            "GBP",
            "in stock",
            "/products/widget-three",
        ),
    ],
)
def test_each_structured_syntax(
    filename,
    gtin,
    sku,
    mpn,
    name,
    amount,
    currency,
    availability,
    path,
):
    facts = page_facts_from_html(_fixture(filename), URL)
    assert isinstance(facts, PageFacts)
    assert facts.gtin == (gtin,)
    assert facts.sku == (sku,)
    assert facts.mpn == (mpn,)
    assert facts.brand == "Example Brand"
    assert facts.name == name
    assert facts.price_amount == Decimal(amount)
    assert facts.price_currency == currency
    assert facts.availability == availability
    assert facts.url == "https://shop.example.test" + path


def test_graph_type_arrays_and_manufacturer_model_are_preserved():
    facts = page_facts_from_html(_fixture("product_jsonld.html"), URL)
    assert facts.model == ("WID 100",)
    assert facts.name != "Shop"
    assert identity_facts(_fixture("product_jsonld.html")) == {
        "barcodes": ["4006381333931"],
        "models": ["WID-100", "WID 100"],
        "stock_codes": ["STOCK-77"],
    }


def test_jsonld_takes_precedence_over_conflicting_opengraph_identifiers():
    html = _fixture("product_jsonld.html") + _fixture("product_opengraph.html")
    facts = page_facts_from_html(html, URL)
    assert facts.gtin == ("4006381333931",)
    assert facts.name == "Widget One"
    assert facts.price_currency == "USD"


def test_arrays_and_multiple_product_claims_are_evidence_not_a_link_decision():
    html = _ld(
        [
            {"@type": "Product", "gtin13": ["4006381333931", "4006381333931"], "mpn": "AB-100"},
            {"@type": "Product", "gtin12": "036000291452", "model": "AB-200"},
        ]
    )
    facts = page_facts_from_html(html, URL)
    assert facts.gtin == ("4006381333931", "036000291452")
    assert facts.mpn == ("AB-100",) and facts.model == ("AB-200",)


@pytest.mark.parametrize(
    "html",
    ["", "<html><body>No facts</body></html>", _ld({"@type": "Organization", "name": "Shop"})],
)
def test_missing_product_metadata_is_empty(html):
    assert page_facts_from_html(html, URL) == PageFacts(url=URL)


def test_broken_jsonld_does_not_prevent_opengraph_extraction():
    html = '<script type="application/ld+json">{bad json</script>'
    facts = page_facts_from_html(html + _fixture("product_opengraph.html"), URL)
    assert facts.gtin == ("96385074",)
    assert facts.price_amount == Decimal("99.50")


def test_untyped_jsonld_and_legacy_raw_json_probe_still_work():
    data = {"gtin13": "4006381333931", "model": "AB-100"}
    assert identity_facts(_ld(data))["models"] == ["AB-100"]
    assert identity_facts("<html><script>" + json.dumps(data) + "</script></html>")["barcodes"] == [
        "4006381333931"
    ]
    raw = json.dumps(data) + '\n"priceCurrency": "USD", "price": 12'
    assert identity_facts(raw)["barcodes"] == ["4006381333931"]


def test_raw_gtin_claim_is_preserved_but_validation_refuses_it():
    # Existing identity keys/corroboration are unchanged in this foundations step.
    facts = page_facts_from_html(_ld({"@type": "Product", "gtin13": "4006381333932"}), URL)
    assert facts.gtin == ("4006381333932",)
    assert normalize_gtin(facts.gtin[0]) is None


def test_sku_never_becomes_a_barcode_or_manufacturer_model():
    html = _ld({"@type": "Product", "sku": ["4006381333931", "AB-100"]})
    facts = identity_facts(html)
    assert facts["barcodes"] == [] and facts["models"] == []
    product = SimpleNamespace(
        ean="4006381333931",
        upc=None,
        part_number="AB-100",
        model_name=None,
        sales_model_name=None,
    )
    assert corroboration(facts, product) is None
    assert barcode_key("0004006381333931") == "4006381333931"
    assert model_key("ab-100") == "AB100"


def test_exact_model_match_and_existing_minimum_length_are_unchanged():
    product = SimpleNamespace(
        ean=None,
        upc=None,
        part_number="AB-100",
        model_name=None,
        sales_model_name=None,
    )
    assert corroboration(identity_facts(_ld({"model": "ab 100"})), product) == "model"
    assert corroboration(identity_facts(_ld({"model": "AB-100X"})), product) is None
    product.part_number = "AB1"
    assert corroboration(identity_facts(_ld({"model": "AB1"})), product) is None


def test_zero_and_unknown_currency_are_not_invented():
    facts = page_facts_from_html(
        _ld(
            {
                "@type": "Product",
                "offers": {"price": 0},
            }
        ),
        URL,
    )
    assert facts.price_amount == Decimal("0")
    assert facts.price_currency is None
    assert facts.url == URL
    absent = page_facts_from_html(
        _ld(
            {
                "@type": "Product",
                "offers": {"price": "not a price", "priceCurrency": "EUR"},
            }
        ),
        URL,
    )
    assert absent.price_amount is None
    assert absent.price_currency == "EUR"


def test_bad_metadata_url_falls_back_to_the_fetched_url():
    facts = page_facts_from_html(_ld({"@type": "Product", "url": "https://["}), URL)
    assert facts.url == URL
    assert (
        page_facts_from_html(_ld({"@type": "Product", "url": "javascript:alert(1)"}), URL).url
        == URL
    )
