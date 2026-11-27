"""Structured page evidence, extracted locally with extruct and price-parser.

JSON-LD, microdata and OpenGraph are considered in that order. Identifier tuples
retain raw evidence, including invalid GTIN claims: callers doing catalogue
resolution must validate GTINs with gtin.normalize_gtin and check uniqueness.
SKU is always separate from manufacturer model/part evidence.

No context URL, page URL or other remote resource is fetched. Only extruct's
non-network syntaxes are enabled. Missing or malformed markup yields empty facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin, urlsplit

import extruct
from extruct.utils import parse_html
from price_parser import Price

_GTIN_KEYS = ("gtin", "gtin8", "gtin12", "gtin13", "gtin14")
_IDENTITY_KEYS = (*_GTIN_KEYS, "sku", "mpn", "model")


@dataclass(frozen=True)
class PageFacts:
    gtin: tuple[str, ...] = ()
    sku: tuple[str, ...] = ()
    mpn: tuple[str, ...] = ()
    model: tuple[str, ...] = ()
    brand: str | None = None
    name: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    availability: str | None = None
    url: str = ""


def _nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            if key != "@context":
                yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, list):
        for item in value:
            yield from _texts(item)
    elif isinstance(value, dict):
        props = _properties(value)
        for key in ("@value", "value", "name", "@id"):
            if key in props:
                yield from _texts(props[key])
                break
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            yield text


def _properties(node: dict[str, Any]) -> dict[str, Any]:
    props = node.get("properties")
    return props if isinstance(props, dict) else node


def _values(nodes: list[dict[str, Any]], *keys: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(text for node in nodes for key in keys for text in _texts(node.get(key)))
    )


def _first(node: dict[str, Any], *keys: str) -> str | None:
    return next(iter(_values([node], *keys)), None)


def _products(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for node in _nodes(data):
        types = tuple(_texts(node.get("@type", node.get("type"))))
        product = any(
            kind.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1] == "Product" for kind in types
        )
        props = _properties(node)
        # Untyped identity documents are supported by the existing HTML reader.
        untyped = not types and any(key in props for key in _IDENTITY_KEYS)
        if (product or untyped) and id(props) not in seen:
            seen.add(id(props))
            found.append(props)
    return found


def _legacy_document(html: str) -> str:
    """Adapt the HTML reader's historical raw-JSON probe input, without regex extraction."""
    text = html.lstrip()
    if text.startswith("{"):
        try:
            value, _end = json.JSONDecoder().raw_decode(text)
        except ValueError:
            return html
        if isinstance(value, dict) and any(key in value for key in _IDENTITY_KEYS):
            payload = json.dumps(value).replace("<", r"\u003c")
            return f'<script type="application/ld+json">{payload}</script>'
    return html


def _document(html: str) -> Any:
    """Prepare legacy JSON-only scripts using extruct's own HTML parser."""
    source = _legacy_document(html)
    if not source.strip():
        return source
    try:
        tree = parse_html(source, encoding="UTF-8")
    except Exception:
        # Let extruct's errors="ignore" handle unparseable markup.
        return source
    for script in tree.xpath("//script[not(@type)]"):
        try:
            value = json.loads(script.text or "")
        except ValueError:
            continue
        if isinstance(value, dict) and any(key in value for key in _IDENTITY_KEYS):
            script.set("type", "application/ld+json")
    return tree


def _opengraph(data: Any) -> dict[str, Any]:
    props: dict[str, list[str]] = {}
    for item in data or []:
        for key, value in item.get("properties", []):
            props.setdefault(key, []).append(value)
    # Keep the metadata vocabulary explicit; no site-specific selectors.
    mapping = {
        "gtin": (
            "product:gtin",
            "product:gtin8",
            "product:gtin12",
            "product:gtin13",
            "product:gtin14",
        ),
        "sku": ("product:sku", "product:retailer_item_id"),
        "mpn": ("product:mpn",),
        "model": ("product:model",),
        "brand": ("product:brand",),
        "name": ("og:title",),
        "price": ("product:price:amount", "og:price:amount"),
        "priceCurrency": ("product:price:currency", "og:price:currency"),
        "availability": ("product:availability",),
        "url": ("og:url",),
    }
    return {
        field: [value for key in keys for value in props.get(key, [])]
        for field, keys in mapping.items()
    }


def _offer(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers")
    for offer in offers if isinstance(offers, list) else [offers]:
        if isinstance(offer, dict):
            return _properties(offer)
    return product


def _price(offer: dict[str, Any], locale: str | None = None) -> tuple[Decimal | None, str | None]:
    raw = _first(offer, "price")
    currency = _first(offer, "priceCurrency")
    if locale:
        # The tenant saved this tag. A parse failure is no price, not a second guess.
        from babel.core import UnknownLocaleError
        from babel.numbers import NumberFormatError, parse_decimal

        try:
            amount = parse_decimal(str(raw or ""), locale=locale)
        except (NumberFormatError, UnknownLocaleError, ValueError):
            amount = None
        if amount is not None and (not amount.is_finite() or amount < 0):
            amount = None
        return amount, currency.upper() if isinstance(currency, str) and currency else None
    parsed = Price.fromstring(raw or "")
    amount = parsed.amount
    if amount is not None and (not amount.is_finite() or amount < 0):
        amount = None
    # A symbol remains a symbol; never infer a tenant country or ISO currency.
    return amount, currency.upper() if currency else parsed.currency


def _url(value: str | None, fallback: str) -> str:
    try:
        target = urljoin(fallback, value) if value else fallback
        return target if urlsplit(target).scheme in {"http", "https"} else fallback
    except ValueError:
        return fallback


def page_facts_from_html(html: str, url: str = "", *, locale: str | None = None) -> PageFacts:
    """Return structured evidence from HTML and its fetched URL; no I/O or writes.

    Identity claims from multiple Product nodes are retained as evidence, never
    a catalogue decision. Descriptive/offer fields come from the first product;
    lower-priority syntaxes are used only when no product was found.
    """
    extracted = extruct.extract(
        _document(html or ""),
        base_url=url or None,
        syntaxes=["json-ld", "microdata", "opengraph"],
        errors="ignore",
    )
    products = _products(extracted.get("json-ld", []))
    if not products:
        products = _products(extracted.get("microdata", []))
    if not products:
        products = [_opengraph(extracted.get("opengraph", []))]
    product = products[0]
    offer = _offer(product)
    amount, currency = _price(offer, locale)
    return PageFacts(
        gtin=_values(products, *_GTIN_KEYS),
        sku=_values(products, "sku"),
        mpn=_values(products, "mpn"),
        model=_values(products, "model"),
        brand=_first(product, "brand"),
        name=_first(product, "name"),
        price_amount=amount,
        price_currency=currency,
        availability=_first(offer, "availability"),
        url=_url(_first(product, "url"), url),
    )


_EMBEDDED_SCRIPT = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']application/json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_EMBEDDED_KEYS = {
    "gtin": "gtin",
    "gtin8": "gtin",
    "gtin12": "gtin",
    "gtin13": "gtin",
    "gtin14": "gtin",
    "ean": "gtin",
    "mpn": "mpn",
    "manufacturerpartnumber": "mpn",
    "model": "model",
}
MAX_EMBEDDED_BYTES = 2 * 1024 * 1024


def embedded_identity(html: str) -> dict[str, tuple[str, ...]]:
    """Identity keys in JSON data embedded in the page (script-built sites).

    Walks every ``<script type="application/json">`` block (this includes framework page
    data such as ``__NEXT_DATA__``) for the keys ``gtin*``, ``ean``, ``mpn``,
    ``manufacturerPartNumber`` and ``model``. Values are evidence only; several products'
    keys on one page make the linking decision ambiguous, never a guess.
    """
    found: dict[str, list[str]] = {"gtin": [], "mpn": [], "model": []}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                kind = _EMBEDDED_KEYS.get(str(key).replace("_", "").lower())
                if kind and isinstance(child, (str, int)) and not isinstance(child, bool):
                    text = str(child).strip()
                    if text and len(text) <= 64:
                        found[kind].append(text)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for raw in _EMBEDDED_SCRIPT.findall(html or ""):
        if len(raw) > MAX_EMBEDDED_BYTES:
            continue
        try:
            walk(json.loads(raw))
        except ValueError:
            continue
    return {kind: tuple(dict.fromkeys(values)) for kind, values in found.items()}
