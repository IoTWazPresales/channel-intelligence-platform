"""Takealot live fetch — REST product-details, not the Next.js SPA shell.

Column mapping (locked)
-----------------------
- ``extracted_price`` ← ``buybox.items[].price`` (storefront selling price, ZAR).
  Never ``listing_price`` (that's the struck-through RRP).
- Prefer the buybox item whose ``sku`` equals the CST/report ``external_id``.
  Takealot WEEK "Product ID" is a SKU, not a PLID.
- Else the ``is_selected`` item, else the first item.
- ``extracted_availability`` ← ``is_add_to_cart_available`` / stock status.
- PLID comes from the URL (``/PLID\\d+``) or, on 404, exact EAN search
  (one result, then barcode/SKU corroboration). No title fuzzy match. No Google.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.listing_capture.observation import ParseResult

TAKEALOT_REST_VERSION = "v-1-16-0"
TAKEALOT_API_ORIGIN = "https://api.takealot.com"
_PLID_IN_URL_RE = re.compile(r"(?:PLID|plid)(\d{5,12})")
_HttpGet = Callable[[str], tuple[int, str]]


def normalize_barcode(raw: str | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"\D", "", s)


def extract_plid(url: str | None, *, external_id: str | None = None) -> str | None:
    """PLID from a canonical PDP URL only — never treat a report SKU as a PLID."""
    if url:
        m = _PLID_IN_URL_RE.search(url)
        if m:
            return m.group(1)
    # Only if the token itself is already PLID-prefixed (steward pasted a real PLID).
    if external_id:
        m = _PLID_IN_URL_RE.fullmatch(str(external_id).strip())
        if m:
            return m.group(1)
    return None


def product_details_url(plid: str) -> str:
    digits = re.sub(r"\D", "", str(plid))
    return (
        f"{TAKEALOT_API_ORIGIN}/rest/{TAKEALOT_REST_VERSION}"
        f"/product-details/PLID{digits}?platform=desktop"
    )


def ean_search_url(ean: str) -> str:
    return (
        f"{TAKEALOT_API_ORIGIN}/rest/{TAKEALOT_REST_VERSION}"
        f"/searches/products?qsearch={ean}"
    )


def _selected_buybox_item(data: dict[str, Any], *, preferred_sku: str | None) -> dict[str, Any] | None:
    items = ((data.get("buybox") or {}).get("items")) or []
    if not isinstance(items, list) or not items:
        return None
    want = re.sub(r"\D", "", str(preferred_sku or ""))
    if want:
        for item in items:
            if not isinstance(item, dict):
                continue
            sku = re.sub(r"\D", "", str(item.get("sku") or ""))
            if sku and sku == want:
                return item
    for item in items:
        if isinstance(item, dict) and item.get("is_selected"):
            return item
    first = items[0]
    return first if isinstance(first, dict) else None


def _barcode_from_details(data: dict[str, Any]) -> str:
    flix = data.get("flixmedia") if isinstance(data.get("flixmedia"), dict) else {}
    for key in ("ean", "mpn"):
        got = normalize_barcode(flix.get(key) if isinstance(flix, dict) else None)
        if got:
            return got
    info = data.get("product_information") if isinstance(data.get("product_information"), dict) else {}
    for row in info.get("items") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("item_type") or "").lower() == "barcode":
            return normalize_barcode(str(row.get("displayable_text") or ""))
    return ""


def parse_takealot_product_json(
    data: dict[str, Any],
    *,
    preferred_sku: str | None = None,
    parser_version: str,
    marketplace: str = "takealot",
) -> "_ParseResult":
    from app.services.listing_capture.observation import ParseResult as _ParseResult

    flags: dict[str, Any] = {
        "parser_version": parser_version,
        "marketplace": marketplace,
        "method": "takealot_rest_buybox",
        "vat_basis": "inc_vat",
        "api_version": TAKEALOT_REST_VERSION,
    }
    item = _selected_buybox_item(data, preferred_sku=preferred_sku)
    if item is None:
        return _ParseResult(parse_status="parse_failed", flags={**flags, "reason": "no_buybox_item"})
    price_raw = item.get("price")
    try:
        price_val = float(price_raw) if price_raw is not None else None
    except (TypeError, ValueError):
        price_val = None
    if price_val is None or price_val < 1:
        return _ParseResult(parse_status="parse_failed", flags={**flags, "reason": "no_sell_price"})

    in_cart = bool(item.get("is_add_to_cart_available"))
    stock = ((item.get("stock_availability") or {}) if isinstance(item.get("stock_availability"), dict) else {})
    status_text = str(stock.get("status") or "")
    if in_cart or "in stock" in status_text.lower():
        availability = "in_stock"
    else:
        availability = "out_of_stock"

    badges = (data.get("badges") or {}).get("items") if isinstance(data.get("badges"), dict) else None
    promo = None
    if isinstance(badges, list):
        for badge in badges:
            if isinstance(badge, dict) and str(badge.get("type") or "") == "saving":
                promo = str(badge.get("value") or "") or None
                break

    href = data.get("desktop_href") or ((data.get("seo") or {}).get("canonical") if isinstance(data.get("seo"), dict) else None)
    flags.update(
        {
            "plid": ((data.get("buybox") or {}).get("plid") if isinstance(data.get("buybox"), dict) else None),
            "tsin": ((data.get("buybox") or {}).get("tsin") if isinstance(data.get("buybox"), dict) else None),
            "sku": item.get("sku"),
            "rrp_listing_price": item.get("listing_price"),
            "canonical_url": href,
            "sku_matched": bool(
                preferred_sku
                and re.sub(r"\D", "", str(item.get("sku") or ""))
                == re.sub(r"\D", "", str(preferred_sku))
            ),
        }
    )
    return _ParseResult(
        parse_status="ok",
        price=price_val,
        availability=availability,
        promo_badge=promo,
        flags=flags,
    )


def _parse_json_body(body: str) -> dict[str, Any] | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _plid_from_search(data: dict[str, Any]) -> str | None:
    results = ((data.get("sections") or {}).get("products") or {}).get("results") or []
    if not isinstance(results, list) or len(results) != 1:
        return None
    core = ((results[0] or {}).get("product_views") or {}).get("core") or {}
    plid = core.get("id")
    if plid is None:
        return None
    digits = re.sub(r"\D", "", str(plid))
    return digits or None


def fetch_takealot_listing(
    *,
    url: str,
    http_get: _HttpGet,
    external_id: str | None = None,
    ean: str | None = None,
    known_plid: str | None = None,
) -> tuple[int, str, dict[str, Any]]:
    """Return (http_status, body, fetch_flags). Caller parses body."""
    flags: dict[str, Any] = {"fetch": "takealot_rest"}
    plid = (known_plid or "").strip() or extract_plid(url, external_id=external_id)
    status, body = 0, ""

    def _get_details(plid_digits: str) -> tuple[int, str, dict[str, Any] | None]:
        status, body = http_get(product_details_url(plid_digits))
        return status, body, _parse_json_body(body)

    if plid:
        status, body, data = _get_details(plid)
        if status == 200 and data and isinstance(data.get("buybox"), dict):
            flags["plid_source"] = "url_or_known"
            flags["resolved_plid"] = plid
            return status, body, flags

    barcode = normalize_barcode(ean)
    if not barcode:
        return (
            status if plid else 0,
            body if plid else "",
            {**flags, "reason": "plid_not_found", "ean_resolve": "skipped_no_ean"},
        )

    search_status, search_body = http_get(ean_search_url(barcode))
    search_data = _parse_json_body(search_body)
    resolved = _plid_from_search(search_data) if search_data else None
    if not resolved:
        n = 0
        if search_data:
            results = ((search_data.get("sections") or {}).get("products") or {}).get("results") or []
            n = len(results) if isinstance(results, list) else 0
        return (
            search_status,
            search_body,
            {**flags, "reason": "ean_not_unique_or_missing", "ean_result_count": n},
        )

    status, body, data = _get_details(resolved)
    flags["plid_source"] = "ean_search"
    flags["resolved_plid"] = resolved
    flags["ean"] = barcode
    if status != 200 or not data:
        return status, body, {**flags, "reason": "ean_details_failed"}

    found_barcode = _barcode_from_details(data)
    sku_digits = ""
    item = _selected_buybox_item(data, preferred_sku=external_id)
    if item:
        sku_digits = re.sub(r"\D", "", str(item.get("sku") or ""))
    ext_digits = re.sub(r"\D", "", str(external_id or ""))
    barcode_ok = bool(found_barcode) and found_barcode == barcode
    sku_ok = bool(ext_digits) and sku_digits == ext_digits
    if not barcode_ok and not sku_ok:
        return (
            status,
            body,
            {**flags, "reason": "ean_hit_not_corroborated", "details_barcode": found_barcode},
        )
    flags["corroboration"] = "barcode" if barcode_ok else "sku"
    return status, body, flags
