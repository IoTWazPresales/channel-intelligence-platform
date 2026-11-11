"""Page reader for sites whose product page is ordinary HTML (JSON-LD offer or a shown price).

Fetches the stored listing URL itself. When the page names a seller, that name is the buy-box
seller. Otherwise the seller is the site's ``first_party_seller`` (the store's own stock).
A different seller on the customer's own site is competition. A page that lists several priced
offers still needs a reader that keeps each offer.
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


def seller_from_page(text: str) -> str | None:
    """The seller the page itself names, or None when it names none."""
    if not text:
        return None
    match = _SELLER_OBJECT.search(text) or _SELLER_STRING.search(text)
    if not match:
        return None
    return _decode_json_string(match.group(1))


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
        named = seller_from_page(body)
        seller_name = named if named else (site.first_party_seller or None)
        parsed.offers = [
            {
                "seller_name": seller_name,
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
    seller = seller_from_page(text) or (site.first_party_seller or "").strip()
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
