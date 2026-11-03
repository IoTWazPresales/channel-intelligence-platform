"""Page reader for sites that publish a product-details JSON document with a buy box.

Every URL comes from the site's data (``details_url_pattern``, ``search_url_pattern``,
``product_url_pattern``, ``page_id_pattern``); nothing here names a site.

Column mapping (locked)
-----------------------
- ``extracted_price`` ← the buy-box item's ``price`` (storefront selling price, incl. VAT).
  The buy box is the ``is_selected`` item, else the first item.
  Never ``listing_price`` (the struck-through RRP). A report stock code does not choose the price.
- Every buy-box item and every ``other_offers`` item is kept. One of them is the buy box.
- ``extracted_availability`` ← ``is_add_to_cart_available`` / stock status.
- The page id comes from a known page id, the stored URL (``page_id_pattern``) or, when the
  details call fails, an exact barcode search (one result, then barcode/SKU corroboration).
  No title fuzzy match.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote, urlsplit

if TYPE_CHECKING:
    from app.services.listing_capture.adapters import SiteConfig
    from app.services.listing_capture.observation import ParseResult

ADAPTER_KEY = "rest_buybox_json"
METHOD = "rest_buybox"
REQUIRED_FIELDS: tuple[str, ...] = ("details_url_pattern", "page_id_pattern", "product_url_pattern")
READS_STORED_URL = False
_HttpGet = Callable[[str], tuple[int, str]]


def normalize_barcode(raw: str | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"\D", "", s)


def page_id_from_url(site: "SiteConfig", url: str | None) -> str | None:
    """Page id read from a product URL with the site's ``page_id_pattern`` (first group)."""
    if not url or not site.page_id_pattern:
        return None
    try:
        match = re.search(site.page_id_pattern, url)
    except re.error:
        return None
    if not match:
        return None
    value = match.group(1) if match.groups() else match.group(0)
    return (value or "").strip() or None


def details_url(site: "SiteConfig", page_id: str) -> str:
    return (site.details_url_pattern or "").replace("{page_id}", quote(str(page_id), safe=""))


def search_url(site: "SiteConfig", query: str) -> str:
    return (site.search_url_pattern or "").replace("{query}", quote(str(query), safe=""))


def product_url(
    site: "SiteConfig",
    page_id: str,
    *,
    slug: str | None = None,
    canonical_url: str | None = None,
) -> str | None:
    """Product page link for a page id: the page's canonical link when it carries the same page id
    on the same host as ``product_url_pattern``, else the pattern filled in."""
    pattern = site.product_url_pattern or ""
    pid = str(page_id or "").strip()
    if not pattern or not pid:
        return None
    canon = (canonical_url or "").strip()
    if canon:
        want_host = urlsplit(pattern).netloc.lower()
        if urlsplit(canon).netloc.lower() == want_host and page_id_from_url(site, canon) == pid:
            return canon
    if "{slug}" in pattern:
        slug_text = re.sub(r"[^a-z0-9]+", "-", str(slug or "").lower()).strip("-")
        if not slug_text:
            return None
        pattern = pattern.replace("{slug}", slug_text)
    return pattern.replace("{page_id}", quote(pid, safe=""))


def request_headers(site: "SiteConfig") -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if site.product_url_pattern:
        parts = urlsplit(site.product_url_pattern)
        if parts.scheme and parts.netloc:
            headers["Referer"] = f"{parts.scheme}://{parts.netloc}/"
    return headers


def buy_box_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """The offer the shopper sees: the selected buy-box item, else the first item."""
    items = ((data.get("buybox") or {}).get("items")) or []
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("is_selected"):
            return item
    for item in items:
        if isinstance(item, dict):
            return item
    return None


def selected_buybox_item(data: dict[str, Any], *, preferred_sku: str | None) -> dict[str, Any] | None:
    """Kept for callers that still ask. The shopper's price uses ``buy_box_item``."""
    del preferred_sku
    return buy_box_item(data)


def _offer_row(
    item: dict[str, Any],
    *,
    is_buy_box: bool,
    condition: str | None,
    seller_name: str,
    seller_id: str,
) -> dict[str, Any]:
    try:
        price = float(item.get("price")) if item.get("price") is not None else None
    except (TypeError, ValueError):
        price = None
    stock = item.get("stock_availability") if isinstance(item.get("stock_availability"), dict) else {}
    in_cart = bool(item.get("is_add_to_cart_available")) or bool(stock.get("is_in_stock"))
    status_text = str(stock.get("status") or "")
    availability = "in_stock" if in_cart or "in stock" in status_text.lower() else "out_of_stock" if stock else None
    ref = item.get("id") or item.get("product_id")
    return {
        "seller_name": seller_name or None,
        "seller_id": seller_id or None,
        "price": price,
        "availability": availability,
        "is_buy_box": is_buy_box,
        "offer_ref": str(ref) if ref is not None else None,
        "condition": condition,
    }


def collect_offers(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every offer on the document. Exactly one is the buy box when a buy box exists."""
    seller_detail = data.get("seller_detail") if isinstance(data.get("seller_detail"), dict) else {}
    top_name = str(seller_detail.get("display_name") or "").strip()
    top_id = str(seller_detail.get("seller_id") or "").strip()
    buy = buy_box_item(data)
    items = ((data.get("buybox") or {}).get("items")) or []
    offers: list[dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            embedded = item.get("seller") if isinstance(item.get("seller"), dict) else {}
            name = str(embedded.get("display_name") or "").strip()
            sid = str(embedded.get("seller_id") or "").strip()
            if item is buy:
                name = name or top_name
                sid = sid or top_id
            offers.append(_offer_row(item, is_buy_box=item is buy, condition="buy_box", seller_name=name, seller_id=sid))
    other = data.get("other_offers") if isinstance(data.get("other_offers"), dict) else {}
    for cond in other.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        label = str(cond.get("condition") or cond.get("name") or "other")
        for item in cond.get("items") or []:
            if not isinstance(item, dict):
                continue
            embedded = item.get("seller") if isinstance(item.get("seller"), dict) else {}
            offers.append(
                _offer_row(
                    item,
                    is_buy_box=False,
                    condition=label,
                    seller_name=str(embedded.get("display_name") or "").strip(),
                    seller_id=str(embedded.get("seller_id") or "").strip(),
                )
            )
    return offers


def barcode_from_details(data: dict[str, Any]) -> str:
    media = data.get("flixmedia") if isinstance(data.get("flixmedia"), dict) else {}
    for key in ("ean", "mpn"):
        got = normalize_barcode(media.get(key) if isinstance(media, dict) else None)
        if got:
            return got
    info = data.get("product_information") if isinstance(data.get("product_information"), dict) else {}
    for row in info.get("items") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("item_type") or "").lower() == "barcode":
            return normalize_barcode(str(row.get("displayable_text") or ""))
    return ""


def parse_json(
    data: dict[str, Any],
    *,
    site_key: str,
    preferred_sku: str | None = None,
    parser_version: str,
) -> "ParseResult":
    from app.services.listing_capture.observation import ParseResult

    buybox = data.get("buybox") if isinstance(data.get("buybox"), dict) else {}
    flags: dict[str, Any] = {
        "parser_version": parser_version,
        "marketplace": site_key,
        "method": METHOD,
        "vat_basis": "inc_vat",
    }
    offers = collect_offers(data)
    item = buy_box_item(data)
    if item is None:
        return ParseResult(parse_status="parse_failed", flags={**flags, "reason": "no_buybox_item"})
    price_raw = item.get("price")
    try:
        price_val = float(price_raw) if price_raw is not None else None
    except (TypeError, ValueError):
        price_val = None
    if price_val is None or price_val < 1:
        return ParseResult(parse_status="parse_failed", flags={**flags, "reason": "no_sell_price"})

    in_cart = bool(item.get("is_add_to_cart_available"))
    stock = item.get("stock_availability") if isinstance(item.get("stock_availability"), dict) else {}
    status_text = str(stock.get("status") or "")
    availability = "in_stock" if in_cart or "in stock" in status_text.lower() else "out_of_stock"

    badges = (data.get("badges") or {}).get("items") if isinstance(data.get("badges"), dict) else None
    promo = None
    if isinstance(badges, list):
        for badge in badges:
            if isinstance(badge, dict) and str(badge.get("type") or "") == "saving":
                promo = str(badge.get("value") or "") or None
                break

    seo = data.get("seo") if isinstance(data.get("seo"), dict) else {}
    href = data.get("desktop_href") or seo.get("canonical")
    page_id = buybox.get("plid")
    flags.update(
        {
            "page_id": str(page_id) if page_id is not None else None,
            "variant_id": buybox.get("tsin"),
            "sku": item.get("sku"),
            "rrp_listing_price": item.get("listing_price"),
            "canonical_url": href,
            "sku_matched": bool(
                preferred_sku
                and re.sub(r"\D", "", str(item.get("sku") or "")) == re.sub(r"\D", "", str(preferred_sku))
            ),
        }
    )
    return ParseResult(
        parse_status="ok",
        price=price_val,
        availability=availability,
        promo_badge=promo,
        flags=flags,
        offers=offers,
    )


def parse_body(body: str) -> dict[str, Any] | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse(
    body: str,
    *,
    site: "SiteConfig",
    preferred_sku: str | None = None,
    parser_version: str,
) -> "ParseResult":
    from app.services.listing_capture.observation import ParseResult

    if not (body or "").strip():
        return ParseResult(
            parse_status="parse_failed",
            flags={"parser_version": parser_version, "marketplace": site.site_key, "reason": "empty_snapshot"},
        )
    data = parse_body(body)
    if data is None or not isinstance(data.get("buybox"), dict):
        return ParseResult(
            parse_status="parse_failed",
            flags={"parser_version": parser_version, "marketplace": site.site_key, "reason": "not_product_details"},
        )
    return parse_json(data, site_key=site.site_key, preferred_sku=preferred_sku, parser_version=parser_version)


def verified_url(site: "SiteConfig", fetch_flags: dict[str, Any], parse_flags: dict[str, Any]) -> str | None:
    page_id = fetch_flags.get("resolved_page_id")
    if not page_id:
        return None
    canon = parse_flags.get("canonical_url")
    return product_url(site, str(page_id), canonical_url=str(canon) if canon else None)


def quality_fields(text: str, *, site: "SiteConfig") -> dict[str, Any]:
    data = parse_body(text)
    if data is None or "core" not in data:
        return {"unreadable": "Snapshot is not product details data"}
    core = data.get("core") if isinstance(data.get("core"), dict) else {}
    gallery = data.get("gallery") if isinstance(data.get("gallery"), dict) else {}
    images = gallery.get("images") if isinstance(gallery.get("images"), list) else None
    info = data.get("product_information") if isinstance(data.get("product_information"), dict) else None
    spec_items = info.get("items") if isinstance(info, dict) and isinstance(info.get("items"), list) else None
    description = data.get("description") if isinstance(data.get("description"), dict) else {}
    reviews = data.get("reviews") if isinstance(data.get("reviews"), dict) else None
    seller = data.get("seller_detail") if isinstance(data.get("seller_detail"), dict) else None
    item = selected_buybox_item(data, preferred_sku=None)
    price = None
    availability = None
    if item is not None:
        try:
            price = float(item.get("price")) if item.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
        stock = item.get("stock_availability") if isinstance(item.get("stock_availability"), dict) else {}
        if item.get("is_add_to_cart_available") or "in stock" in str(stock.get("status") or "").lower():
            availability = "in_stock"
        elif stock:
            availability = "out_of_stock"
    review_count = None
    if isinstance(reviews, dict) and reviews.get("count") is not None:
        try:
            review_count = int(reviews.get("count"))
        except (TypeError, ValueError):
            review_count = None
    seller_name = str(seller.get("display_name") or "").strip() if seller else ""
    seller_id = str(seller.get("seller_id") or "").strip() if seller else ""
    if not seller_name:
        seller_name = (site.first_party_seller or "").strip()
    return {
        "title": str(core.get("title") or ""),
        "brand": str(core.get("brand") or ""),
        "image_count": len(images) if images is not None else None,
        "description_html": description.get("html") if isinstance(description, dict) else None,
        "spec_text": None,
        "spec_names": [str(r.get("display_name") or "") for r in spec_items if isinstance(r, dict)]
        if spec_items is not None
        else None,
        "review_count": review_count,
        "seller_name": seller_name or None,
        "seller_id": seller_id or None,
        "seller_known": bool(seller_name or seller_id),
        "price": price,
        "availability": availability,
    }


def search_hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    """``[{page_id, slug, title}]`` from a search document (``sections.products.results``)."""
    results = ((data.get("sections") or {}).get("products") or {}).get("results") or []
    if not isinstance(results, list):
        return []
    out: list[dict[str, Any]] = []
    for row in results:
        core = ((row or {}).get("product_views") or {}).get("core") or {}
        page_id = re.sub(r"\D", "", str(core.get("id") or ""))
        if not page_id:
            continue
        out.append({"page_id": page_id, "slug": core.get("slug"), "title": core.get("title")})
    return out


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
    """Return (http_status, body, fetch_flags). Caller parses body.

    A search hit is accepted only when the page's barcode or model equals the product's.
    ``external_id`` is the report stock code: it is recorded and never used to accept a page.
    """
    flags: dict[str, Any] = {"fetch": METHOD}
    if not site.details_url_pattern:
        return 0, "", {**flags, "reason": "site_not_configured", "missing": ["details_url_pattern"]}
    page_id = (known_page_id or "").strip() or page_id_from_url(site, url)
    status, body = 0, ""

    def _get_details(pid: str) -> tuple[int, str, dict[str, Any] | None]:
        got_status, got_body = http_get(details_url(site, pid))
        return got_status, got_body, parse_body(got_body)

    if page_id:
        status, body, data = _get_details(page_id)
        # Status of the details call for the stored page id; the dead-link rule reads this
        # even when the returned status is the barcode search's.
        flags["details_status"] = status
        if status == 200 and data and isinstance(data.get("buybox"), dict):
            flags["page_id_source"] = "url_or_known"
            flags["resolved_page_id"] = page_id
            return status, body, flags

    from app.services.listing_capture.identity import barcodes_match, model_key, models_match, page_facts_from_json

    if external_id:
        flags["stock_code"] = str(external_id)
    barcode = normalize_barcode(ean)
    queries: list[tuple[str, str]] = []
    if barcode and site.search_url_pattern:
        queries.append(("barcode", barcode))
    for model in models or []:
        if site.search_url_pattern and len(model_key(model)) >= 4:
            queries.append(("model", str(model).strip()))
    if not queries:
        skipped = "skipped_no_search" if barcode and not site.search_url_pattern else "skipped_no_barcode"
        return (
            status if page_id else 0,
            body if page_id else "",
            {**flags, "reason": "page_id_not_found", "barcode_resolve": skipped},
        )

    search_status, search_body = status, body
    for kind, query in queries:
        search_status, search_body = http_get(search_url(site, query))
        search_data = parse_body(search_body)
        hits = search_hits(search_data) if search_data else []
        if len(hits) > 1:
            return (
                search_status,
                search_body,
                {**flags, "reason": "barcode_not_unique_or_missing", "barcode_result_count": len(hits), "candidates": hits[:8]},
            )
        if len(hits) != 1:
            continue
        resolved = hits[0]["page_id"]
        status, body, data = _get_details(resolved)
        flags["page_id_source"] = "barcode_search" if kind == "barcode" else "model_search"
        flags["resolved_page_id"] = resolved
        if status != 200 or not data:
            return status, body, {**flags, "reason": "barcode_details_failed"}
        facts = page_facts_from_json(data)
        flags["page_facts"] = {k: facts[k] for k in ("barcodes", "models", "stock_codes")}
        if kind == "barcode" and barcodes_match(facts["barcodes"], [barcode]):
            flags["corroboration"] = "barcode"
            flags["barcode"] = barcode
            return status, body, flags
        if kind == "model" and models_match(facts["models"], [query]):
            flags["corroboration"] = "model"
            return status, body, flags
        return (
            status,
            body,
            {**flags, "reason": "barcode_hit_not_corroborated", "details_barcode": (facts["barcodes"] or [""])[0]},
        )
    return (
        search_status,
        search_body,
        {
            **flags,
            "reason": "barcode_not_unique_or_missing",
            "barcode_result_count": 0,
            "candidates": [],
        },
    )


def link_dead(fetch_flags: dict[str, Any], status: int) -> bool:
    """Dead: the details call for the stored page id 404'd and barcode recovery failed, or a resolved id 404s."""
    unresolved = fetch_flags.get("reason") in {"page_id_not_found", "barcode_not_unique_or_missing"}
    return (fetch_flags.get("details_status") in (404, 410) and unresolved) or (
        status in (404, 410) and bool(fetch_flags.get("page_id_source"))
    )
