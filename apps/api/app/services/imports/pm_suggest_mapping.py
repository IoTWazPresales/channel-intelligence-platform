"""Product Master column suggestions: competitive scoring, semantic groups, explainability."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.pipeline import default_field_mapping, effective_mapping_template
from app.services.imports.identifier_resolution_hook import maybe_identifier_resolution_hint
from app.services.imports.pm_deterministic_aliases import (
    STRONG_DETERMINISTIC_REASONS,
    deterministic_alias_scores,
)
from app.services.imports.pm_value_patterns import (
    best_barcode_kind_from_samples,
    looks_like_calendar_date_or_datetime,
)
from app.services.imports.pm_field_catalog import (
    LEGACY_PM_TARGET_TO_GENERIC,
    PM_CANONICAL_GENERIC,
    PM_GLOBAL_HEADER_SYNONYMS,
    PM_IDENTITY_TARGETS,
    PM_SEMANTIC_GROUP,
    normalize_pm_mapping_target,
)

# --- Score weights (relative scale; exact header dominates weak fuzzy matches) ---
_SCORE_EXACT_CANONICAL_HEADER = 92.0
_SCORE_EXACT_LEGACY_HEADER = 88.0
_SCORE_NEAR_EXACT_HEADER = 48.0
_SCORE_TEMPLATE_HINT = 16.0
_SCORE_SAMPLE_STRONG = 22.0
_SCORE_SAMPLE_MEDIUM = 14.0
_SCORE_SAMPLE_WEAK = 8.0
_SCORE_DTYPE_MATCH = 12.0
_SCORE_GROUP_ALIGN_BONUS = 6.0
_SCORE_GROUP_MISMATCH_PENALTY = -28.0
_SCORE_SOURCE_MEMORY_BASE = 34.0

# Tier thresholds (raw score scale ~0–120)
_RAW_TIER_AUTO = 50.0
_RAW_TIER_SUGGEST = 22.0
_RAW_WEAK_CAP = 18.0
# Do not surface weak hint_target below this raw score (reduces embarrassing hints).
_RAW_HINT_MIN = 28.0

_MIN_ACCEPT_RAW = 18.0
_MARGIN_VS_RUNNER_UP = 10.0
_CONF_AMBIGUOUS_RATIO = 0.82

_REASON_EXACT_HEADER = "exact_header_match"
_REASON_NEAR_EXACT_HEADER = "normalized_header_match"
_REASON_LEGACY_ALIAS_HEADER = "legacy_alias_header"
_REASON_CURATED_ALIAS = "alias_catalog_match"
_REASON_TEMPLATE = "template_mapping"
_REASON_PATTERN_HEADER = "header_keyword_signal"
_REASON_SAMPLE_FORM_FACTOR = "sample_values_resemble_form_factor"
_REASON_SAMPLE_PLATFORM = "sample_values_resemble_platform_cpu_family"
_REASON_SAMPLE_SERIES = "sample_values_resemble_series_or_segment_name"
_REASON_SAMPLE_BARCODE = "sample_values_resemble_barcode"
_REASON_SAMPLE_TECH_ID = "sample_values_resemble_technical_id"
_REASON_SAMPLE_DISPLAY_NAME = "sample_values_resemble_long_title"
_REASON_DTYPE_NUMERIC_RANGE = "dtype_numeric_capacity_like"
_REASON_GROUP_ALIGN = "semantic_group_aligned_with_header"
_REASON_GROUP_MISMATCH = "semantic_group_mismatch_penalty"
_REASON_LOW_CONFIDENCE = "low_confidence"
_REASON_CLOSE_RUNNER_UP = "ambiguous_close_runner_up"
_REASON_ALIAS_MATCH = "alias_match"
_REASON_SOURCE_MEMORY = "source_memory"
_REASON_NO_CANONICAL_FIT = "no_suitable_canonical_target"
_REASON_RECOMMEND_STAGE = "recommend_stage_metadata"
_REASON_RECOMMEND_IGNORE = "recommend_ignore"
_REASON_IDENTIFIER_HOOK = "identifier_resolution_available"

# Normalized explainability tokens (aligned with UI).
_REASON_BARCODE_LIKE_VALUE = "barcode_like_value"
_REASON_TECH_ID_LIKE_VALUE = "technical_id_like_value"
_REASON_DATE_LIKE_VALUE = "date_like_value"

_CATCHALL_WEAK_HINT_TARGETS = frozenset({"technical_product_id", "display_name"})

_EXACT_REASON_CODES = frozenset(
    {
        _REASON_EXACT_HEADER,
        _REASON_LEGACY_ALIAS_HEADER,
        _REASON_CURATED_ALIAS,
        _REASON_NEAR_EXACT_HEADER,
        _REASON_ALIAS_MATCH,
    }
)

# Deterministic universal aliases + exact-style headers both qualify for strong auto-map/suggest tiers.
_STRONG_SIGNAL_REASON_CODES = frozenset(_EXACT_REASON_CODES | STRONG_DETERMINISTIC_REASONS)


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")


def _infer_meta(inferred_schema: dict[str, Any] | None, header: str) -> dict[str, Any] | None:
    if not inferred_schema or not isinstance(inferred_schema, dict):
        return None
    for col in inferred_schema.get("columns") or []:
        if isinstance(col, dict) and str(col.get("name", "")).strip() == str(header).strip():
            return col
    return None


def _samples_join(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    raw = meta.get("sample") or []
    parts = []
    for x in raw[:8]:
        if x is None:
            continue
        parts.append(str(x))
    return " ".join(parts)


def _dtype_is_date(dtype: str) -> bool:
    d = (dtype or "").lower()
    return "datetime" in d or "date" in d


def _dtype_is_numeric(dtype: str) -> bool:
    d = (dtype or "").lower()
    return any(x in d for x in ("int", "float", "decimal", "number"))


_RE_FORM_FACTOR = re.compile(
    r"\b(notebook|desktop|mini\s*pc|workstation|tower|ai\s*pc|chromebook|tablet|"
    r"convertible|2\s*[\-/]\s*1|two[\s\-]in[\s\-]one|clamshell|brick|\bai\s*o\s*t\b)\b",
    re.I,
)
_RE_INTEL_AMD_GEN = re.compile(
    r"\b(intel|amd|snapdragon|apple\s*m\d|xeon|core\s*i\d|\d+(?:st|nd|rd|th)\s+gen)\b",
    re.I,
)
_RE_PLATFORM_CODENAME = re.compile(r"\b[A-Z]{3,}(?:\s+[A-Z]{3,})+\b|\b[A-Z]{8,}\b")
_RE_SERIES_MARKETING = re.compile(
    r"\b(rog|vivobook|zenbook|thinkpad|latitude|precision|elitebook|spectre|surface|"
    r"swift|spin|nitro|predator|legion|thinkcentre|macbook|surface\s*pro)\b",
    re.I,
)

# Generic spec / rich-attribute columns — usually no Product Master canonical slot.
_SPEC_STAGE_HINT = re.compile(
    r"(processor|cpu|gpu|graphics|memory|ram|storage|ssd|hdd|nvme|display|screen|panel|"
    r"resolution|refresh|battery|watt|power_supply|dimension|weight|port|hdmi|usb|"
    r"thunderbolt|ethernet|wifi|wlan|camera|speaker|audio|cooling|fan|heatsink|chipset|"
    r"socket|cores|threads|battery_|mah|nits|touchscreen|webcam|keyboard|trackpad|"
    r"accessory|adapter|cable|charger|certification|warranty_text|photo|image|picture|"
    r"content_url|marketing_blob|spec_sheet|datasheet|long_description|detail)",
    re.I,
)


def _infer_header_signal_groups(nh: str) -> tuple[frozenset[str], list[str]]:
    """Rough semantic buckets implied by normalized header tokens (not mutually exclusive)."""
    reasons: list[str] = []
    groups: set[str] = set()

    def tok_hit(*needles: str) -> bool:
        return any(n in nh for n in needles)

    if nh == "series" or nh.endswith("_series") or nh.startswith("series_") or nh.endswith("_series_name"):
        groups.add("classification")
        reasons.append("header_tokens_series")
    if any(t in nh for t in ("series_name", "product_series")):
        groups.add("classification")
        reasons.append("header_tokens_series_name")

    if "form_factor" in nh or "chassis" in nh:
        groups.add("classification")
        reasons.append("header_tokens_form_factor")

    if any(x in nh for x in ("memory", "ram", "capacity", "mhz", "ghz")) or tok_hit("gb", "tb"):
        groups.add("capacity_spec")
        reasons.append("header_tokens_capacity_spec")

    if any(x in nh for x in ("cpu", "processor", "socket", "platform", "chipset")):
        groups.add("technical_platform")
        reasons.append("header_tokens_platform")

    if any(x in nh for x in ("launch", "eol", "retire", "lifecycle", "phase")):
        groups.add("lifecycle")
        reasons.append("header_tokens_lifecycle")

    if any(x in nh for x in ("ean", "gtin", "upc", "barcode")):
        groups.add("barcode")
        reasons.append("header_tokens_barcode")

    if _SPEC_STAGE_HINT.search(nh):
        groups.add("spec_attribute")
        reasons.append("header_tokens_spec_attribute")

    return frozenset(groups), reasons


def _sample_signals(
    samples_txt: str,
    nh: str,
    meta: dict[str, Any] | None,
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Keyed by generic target — conservative barcodes need per-cell sample strings."""
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def add(gt: str, w: float, reason: str) -> None:
        if gt not in PM_CANONICAL_GENERIC:
            return
        scores[gt] = scores.get(gt, 0.0) + w
        reasons.setdefault(gt, []).append(reason)

    raw_cells: list[str] = []
    if meta:
        for x in (meta.get("sample") or [])[:8]:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                raw_cells.append(s)
    if not raw_cells and not samples_txt.strip():
        return scores, reasons

    bk, _btags = best_barcode_kind_from_samples(raw_cells if raw_cells else [samples_txt])
    if bk == "barcode_ean":
        add("barcode_ean", _SCORE_SAMPLE_STRONG, _REASON_BARCODE_LIKE_VALUE)
    elif bk == "barcode_upc":
        add("barcode_upc", _SCORE_SAMPLE_STRONG, _REASON_BARCODE_LIKE_VALUE)

    if _RE_FORM_FACTOR.search(samples_txt):
        add("form_factor", _SCORE_SAMPLE_STRONG, _REASON_SAMPLE_FORM_FACTOR)

    if _RE_INTEL_AMD_GEN.search(samples_txt) or _RE_PLATFORM_CODENAME.search(samples_txt):
        if not _SPEC_STAGE_HINT.search(nh):
            add("model_family", _SCORE_SAMPLE_MEDIUM, _REASON_SAMPLE_PLATFORM)

    if _RE_SERIES_MARKETING.search(samples_txt) and len(samples_txt) < 120:
        add("series", _SCORE_SAMPLE_MEDIUM, _REASON_SAMPLE_SERIES)

    title_like_header = any(
        x in nh
        for x in (
            "name",
            "title",
            "description",
            "marketing",
            "product_name",
            "display_name",
            "long_name",
            "label",
        )
    )
    # Long prose → display name only when header suggests a title/marketing column.
    if title_like_header and len(samples_txt.strip()) > 28 and sum(c.isalpha() for c in samples_txt) > 18:
        add("display_name", _SCORE_SAMPLE_WEAK, _REASON_SAMPLE_DISPLAY_NAME)

    parts = samples_txt.split()
    # Avoid blocking on substring "name" inside tokens like model_name / machine_name (spec columns).
    name_display_context = any(
        p in nh
        for p in (
            "product_name",
            "display_name",
            "long_name",
            "short_name",
            "marketing_name",
            "vendor_name",
            "item_name",
            "full_name",
        )
    )
    allow_tech_token = not name_display_context
    allow_tech_token = allow_tech_token and not any(
        x in nh
        for x in (
            "title",
            "description",
            "marketing",
            "display",
            "ean",
            "gtin",
            "upc",
            "barcode",
            "country",
            "launch",
            "date",
            "price",
            "color",
            "photo",
            "image",
            "warranty",
        )
    )
    if parts and allow_tech_token:
        first = parts[0].strip()
        if 4 <= len(first) <= 44 and re.match(r"^[A-Za-z0-9][A-Za-z0-9\-_./]+$", first):
            if looks_like_calendar_date_or_datetime(first):
                pass
            elif not any(c.isalpha() for c in first) and 8 <= len(re.sub(r"\D", "", first)) <= 14:
                pass  # digit-only codes handled by strict barcode path
            elif len(first) < 50 and first.count(" ") == 0:
                add("technical_product_id", _SCORE_SAMPLE_MEDIUM - 4.0, _REASON_TECH_ID_LIKE_VALUE)

    return scores, reasons


def _curated_header_alias(nh: str) -> str | None:
    """High-precision normalized header → canonical target (extra entries beyond legacy map)."""
    extra = {
        "product_series": "series",
        "line_series": "series",
        "sku_series": "series",
        "family_name": "model_family",
    }
    if nh in extra:
        return extra[nh]
    return None


def _exact_header_target(nh: str) -> tuple[str | None, str | None]:
    if nh in PM_CANONICAL_GENERIC:
        return nh, _REASON_EXACT_HEADER
    leg = LEGACY_PM_TARGET_TO_GENERIC.get(nh)
    if leg:
        return leg, _REASON_LEGACY_ALIAS_HEADER
    cur = _curated_header_alias(nh)
    if cur:
        return cur, _REASON_CURATED_ALIAS
    g = PM_GLOBAL_HEADER_SYNONYMS.get(nh)
    if g and g in PM_CANONICAL_GENERIC:
        return g, _REASON_ALIAS_MATCH
    return None, None


def _header_pattern_scores(nh: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    """
    Conservative substring rules — needles must be specific enough to avoid
    `memory_capacity_range` matching a lone `range` token.
    """
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def add(gt: str, w: float) -> None:
        if gt not in PM_CANONICAL_GENERIC:
            return
        scores[gt] = scores.get(gt, 0.0) + w
        reasons.setdefault(gt, []).append(_REASON_PATTERN_HEADER)

    def matches_needle(needle: str) -> bool:
        if nh == needle:
            return True
        if needle.startswith(nh) or nh.startswith(needle + "_") or nh.endswith("_" + needle):
            return True
        if len(needle) >= 4 and f"_{needle}_" in f"_{nh}_":
            return True
        return False

    # (target, needles, weight) — avoid short needles like "range" without prefix
    patterns: list[tuple[str, list[str], float]] = [
        ("technical_product_id", ["technical_product", "product_id", "part_number", "part_no", "mpn", "material", "item_id", "manufacturer"], 3.2),
        ("display_name", ["display_name", "product_name", "title", "description", "item_description", "long_name"], 3.2),
        ("market_sku", ["market_sku", "sales_model", "commercial_model", "disti_model", "channel_model"], 3.0),
        ("model_family", ["model_family", "series_model"], 2.8),
        ("source_product_code", ["source_product", "vendor_sku", "feed_sku", "external_id", "disti_sku"], 2.8),
        ("barcode_ean", ["ean", "gtin", "gtin14", "barcode_ean"], 3.2),
        ("barcode_upc", ["upc", "barcode_upc"], 3.2),
        ("category", ["category", "product_class"], 2.2),
        ("product_line", ["product_line", "line_of_business", "lob"], 2.2),
        (
            "series",
            ["series", "series_name", "product_series", "line_series", "model_series", "product_range", "line_range"],
            3.0,
        ),
        ("business_unit", ["business_unit", "bu_code", "division"], 2.2),
        ("form_factor", ["form_factor", "chassis", "product_type"], 3.0),
        ("price_band", ["price_band", "price_tier"], 2.0),
        ("country_code", ["country_code", "market_country"], 2.0),
        ("lifecycle_status", ["lifecycle", "item_status", "publish"], 2.4),
        ("launch_date", ["launch", "intro_date", "start_date", "creation_date"], 2.6),
        ("end_of_life_date", ["end_of_life", "sunset_date"], 2.6),
    ]

    for gt, needles, w in patterns:
        for n in needles:
            if matches_needle(n):
                add(gt, w)
                break

    return scores, reasons


def _template_scores(nh: str, tpl_norm: str | None) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    if not tpl_norm or tpl_norm not in PM_CANONICAL_GENERIC:
        return scores, reasons

    conflict = False
    # Pipeline maps `series_name` → name → display_name; suppress that mistake.
    if tpl_norm == "display_name":
        if "series" in nh or (nh.endswith("_name") and nh.startswith("series")):
            conflict = True
        if nh in ("model_family", "model_name") or ("model" in nh and "name" in nh and "display" not in nh):
            conflict = True

    if conflict:
        return scores, reasons

    w = _SCORE_TEMPLATE_HINT
    scores[tpl_norm] = w
    reasons[tpl_norm] = [_REASON_TEMPLATE]

    return scores, reasons


def _dtype_scores(nh: str, dtype: str, meta: dict[str, Any] | None) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    if not meta:
        return scores, reasons

    if _dtype_is_date(dtype):
        if any(x in nh for x in ("launch", "intro", "start", "creation", "open", "ship", "ga", "live", "ttv", "release")):
            scores["launch_date"] = _SCORE_DTYPE_MATCH
            reasons["launch_date"] = [_REASON_DATE_LIKE_VALUE]
        elif any(x in nh for x in ("eol", "retire", "sunset", "phase", "obsolete", "discontinue", "last_buy", "end")):
            scores["end_of_life_date"] = _SCORE_DTYPE_MATCH
            reasons["end_of_life_date"] = [_REASON_DATE_LIKE_VALUE]

    if _dtype_is_numeric(dtype):
        if any(x in nh for x in ("memory", "ram", "capacity", "gb", "mhz")):
            # No canonical RAM target — dtype supports refusal / weak suggestion elsewhere
            reasons.setdefault("_numeric_capacity_hint", [_REASON_DTYPE_NUMERIC_RANGE])

    return scores, reasons


def _merge_score_maps(
    *maps: tuple[dict[str, float], dict[str, list[str]]],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    total: dict[str, float] = {}
    all_reasons: dict[str, list[str]] = {}
    for sc, rs in maps:
        for k, v in sc.items():
            if k.startswith("_"):
                continue
            total[k] = total.get(k, 0.0) + v
        for k, rlist in rs.items():
            if k.startswith("_"):
                continue
            all_reasons.setdefault(k, []).extend(rlist)
    return total, all_reasons


def _apply_group_penalties(
    nh: str,
    scores: dict[str, float],
    header_groups: frozenset[str],
    samples_txt: str,
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Down-rank targets whose semantic group disagrees with header signals."""
    extra_reasons: dict[str, list[str]] = {}
    if not header_groups:
        return scores, extra_reasons

    out = dict(scores)
    for tgt, sc in list(out.items()):
        # capacity_spec in header: penalize series/display/form_factor unless samples strongly disagree
        if "capacity_spec" in header_groups and tgt in ("series", "display_name", "form_factor"):
            if tgt == "series" and _RE_SERIES_MARKETING.search(samples_txt):
                continue
            out[tgt] = sc + _SCORE_GROUP_MISMATCH_PENALTY
            extra_reasons.setdefault(tgt, []).append(_REASON_GROUP_MISMATCH)
        # cpu/platform header should not bind to chassis/form factor without form-factor samples
        if "technical_platform" in header_groups and tgt == "form_factor":
            if not _RE_FORM_FACTOR.search(samples_txt):
                out[tgt] = out[tgt] + _SCORE_GROUP_MISMATCH_PENALTY
                extra_reasons.setdefault(tgt, []).append(_REASON_GROUP_MISMATCH)

        # Rich spec columns: down-rank only the noisiest catch-alls; allow real model_family signals.
        if "spec_attribute" in header_groups and tgt in ("technical_product_id", "display_name"):
            out[tgt] = out[tgt] + _SCORE_GROUP_MISMATCH_PENALTY
            extra_reasons.setdefault(tgt, []).append(_REASON_GROUP_MISMATCH)

    return out, extra_reasons


def _apply_source_memory_boost(
    merged: dict[str, float],
    merged_reasons: dict[str, list[str]],
    mem_row: dict[str, Any] | None,
) -> None:
    if not mem_row or not mem_row.get("target"):
        return
    t = normalize_pm_mapping_target(str(mem_row["target"]))
    if not t or t not in PM_CANONICAL_GENERIC:
        return
    c = int(mem_row.get("confirmations", 1))
    boost = _SCORE_SOURCE_MEMORY_BASE + min(c, 15) * 1.1
    merged[t] = merged.get(t, 0.0) + boost
    merged_reasons.setdefault(t, []).append(_REASON_SOURCE_MEMORY)


def _score_column_competitive(
    nh: str,
    meta: dict[str, Any] | None,
    template_tgt: str | None,
    source_mem_row: dict[str, Any] | None = None,
) -> tuple[
    dict[str, float],
    dict[str, list[str]],
    list[tuple[str, float]],
    tuple[str | None, float],
    tuple[str | None, float],
]:
    tpl_norm = normalize_pm_mapping_target(template_tgt) if template_tgt else None
    samples_txt = _samples_join(meta)
    dtype = str(meta.get("dtype", "")) if meta else ""

    det_scores, det_reasons = deterministic_alias_scores(nh, meta)
    header_groups, _ = _infer_header_signal_groups(nh)
    sample_scores, sample_reasons = _sample_signals(samples_txt, nh, meta)
    pattern_scores, pattern_reasons = _header_pattern_scores(nh)
    template_scores, template_reasons = _template_scores(nh, tpl_norm)
    dtype_scores, dtype_reasons = _dtype_scores(nh, dtype, meta)

    # Layer order: deterministic aliases → template mapping → probabilistic signals.
    merged, merged_reasons = _merge_score_maps(
        (det_scores, det_reasons),
        (template_scores, template_reasons),
        (pattern_scores, pattern_reasons),
        (sample_scores, sample_reasons),
        (dtype_scores, dtype_reasons),
    )

    # Source-scoped memory (confirmed imports) reinforces targets before structural boosts.
    _apply_source_memory_boost(merged, merged_reasons, source_mem_row)

    exact_tgt, exact_reason = _exact_header_target(nh)
    if exact_tgt:
        merged[exact_tgt] = merged.get(exact_tgt, 0.0) + (
            _SCORE_EXACT_CANONICAL_HEADER if nh == exact_tgt else _SCORE_EXACT_LEGACY_HEADER
        )
        merged_reasons.setdefault(exact_tgt, []).insert(0, exact_reason)

    # Near-exact: canonical key matches as stem (e.g. `form_factor_v2` → form_factor)
    for cand in PM_CANONICAL_GENERIC:
        if nh != cand and (nh.startswith(cand + "_") or nh.endswith("_" + cand) or f"_{cand}_" in f"_{nh}_"):
            merged[cand] = merged.get(cand, 0.0) + _SCORE_NEAR_EXACT_HEADER
            merged_reasons.setdefault(cand, []).append(_REASON_NEAR_EXACT_HEADER)

    merged, group_rs = _apply_group_penalties(nh, merged, header_groups, samples_txt)
    for t, rs in group_rs.items():
        merged_reasons.setdefault(t, []).extend(rs)

    # Group alignment bonus when header group matches target group
    for tgt in list(merged.keys()):
        tg = PM_SEMANTIC_GROUP.get(tgt, "")
        if header_groups and tg in header_groups:
            merged[tgt] = merged.get(tgt, 0.0) + _SCORE_GROUP_ALIGN_BONUS
            merged_reasons.setdefault(tgt, []).append(_REASON_GROUP_ALIGN)

    sample_vals = (
        [str(x) for x in (meta.get("sample") or [])[:8] if x is not None and str(x).strip()] if meta else []
    )
    if sample_vals and merged:
        ir_hint = maybe_identifier_resolution_hint(
            normalized_header=nh,
            sample_values=sample_vals,
            context={"best_guess": max(merged.items(), key=lambda x: x[1])[0]},
        )
        if ir_hint is not None:
            bt = max(merged.items(), key=lambda x: x[1])[0]
            merged_reasons.setdefault(bt, []).append(_REASON_IDENTIFIER_HOOK)

    ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    best_t, best_s = ranked[0] if ranked else (None, 0.0)
    second_t, second_s = ranked[1] if len(ranked) > 1 else (None, 0.0)

    return merged, merged_reasons, ranked, (best_t, best_s), (second_t, second_s)


def _raw_to_confidence(best: float, second: float) -> float:
    if best <= 0:
        return 0.0
    gap = best - max(second, 0.0)
    ratio = gap / (best + 1e-6)
    return float(min(1.0, max(0.0, 0.35 + 0.65 * min(1.0, ratio * 1.4))))


def _dedupe_reasons(rs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in rs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _runner_up_payload(
    second_t: str | None,
    second_s: float,
    best_s: float,
    merged_reasons: dict[str, list[str]],
) -> dict[str, Any] | None:
    if second_t is None:
        return None
    return {
        "target": second_t,
        "confidence": round(min(_raw_to_confidence(second_s, best_s) * _CONF_AMBIGUOUS_RATIO, 0.95), 3),
        "reasons": (merged_reasons.get(second_t) or [])[:6],
    }


def _heuristic_disposition(nh: str, samples_txt: str, best_s: float) -> tuple[str | None, list[str]]:
    """When canonical mapping is weak — recommend stage metadata or ignore for obvious cases."""
    extra: list[str] = []
    if re.match(r"^col_?\d+$", nh) or nh in ("x", "xx", "field1", "f1", "column1", "column2", "a", "b", "tbd", "na", "n_a"):
        return "ignore", [_REASON_RECOMMEND_IGNORE]
    if _SPEC_STAGE_HINT.search(nh) and best_s < 44:
        return "stage_raw", [_REASON_RECOMMEND_STAGE, _REASON_NO_CANONICAL_FIT]
    if any(x in nh for x in ("proprietary", "user_defined", "custom_field", "custom_attr")) and "name" not in nh:
        return "stage_raw", [_REASON_RECOMMEND_STAGE]
    if any(x in nh for x in ("wattage", "voltage", "amperage", "screen_diag", "weight_kg")) and best_s < 38:
        return "stage_raw", [_REASON_RECOMMEND_STAGE]
    if ("capacity" in nh or "_mhz" in nh or "mhz" in nh) and best_s < 28:
        return "stage_raw", [_REASON_RECOMMEND_STAGE]
    if best_s < 12 and len(samples_txt.strip()) < 2:
        return "ignore", [_REASON_RECOMMEND_IGNORE]
    return None, extra


def _finalize_mapper_decision(
    nh: str,
    best_t: str | None,
    best_s: float,
    second_t: str | None,
    second_s: float,
    merged_reasons: dict[str, list[str]],
    samples_txt: str,
    mem_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Produce mapper_action, optional target, restraint on noisy hints, disposition hints."""
    conf = _raw_to_confidence(best_s, second_s)
    unique_reasons = _dedupe_reasons(list(merged_reasons.get(best_t or "", [])))
    ambiguous = second_t is not None and second_s >= best_s - _MARGIN_VS_RUNNER_UP
    strong_signal = any(r in _STRONG_SIGNAL_REASON_CODES for r in unique_reasons)
    from_memory = _REASON_SOURCE_MEMORY in unique_reasons

    rec_disp, rec_rs = _heuristic_disposition(nh, samples_txt, best_s)
    ru = _runner_up_payload(second_t, second_s, best_s, merged_reasons)
    if ru and (
        (best_s < _RAW_TIER_SUGGEST and not strong_signal)
        or (second_t and second_t in _CATCHALL_WEAK_HINT_TARGETS)
    ):
        ru = None

    base_out: dict[str, Any] = {
        "confidence": round(conf if best_t else 0.0, 3),
        "reasons": unique_reasons[:10],
        "runner_up": ru,
        "from_source_memory": from_memory,
    }

    # Strong structural recommendation before scoring (noise / internal-only columns).
    if rec_disp == "ignore":
        base_out["mapper_action"] = "recommend_ignore"
        base_out["recommended_disposition"] = "ignore"
        base_out["reasons"] = _dedupe_reasons(base_out["reasons"] + rec_rs + [_REASON_RECOMMEND_IGNORE])[:10]
        return base_out

    template_hint = _REASON_TEMPLATE in unique_reasons

    auto_ok = False
    if best_t:
        if strong_signal and best_s >= 68:
            auto_ok = True
        elif best_s >= _RAW_TIER_AUTO and not ambiguous:
            auto_ok = True
        elif from_memory and best_s >= 36 and not ambiguous:
            auto_ok = True
        elif template_hint and best_s >= 14 and not ambiguous:
            # Import template alias mapping alone is trusted for auto-fill (validated by provider setup).
            auto_ok = True

    suggest_ok = False
    if best_t and not auto_ok:
        if best_s >= _RAW_TIER_SUGGEST and (not ambiguous or strong_signal):
            suggest_ok = True
        elif strong_signal and best_s >= _RAW_WEAK_CAP:
            suggest_ok = True

    # Weak canonical fit → stage useful spec / attribute columns (commercial default).
    if (
        best_t
        and best_s < _RAW_TIER_SUGGEST
        and not strong_signal
        and not from_memory
        and rec_disp == "stage_raw"
    ):
        base_out["mapper_action"] = "recommend_stage_metadata"
        base_out["recommended_disposition"] = "stage_raw"
        base_out["reasons"] = _dedupe_reasons(base_out["reasons"] + rec_rs + [_REASON_RECOMMEND_STAGE])[:10]
        return base_out

    if auto_ok and best_t:
        base_out["mapper_action"] = "auto_map"
        base_out["target"] = best_t
        base_out.pop("disposition", None)
        base_out["confidence"] = round(max(conf, 0.56), 3)
        return base_out

    if suggest_ok and best_t:
        base_out["mapper_action"] = "suggest"
        base_out["target"] = best_t
        base_out["suggested_target"] = best_t
        base_out.pop("disposition", None)
        base_out["confidence"] = round(min(conf, 0.88), 3)
        rs = base_out["reasons"]
        if ambiguous and not strong_signal:
            rs = _dedupe_reasons(rs + [_REASON_CLOSE_RUNNER_UP])
        base_out["reasons"] = rs[:10]
        return base_out

    base_out["mapper_action"] = "no_strong_suggestion"
    tail: list[str] = []
    if ambiguous and best_t:
        tail.append(_REASON_CLOSE_RUNNER_UP)
    elif best_s < _RAW_TIER_SUGGEST:
        tail.append(_REASON_LOW_CONFIDENCE)
    if not best_t:
        tail.append(_REASON_NO_CANONICAL_FIT)

    base_out["reasons"] = _dedupe_reasons(base_out["reasons"] + tail)[:10]

    # Only surface a weak hint when almost at suggest tier — never for catch-all identity/title guesses.
    if (
        best_t
        and best_t not in _CATCHALL_WEAK_HINT_TARGETS
        and best_s >= _RAW_HINT_MIN
        and best_s < _RAW_TIER_SUGGEST
        and not ambiguous
    ):
        base_out["hint_target"] = best_t

    if mem_row and mem_row.get("disposition") and not best_t:
        if mem_row.get("disposition") == "stage_raw":
            base_out["mapper_action"] = "recommend_stage_metadata"
            base_out["recommended_disposition"] = "stage_raw"
            base_out["reasons"] = _dedupe_reasons(base_out["reasons"] + [_REASON_SOURCE_MEMORY])[:10]

    return base_out


def suggest_pm_mapping(
    headers: list[str],
    source: Any,
    inferred_schema: dict[str, Any] | None = None,
    header_memory: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return suggested_mapping: header → rich mapper payload (actions, restraint, explainability)."""
    template = effective_mapping_template(source)
    auto = default_field_mapping(headers, template)
    mem = header_memory or {}

    out: dict[str, Any] = {}
    used_targets: set[str] = set()

    for h in headers:
        nh = _norm_header(h)
        meta = _infer_meta(inferred_schema, h)
        raw_tpl = auto.get(h)
        tpl_norm = normalize_pm_mapping_target(raw_tpl) if raw_tpl else None
        mem_row = mem.get(nh) if isinstance(mem.get(nh), dict) else None

        _, merged_reasons, ranked, (best_t, best_s), (second_t, second_s) = _score_column_competitive(
            nh, meta, raw_tpl, source_mem_row=mem_row
        )

        base = _finalize_mapper_decision(
            nh,
            best_t,
            best_s,
            second_t,
            second_s,
            merged_reasons,
            _samples_join(meta),
            mem_row,
        )

        tgt = base.get("target")
        action = base.get("mapper_action", "")

        if tgt and tgt in used_targets:
            out[h] = {
                "mapper_action": "no_strong_suggestion",
                "confidence": 0.0,
                "reasons": ["target_already_used"],
                "runner_up": None,
                "from_source_memory": False,
            }
            continue

        if tgt and tgt in PM_IDENTITY_TARGETS and (used_targets & PM_IDENTITY_TARGETS):
            out[h] = {
                "mapper_action": "no_strong_suggestion",
                "confidence": 0.0,
                "reasons": ["identity_target_already_mapped"],
                "runner_up": None,
                "from_source_memory": False,
            }
            continue

        if action == "auto_map" and tgt:
            used_targets.add(tgt)

        # Legacy: UI / saved jobs expect disposition when unmapped
        if action in ("no_strong_suggestion", "recommend_ignore") and "disposition" not in base:
            base["disposition"] = "ignore"

        out[h] = base

    return out
