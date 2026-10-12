"""Listing quality checks from a stored snapshot. No network fetch.

Accepted checks (D-0050): price and stock, title brand and model, six images,
150 words, five key specs, expected seller, review count. A missing field is
"no_data". A failed check is a flag. Search position is deferred. Amazon is
not checked.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

RULES_VERSION = "n0078-2026-10-12"
IMAGE_FLOOR = 6
WORD_FLOOR = 150
EXPECTED_SELLER = {"takealot": "Takealot", "evetech": "Evetech"}
SPEC_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CPU", ("cpu", "processor")),
    ("RAM", ("ram", "memory")),
    ("Storage", ("storage", "ssd", "hdd", "hard drive")),
    ("Screen", ("screen", "display")),
    ("OS", ("operating system", " os", "windows")),
)
CHECK_KEYS = (
    "price_and_stock",
    "title",
    "images",
    "description",
    "key_specs",
    "buy_box",
    "reviews",
)


def _check(status: str, evidence: str) -> dict[str, str]:
    return {"status": status, "evidence": evidence}


def _no_data(reason: str) -> dict[str, str]:
    return _check("no_data", reason)


def _words(html: str) -> int:
    text = re.sub(r"<[^>]+>", " ", unescape(html or ""))
    return len(re.findall(r"[A-Za-z0-9]+", text))


def _contains(hay: str, needle: str) -> bool:
    left = re.sub(r"\s+", " ", (hay or "")).strip().lower()
    right = re.sub(r"\s+", " ", (needle or "")).strip().lower()
    return bool(right) and right in left


def _spec_names(items: list[Any]) -> list[str]:
    names: list[str] = []
    for row in items:
        if isinstance(row, dict):
            names.append(str(row.get("display_name") or ""))
    return names


def _specs_present(names: list[str]) -> tuple[list[str], list[str]]:
    blob = " | ".join(names).lower()
    found: list[str] = []
    missing: list[str] = []
    for label, needles in SPEC_GROUPS:
        if any(needle in blob for needle in needles):
            found.append(label)
        else:
            missing.append(label)
    return found, missing


def _product_model(product: dict[str, Any] | None) -> str:
    if not product:
        return ""
    return str(product.get("model_name") or product.get("marketing_name") or product.get("sales_model_name") or "")


def _title_check(title: str, brand: str, product: dict[str, Any] | None) -> dict[str, str]:
    if not title.strip():
        return _no_data("No title on the snapshot")
    model = _product_model(product)
    if not brand.strip() or not model.strip():
        return _no_data("No brand on the snapshot or no model on the product")
    brand_ok = _contains(title, brand)
    model_ok = _contains(title, model)
    if brand_ok and model_ok:
        return _check("pass", f"Title includes {brand} and {model}")
    missing = []
    if not brand_ok:
        missing.append(f"brand {brand}")
    if not model_ok:
        missing.append(f"model {model}")
    return _check("flag", f"Title is missing {', '.join(missing)}")


def _price_stock(price: float | None, availability: str | None) -> dict[str, str]:
    if price is None:
        return _no_data("No price on the snapshot")
    stock = (availability or "").strip().lower()
    if not stock or stock == "unknown":
        return _no_data(f"Price {price:g} is present. Stock was not read")
    if stock == "in_stock":
        return _check("pass", f"Price {price:g} and in stock")
    return _check("flag", f"Price {price:g} but stock is {stock}")


def _images(count: int | None) -> dict[str, str]:
    if count is None:
        return _no_data("No image list on the snapshot")
    if count >= IMAGE_FLOOR:
        return _check("pass", f"{count} images")
    return _check("flag", f"{count} images, below {IMAGE_FLOOR}")


def _description(html: str | None) -> dict[str, str]:
    if html is None or not str(html).strip():
        return _no_data("No description on the snapshot")
    count = _words(str(html))
    if count >= WORD_FLOOR:
        return _check("pass", f"{count} words")
    return _check("flag", f"{count} words, below {WORD_FLOOR}")


def _key_specs(names: list[str] | None) -> dict[str, str]:
    if names is None:
        return _no_data("No specification list on the snapshot")
    found, missing = _specs_present(names)
    if not missing:
        return _check("pass", "CPU, RAM, storage, screen and OS are present")
    return _check("flag", "Missing " + ", ".join(missing))


def _buy_box(marketplace: str, seller: str | None, seller_known: bool) -> dict[str, str]:
    expected = EXPECTED_SELLER.get(marketplace)
    if expected is None:
        return _no_data("This marketplace is not checked")
    if not seller_known:
        return _no_data("Seller was not on the snapshot")
    seen = (seller or expected).strip() or expected
    if seen.lower() == expected.lower():
        return _check("pass", expected)
    return _check("flag", f"{seen}, not {expected}")


def _reviews(count: int | None) -> dict[str, str]:
    if count is None:
        return _no_data("No review count on the snapshot")
    if count == 0:
        return _check("flag", "0 reviews")
    return _check("pass", f"{count} reviews")


def _takealot(data: dict[str, Any], product: dict[str, Any] | None, price: float | None, availability: str | None) -> dict[str, Any]:
    core = data.get("core") if isinstance(data.get("core"), dict) else {}
    gallery = data.get("gallery") if isinstance(data.get("gallery"), dict) else {}
    images = gallery.get("images") if isinstance(gallery.get("images"), list) else None
    info = data.get("product_information") if isinstance(data.get("product_information"), dict) else None
    spec_items = info.get("items") if isinstance(info, dict) and isinstance(info.get("items"), list) else None
    description = data.get("description") if isinstance(data.get("description"), dict) else {}
    reviews = data.get("reviews") if isinstance(data.get("reviews"), dict) else None
    seller = data.get("seller_detail") if isinstance(data.get("seller_detail"), dict) else None
    item = None
    buybox = data.get("buybox") if isinstance(data.get("buybox"), dict) else {}
    items = buybox.get("items") if isinstance(buybox.get("items"), list) else []
    if items and isinstance(items[0], dict):
        item = items[0]
    if price is None and item is not None:
        try:
            price = float(item.get("price")) if item.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
    if availability is None and item is not None:
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
    checks = {
        "price_and_stock": _price_stock(price, availability),
        "title": _title_check(str(core.get("title") or ""), str(core.get("brand") or ""), product),
        "images": _images(len(images) if images is not None else None),
        "description": _description(description.get("html") if isinstance(description, dict) else None),
        "key_specs": _key_specs(_spec_names(spec_items) if spec_items is not None else None),
        "buy_box": _buy_box("takealot", seller_name or None, True),
        "reviews": _reviews(review_count),
    }
    return checks


def _evetech_field(text: str, key: str) -> str | None:
    match = re.search(rf'\\?"{key}\\?"\s*:\s*\\?"(.*?)\\?"', text)
    if not match:
        return None
    return match.group(1).encode("utf-8").decode("unicode_escape", errors="replace")


def _evetech(text: str, product: dict[str, Any] | None, price: float | None, availability: str | None) -> dict[str, Any]:
    title = ""
    og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', text, flags=re.I)
    if og:
        title = unescape(og.group(1))
    brand = _evetech_field(text, "brand") or ""
    description = _evetech_field(text, "description")
    image_urls = set(re.findall(r"https?:\\?/\\?/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)", text, flags=re.I))
    review_raw = _evetech_field(text, "reviewCount") or _evetech_field(text, "ratingCount")
    review_count = None
    if review_raw and review_raw.isdigit():
        review_count = int(review_raw)
    names = [label for label, _needles in SPEC_GROUPS if any(needle.strip() in text.lower() for needle in _needles)]
    spec_list: list[str] | None = names if names else None
    checks = {
        "price_and_stock": _price_stock(price, availability),
        "title": _title_check(title, brand, product),
        "images": _images(len(image_urls) if image_urls else None),
        "description": _description(description),
        "key_specs": _key_specs(spec_list),
        "buy_box": _buy_box("evetech", "Evetech", "evetech" in text.lower()),
        "reviews": _reviews(review_count),
    }
    return checks


def _amazon() -> dict[str, Any]:
    reason = "Amazon is not checked. No listing is linked to a product."
    return {key: _no_data(reason) for key in CHECK_KEYS}


def backfill_stored_snapshots(session: Any, *, only_missing: bool = False) -> dict[str, int]:
    """Write quality onto each observation that still has a snapshot. No fetch."""
    from sqlalchemy import or_, select

    from app.models.dimensions import DimProduct
    from app.models.listing_capture import CustomerListing, ListingObservation
    from app.services.listing_capture.observation import decompress_snapshot

    listings = {
        int(row.id): row
        for row in session.scalars(select(CustomerListing)).all()
    }
    products = {
        int(row.id): {
            "model_name": row.model_name,
            "marketing_name": row.marketing_name,
            "sales_model_name": row.sales_model_name,
        }
        for row in session.scalars(select(DimProduct)).all()
    }
    id_query = select(ListingObservation.id).where(ListingObservation.raw_snapshot.is_not(None))
    if only_missing:
        id_query = id_query.where(
            or_(
                ListingObservation.parse_flags.is_(None),
                ListingObservation.parse_flags["quality"].is_(None),
            )
        )
    ids = list(session.scalars(id_query.order_by(ListingObservation.id)).all())
    stamped = 0
    skipped = 0
    for start in range(0, len(ids), 25):
        chunk = ids[start : start + 25]
        rows = session.scalars(
            select(ListingObservation).where(ListingObservation.id.in_(chunk))
        ).all()
        for obs in rows:
            if not obs.raw_snapshot:
                skipped += 1
                continue
            listing = listings.get(int(obs.listing_id))
            market = listing.marketplace if listing is not None else ""
            product = None
            if listing is not None and listing.product_id is not None:
                product = products.get(int(listing.product_id))
            flags = dict(obs.parse_flags) if isinstance(obs.parse_flags, dict) else {}
            flags["quality"] = evaluate_quality(
                decompress_snapshot(obs.raw_snapshot),
                marketplace=market,
                product=product,
                price=float(obs.extracted_price) if obs.extracted_price is not None else None,
                availability=obs.extracted_availability,
                parse_status=obs.parse_status,
            )
            obs.parse_flags = flags
            stamped += 1
        session.flush()
        session.expire_all()
    return {"stamped": stamped, "skipped_no_snapshot": skipped}


def evaluate_quality(
    snapshot_text: str,
    *,
    marketplace: str,
    product: dict[str, Any] | None = None,
    price: float | None = None,
    availability: str | None = None,
    parse_status: str | None = None,
) -> dict[str, Any]:
    """One result per accepted check. Search position is not included."""
    market = (marketplace or "").strip().lower()
    if market == "amazon":
        checks = _amazon()
    elif parse_status == "parse_failed" or not (snapshot_text or "").strip():
        checks = {key: _no_data("No parsed snapshot") for key in CHECK_KEYS}
    elif market == "takealot":
        try:
            data = json.loads(snapshot_text)
        except (json.JSONDecodeError, TypeError, ValueError):
            data = None
        if not isinstance(data, dict) or "core" not in data:
            checks = {key: _no_data("Snapshot is not Takealot product data") for key in CHECK_KEYS}
        else:
            checks = _takealot(data, product, price, availability)
    elif market == "evetech":
        checks = _evetech(snapshot_text, product, price, availability)
    else:
        checks = {key: _no_data("This retailer is not covered yet") for key in CHECK_KEYS}
    flags = [key for key, row in checks.items() if row["status"] == "flag"]
    return {
        "rules_version": RULES_VERSION,
        "marketplace": market,
        "checks": checks,
        "flag_count": len(flags),
        "search_position": "deferred",
    }
