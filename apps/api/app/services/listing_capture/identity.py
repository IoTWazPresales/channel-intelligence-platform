"""Exact identity checks for a product page. A report stock code is never a match.

Barcode: digits only, leading zeros dropped, then equal.
Model: letters and digits uppercased, length at least 4, then equal.
No substring match.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.services.listing_capture.web_discovery.page_facts import (
    embedded_identity,
)
from app.services.listing_capture.web_discovery.page_facts import (
    page_facts_from_html as extract_page_facts,
)

_MIN_MODEL = 4


def digits(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return re.sub(r"\D", "", text)


def barcode_key(raw: Any) -> str:
    return digits(raw).lstrip("0")


def model_key(raw: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())


def barcodes_match(page_values: Iterable[Any], product_values: Iterable[Any]) -> bool:
    want = {barcode_key(v) for v in product_values}
    want.discard("")
    if not want:
        return False
    return any(barcode_key(v) in want for v in page_values)


def models_match(page_values: Iterable[Any], product_values: Iterable[Any]) -> bool:
    want = {model_key(v) for v in product_values}
    want = {k for k in want if len(k) >= _MIN_MODEL}
    if not want:
        return False
    return any(len(model_key(v)) >= _MIN_MODEL and model_key(v) in want for v in page_values)


def product_barcodes(product: Any) -> list[str]:
    return [
        v
        for v in (getattr(product, "ean", None), getattr(product, "upc", None))
        if isinstance(v, str) and v.strip()
    ]


def product_models(product: Any) -> list[str]:
    out = []
    for name in ("part_number", "model_name", "sales_model_name"):
        value = getattr(product, name, None)
        if isinstance(value, str) and len(model_key(value)) >= _MIN_MODEL:
            out.append(value.strip())
    return out


def page_facts_from_html(text: str) -> dict[str, list[str]]:
    """Structured HTML evidence. SKU remains a stock code and never an identity key."""
    facts = extract_page_facts(text)
    barcodes = list(facts.gtin)
    models = list(dict.fromkeys((*facts.mpn, *facts.model)))
    if not barcodes and not models:
        # Script-built pages: identity keys in the page's embedded JSON data.
        embedded = embedded_identity(text)
        barcodes = list(embedded["gtin"])
        models = list(dict.fromkeys((*embedded["mpn"], *embedded["model"])))
    return {
        "barcodes": barcodes,
        "models": models,
        "stock_codes": list(facts.sku),
    }


def page_facts_from_json(data: dict[str, Any]) -> dict[str, list[str]]:
    """Barcodes, models and stock codes read from a product-details document.

    A ``sku`` is a stock code: evidence only, never a barcode or a model.
    """
    barcodes: list[str] = []
    models: list[str] = []
    stock: list[str] = []
    media = data.get("flixmedia") if isinstance(data.get("flixmedia"), dict) else {}
    ean = digits(media.get("ean") if isinstance(media, dict) else None)
    if ean:
        barcodes.append(ean)
    mpn = str(media.get("mpn") or "").strip() if isinstance(media, dict) else ""
    if mpn and digits(mpn) == mpn:
        barcodes.append(mpn)
    elif mpn:
        models.append(mpn)
    info = (
        data.get("product_information") if isinstance(data.get("product_information"), dict) else {}
    )
    for row in (info.get("items") if isinstance(info, dict) else None) or []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("item_type") or "").lower()
        text = str(row.get("displayable_text") or "").strip()
        if not text:
            continue
        if kind == "barcode":
            barcodes.append(text)
        elif kind in {"model_number", "model", "mpn"}:
            models.append(text)
    for item in (
        (data.get("buybox") or {}).get("items") if isinstance(data.get("buybox"), dict) else None
    ) or []:
        if isinstance(item, dict) and item.get("sku"):
            stock.append(str(item.get("sku")))
    return {"barcodes": barcodes, "models": models, "stock_codes": stock}


def corroboration(page: dict[str, Any], product: Any) -> str | None:
    """Return ``barcode`` or ``model`` for exact identity evidence. Stock codes do not count."""
    if barcodes_match(page.get("barcodes") or [], product_barcodes(product)):
        return "barcode"
    if models_match(page.get("models") or [], product_models(product)):
        return "model"
    return None
