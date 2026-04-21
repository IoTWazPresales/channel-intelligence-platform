"""Deterministic Product Master aliases: universal concepts before fuzzy heuristics.

Industry-generic header phrases and conservative value checks only — no vendor-specific SKUs.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.imports.pm_field_catalog import PM_CANONICAL_GENERIC
from app.services.imports.pm_value_patterns import (
    best_barcode_kind_from_samples,
    looks_like_calendar_date_or_datetime,
)

# Slightly below exact canonical header match (92) so true exact keys still win;
# well above fuzzy pattern/sample stacks so obvious columns auto-map reliably.
_SCORE_DETERMINISTIC_HEADER = 93.5
_SCORE_DETERMINISTIC_HEADER_WEAK = 87.0
_SCORE_DETERMINISTIC_VALUE = 86.0

_REASON_DET_HEADER = "deterministic_alias_header"
_REASON_DET_VALUE = "deterministic_value_evidence"

_STRONG_TECH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_./]{3,39}$")


def _norm_tokens(nh: str) -> list[str]:
    return [t for t in nh.split("_") if t]


def _has_segment(nh: str, *segments: str) -> bool:
    """Whole-segment match on normalized underscore header (not mid-token)."""
    toks = set(_norm_tokens(nh))
    for s in segments:
        if s in toks:
            return True
    return False


def _any_phrase(nh: str, phrases: tuple[str, ...]) -> bool:
    return any(p in nh for p in phrases)


def _looks_technical_id(token: str) -> bool:
    if not token or len(token) < 4:
        return False
    d = re.sub(r"\D", "", token)
    if len(d) >= 11 and len(d) <= 14 and re.fullmatch(r"\d+", d):
        return False
    if looks_like_calendar_date_or_datetime(token):
        return False
    if _STRONG_TECH_ID.match(token.strip()):
        return True
    return False


def _samples_list(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    out: list[str] = []
    for x in (meta.get("sample") or [])[:8]:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def deterministic_alias_scores(
    nh: str,
    meta: dict[str, Any] | None,
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Return score/reason maps for deterministic matches (merge as first layer)."""
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def set_if_stronger(tgt: str, sc: float, rs: list[str]) -> None:
        if tgt not in PM_CANONICAL_GENERIC:
            return
        if sc > scores.get(tgt, 0.0):
            scores[tgt] = sc
            reasons[tgt] = rs

    samples = _samples_list(meta)

    # --- Barcodes: strong header semantics, then strict digit evidence only ---
    header_ean = _any_phrase(
        nh,
        (
            "ean",
            "ean_code",
            "gtin",
            "gtin13",
            "gtin_13",
            "gtin14",
            "barcode_ean",
            "european_article",
            "article_number",
        ),
    ) and "upc" not in nh
    header_upc = _any_phrase(nh, ("upc", "upc_code", "barcode_upc", "gtin12", "gtin_12")) and not _any_phrase(
        nh, ("ean", "gtin13", "gtin_13")
    )

    strict_kind, strict_tags = best_barcode_kind_from_samples(samples)
    # Optional: single sample confirms barcode shape when header is generically "code"
    generic_code_header = nh in ("code", "product_code", "vendor_code") or _has_segment(nh, "barcode")

    if header_ean:
        set_if_stronger("barcode_ean", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])
    elif header_upc:
        set_if_stronger("barcode_upc", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])
    elif strict_kind == "barcode_ean" and (
        generic_code_header
        or _any_phrase(nh, ("barcode", "article", "retail", "scan", "upc", "ean"))
        or nh.endswith("_ean")
    ):
        set_if_stronger(
            "barcode_ean",
            _SCORE_DETERMINISTIC_VALUE,
            [_REASON_DET_VALUE] + (strict_tags or ["barcode_like_value"]),
        )
    elif strict_kind == "barcode_upc" and (
        generic_code_header
        or _any_phrase(nh, ("barcode", "retail", "scan"))
        or nh.endswith("_upc")
    ):
        set_if_stronger(
            "barcode_upc",
            _SCORE_DETERMINISTIC_VALUE,
            [_REASON_DET_VALUE] + (strict_tags or ["barcode_like_value"]),
        )

    # --- Technical / manufacturer identifier ---
    tech_header = (
        nh in ("mpn", "technical_product_id", "part_number", "part_no", "product_code")
        or _has_segment(nh, "mpn")
        or _any_phrase(
            nh,
            (
                "manufacturer_part",
                "mfg_part",
                "technical_id",
                "tech_id",
                "engineering_code",
                "factory_part",
                "factory_id",
                "article_id",
            ),
        )
        or nh.endswith("_part_number")
        or nh.endswith("_part_no")
    )
    commerce_noise = _any_phrase(nh, ("commercial_sku", "market_sku", "sales_model", "disti_sku", "channel_sku"))
    if tech_header and not commerce_noise and not header_ean and not header_upc:
        if scores.get("barcode_ean") or scores.get("barcode_upc"):
            pass
        else:
            set_if_stronger(
                "technical_product_id",
                _SCORE_DETERMINISTIC_HEADER,
                [_REASON_DET_HEADER],
            )
    elif (
        _has_segment(nh, "item", "product")
        and _has_segment(nh, "id", "code", "number")
        and not commerce_noise
        and not header_ean
        and not header_upc
        and not _any_phrase(nh, ("order", "cart", "customer", "transaction", "invoice", "gtin", "ean", "upc"))
    ):
        if samples and any(_looks_technical_id(s.split()[0]) for s in samples if s):
            set_if_stronger(
                "technical_product_id",
                _SCORE_DETERMINISTIC_HEADER_WEAK,
                [_REASON_DET_HEADER, _REASON_DET_VALUE, "technical_id_like_value"],
            )
        elif not samples:
            set_if_stronger(
                "technical_product_id",
                _SCORE_DETERMINISTIC_HEADER_WEAK - 4.0,
                [_REASON_DET_HEADER],
            )

    # --- Commercial / market SKU ---
    if _any_phrase(
        nh,
        (
            "market_sku",
            "commercial_sku",
            "sales_model_name",
            "sales_model",
            "commercial_model",
            "disti_sku",
            "channel_sku",
            "retail_sku",
            "customer_sku",
            "distributor_sku",
        ),
    ) or nh == "sku":
        set_if_stronger("market_sku", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])

    # --- Product line (hierarchy) ---
    if nh in ("product_line", "line_id", "line_code") or _any_phrase(
        nh,
        (
            "product_line",
            "prod_line",
            "line_of_business",
            "portfolio_line",
            "merchandising_line",
        ),
    ):
        set_if_stronger("product_line", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])

    # --- Country / market scope ---
    if nh in ("country", "country_code", "country_id", "market_code", "iso_country", "sales_country") or _any_phrase(
        nh,
        ("country_code", "country_of_sale", "market_country", "destination_country", "iso_3166"),
    ):
        set_if_stronger("country_code", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])

    # --- Business unit ---
    if (
        nh in ("business_unit", "bu", "division", "profit_center")
        or _has_segment(nh, "division")
        or _any_phrase(
            nh,
            (
                "business_unit",
                "division_code",
                "segment_code",
                "operating_unit",
                "org_segment",
                "profit_center",
            ),
        )
    ) and "subdivision" not in nh:
        set_if_stronger("business_unit", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])
    elif _has_segment(nh, "bu") and _any_phrase(nh, ("org", "business", "corp", "division")):
        set_if_stronger("business_unit", _SCORE_DETERMINISTIC_HEADER_WEAK, [_REASON_DET_HEADER])

    # --- Lifecycle dates ---
    if _any_phrase(
        nh,
        (
            "launch_date",
            "release_date",
            "go_live",
            "go_live_date",
            "introduction_date",
            "intro_date",
            "general_availability",
            "ga_date",
            "available_date",
            "ship_date",
            "time_to_market",
            "ttv",
            "ttv_date",
            "first_ship",
            "rtm_date",
        ),
    ):
        set_if_stronger("launch_date", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])

    if _any_phrase(
        nh,
        (
            "end_of_life",
            "end_of_life_date",
            "eol_date",
            "eol",
            "end_of_product",
            "end_of_sale",
            "eos",
            "eop",
            "eop_date",
            "retired_date",
            "retirement_date",
            "sunset_date",
            "obsolete",
            "obsolete_date",
            "obsolescence",
            "last_buy",
            "last_ship",
            "product_end",
            "discontinue",
        ),
    ):
        set_if_stronger("end_of_life_date", _SCORE_DETERMINISTIC_HEADER, [_REASON_DET_HEADER])

    # --- Value-backed lifecycle when dtype/date and header tokens ---
    dtype = str(meta.get("dtype", "")).lower() if meta else ""
    date_like = "date" in dtype or "datetime" in dtype
    if date_like and samples and not scores.get("launch_date") and not scores.get("end_of_life_date"):
        if any(looks_like_calendar_date_or_datetime(s) for s in samples):
            if _any_phrase(nh, ("start", "intro", "launch", "release", "live", "ttv", "ship", "ga")):
                set_if_stronger(
                    "launch_date",
                    _SCORE_DETERMINISTIC_VALUE,
                    [_REASON_DET_VALUE, "date_like_value"],
                )
            elif _any_phrase(nh, ("end", "eol", "retire", "sunset", "obsolete", "last", "eop")):
                set_if_stronger(
                    "end_of_life_date",
                    _SCORE_DETERMINISTIC_VALUE,
                    [_REASON_DET_VALUE, "date_like_value"],
                )

    # --- Samples: technical id vs long prose ---
    if scores.get("technical_product_id") and samples:
        first = samples[0].split()[0]
        if len(first) > 60 or first.count(" ") > 3:
            scores.pop("technical_product_id", None)
            reasons.pop("technical_product_id", None)

    return scores, reasons


STRONG_DETERMINISTIC_REASONS: frozenset[str] = frozenset({_REASON_DET_HEADER, _REASON_DET_VALUE})
