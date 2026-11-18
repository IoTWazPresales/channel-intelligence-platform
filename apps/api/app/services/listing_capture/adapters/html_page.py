"""Page reader for sites whose product page is ordinary HTML (JSON-LD offer or a shown price).

Fetches the stored listing URL itself. When the page names a seller and the site's seller
identities were configured (seed or steward, not inferred from a customer name), that name is
the buy-box seller. Otherwise the seller is the site's ``first_party_seller`` (the store's own
stock). A different seller on the customer's own site is competition. A page that lists
several priced offers still needs a reader that keeps each offer.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.services.listing_capture.adapters import SiteConfig
    from app.services.listing_capture.observation import ParseResult

ADAPTER_KEY = "html_page"
REQUIRED_FIELDS: tuple[str, ...] = ()
READS_STORED_URL = True
_HttpGet = Callable[[str], tuple[int, str]]
_JSON_STRING = r'"((?:\\.|[^"\\])*)"'
_SELLER_OBJECT = re.compile(
    rf'"seller"\s*:\s*\{{[^{{}}]*?"(?:name|display_name)"\s*:\s*{_JSON_STRING}',
    flags=re.IGNORECASE,
)
_SELLER_STRING = re.compile(rf'"seller"\s*:\s*{_JSON_STRING}', flags=re.IGNORECASE)


def _decode_json_string(raw: str) -> str | None:
    """Undo JSON string escapes so a match compares the seller the page named."""
    try:
        decoded = json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        decoded = raw
    if not isinstance(decoded, str):
        return None
    name = decoded.strip()
    return name or None


_JSON_LD_BLOCK = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    flags=re.IGNORECASE | re.DOTALL,
)


def _offer_objects(node: Any) -> list[dict[str, Any]]:
    """Every JSON object that carries a price, depth first, in document order."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "price" in node or "lowPrice" in node:
            found.append(node)
        for value in node.values():
            found.extend(_offer_objects(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_offer_objects(item))
    return found


def _seller_name(raw: Any) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("display_name")
    if isinstance(raw, str):
        name = raw.strip()
        return name or None
    return None


def _price_of(offer: dict[str, Any]) -> float | None:
    raw = offer.get("price", offer.get("lowPrice"))
    try:
        return float(str(raw).replace(",", "")) if raw is not None else None
    except ValueError:
        return None


def seller_from_json_ld(text: str, price: float | None = None) -> str | None:
    """The seller of the JSON-LD offer that supplied ``price``.

    JSON-LD blocks are parsed as objects, so a seller object with other properties before
    ``name`` is still read. With a price, only an offer at that price counts; without one,
    only a page with a single seller-bearing offer names a seller. None when unsure.
    """
    return _json_ld_seller(text, price)[0]


def _json_ld_seller(text: str, price: float | None) -> tuple[str | None, bool]:
    """(seller or None, whether any JSON-LD offer names a seller)."""
    offers: list[dict[str, Any]] = []
    for block in _JSON_LD_BLOCK.findall(text or ""):
        try:
            offers.extend(_offer_objects(json.loads(block.strip())))
        except (json.JSONDecodeError, ValueError):
            continue
    named = [(o, _seller_name(o.get("seller"))) for o in offers]
    named = [(o, name) for o, name in named if name]
    if not named:
        return None, False
    if price is not None:
        at_price = {name for o, name in named if _price_of(o) == float(price)}
        return (next(iter(at_price)) if len(at_price) == 1 else None), True
    sellers = {name for _o, name in named}
    return (next(iter(sellers)) if len(sellers) == 1 else None), True


def seller_from_page(text: str, price: float | None = None) -> str | None:
    """The seller the page itself names, or None when it names none.

    The JSON-LD offer that supplied the price wins. When the page's JSON-LD offers name
    sellers but none can be tied to the price, the answer is None: the first ``"seller"`` key
    would be one of those same offers, a guess. Only a page whose JSON-LD names no seller
    falls back to the first ``"seller"`` key (embedded JSON that is not JSON-LD).
    """
    return page_seller(text, price)[0]


def page_seller(text: str, price: float | None = None) -> tuple[str | None, bool]:
    """(seller the page names or None, whether the page names any seller at all).

    ``(None, True)`` means the page names sellers but none can be tied to the price: the
    seller is unknown, and it must not be replaced by the site's own seller.
    """
    if not text:
        return None, False
    from_offer, json_ld_names_sellers = _json_ld_seller(text, price)
    if json_ld_names_sellers:
        return from_offer, True
    match = _SELLER_OBJECT.search(text) or _SELLER_STRING.search(text)
    if not match:
        return None, False
    return _decode_json_string(match.group(1)), True


def seller_or_first_party(text: str, price: float | None, first_party: str | None) -> str | None:
    """The page-named seller; the site's own seller only when the page names no seller.

    A page whose offers name sellers that cannot be tied to the price gives None (unknown),
    never the own seller (Codex review of PR #104, B1).
    """
    named, names_sellers = page_seller(text, price)
    if names_sellers:
        return named
    return (first_party or "").strip() or None


def buy_box_seller_info(text: str, site: SiteConfig, price: float | None = None) -> tuple[str | None, bool]:
    """(buy-box seller, unknown).

    The page-named seller when every seller identity on the site was configured (seed or
    steward); otherwise, as before, the site's ``first_party_seller``. ``unknown`` is True
    when the site is configured and the page names sellers but none can be tied to the
    price: the seller is then None and nothing downstream may fill in the own seller.

    An identity discovery inferred from a customer name is not compared with a page-named
    seller: a differently written own name would read as Competition. Callers pass
    ``site.for_customer(customer_id)``, so the rule applies to the reading customer only.
    """
    sellers = tuple(site.sellers or ())
    configured = bool(sellers) and not any(getattr(s, "inferred", False) for s in sellers)
    own = (site.first_party_seller or "").strip() or None
    if not configured:
        return own, False
    named, names_sellers = page_seller(text, price)
    if names_sellers:
        return named, named is None
    return own, False


def buy_box_seller(text: str, site: SiteConfig, price: float | None = None) -> str | None:
    return buy_box_seller_info(text, site, price)[0]


def request_headers(site: "SiteConfig") -> dict[str, str]:
    return {}


def fetch(
    site: "SiteConfig",
    *,
    url: str,
    http_get: _HttpGet,
    external_id: str | None = None,
    ean: str | None = None,
    known_page_id: str | None = None,
    models: list[str] | None = None,
) -> tuple[int, str, dict[str, Any]]:
    del models
    status, body = http_get(url)
    return status, body, {}


def parse(
    body: str,
    *,
    site: "SiteConfig",
    preferred_sku: str | None = None,
    parser_version: str,
) -> "ParseResult":
    from app.services.listing_capture.observation import parse_snapshot_text

    parsed = parse_snapshot_text(body, marketplace=site.site_key, parser_version=parser_version)
    if parsed.parse_status == "ok":
        seller_name, seller_unknown = buy_box_seller_info(body, site, parsed.price)
        parsed.offers = [
            {
                "seller_name": seller_name,
                "seller_unknown": seller_unknown,
                "seller_id": None,
                "price": parsed.price,
                "availability": parsed.availability,
                "is_buy_box": True,
                "offer_ref": None,
                "condition": None,
            }
        ]
    return parsed


def link_dead(fetch_flags: dict[str, Any], status: int) -> bool:
    return status in (404, 410)


def verified_url(site: "SiteConfig", fetch_flags: dict[str, Any], parse_flags: dict[str, Any]) -> str | None:
    return None


def _embedded_field(text: str, key: str) -> str | None:
    match = re.search(rf'\\?"{key}\\?"\s*:\s*\\?"(.*?)\\?"', text)
    if not match:
        return None
    return match.group(1).encode("utf-8").decode("unicode_escape", errors="replace")


def quality_fields(text: str, *, site: "SiteConfig") -> dict[str, Any]:
    title = ""
    og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', text, flags=re.I)
    if og:
        title = unescape(og.group(1))
    image_urls = set(re.findall(r"https?:\\?/\\?/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)", text, flags=re.I))
    review_raw = _embedded_field(text, "reviewCount") or _embedded_field(text, "ratingCount")
    seller = buy_box_seller(text, site) or ""
    return {
        "title": title,
        "brand": _embedded_field(text, "brand") or "",
        "image_count": len(image_urls) if image_urls else None,
        "description_html": _embedded_field(text, "description"),
        "spec_text": text,
        "spec_names": None,
        "review_count": int(review_raw) if review_raw and review_raw.isdigit() else None,
        "seller_name": seller or None,
        "seller_id": None,
        "seller_known": bool(seller),
        "price": None,
        "availability": None,
    }
