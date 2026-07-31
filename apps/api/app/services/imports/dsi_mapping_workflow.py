"""Distributor sales & inventory: header infer, initial field mapping, gate checks, source mapping memory."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ingestion.infer import infer_schema, read_tabular
from app.ingestion.pipeline import default_field_mapping, effective_mapping_template
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.distributor_sales_inventory import CANONICAL as DSI_CANONICAL
from app.services.imports.pm_mapping_memory import load_by_header_norm, norm_header_key
from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS
from app.storage.local import get_storage_backend

# Targets persisted in column_mapping_memory (same JSON shape as PM: {target, confirmations}).
DSI_MEMORY_TARGETS = frozenset(DSI_CANONICAL)
DSI_TEMPLATE_SLUG = "distributor_inventory"
_IDENTITY_TARGETS = frozenset({"customer_dealer_token", "dealer_group_token"})


def _norm_header_lower(h: str) -> str:
    return (h or "").strip().lower()


def dsi_header_mapping_policy() -> dict[str, Any]:
    """Per-template header policy from IMPORT_TEMPLATE_ROWS (D-022). Runtime source of truth."""
    row = next((t for t in IMPORT_TEMPLATE_ROWS if t.get("slug") == DSI_TEMPLATE_SLUG), None)
    if not row:
        return {}
    ec = row.get("expected_columns") or {}
    pol = ec.get("_policy") if isinstance(ec, dict) else None
    return dict(pol) if isinstance(pol, dict) else {}


def _policy_exact_target_by_norm(policy: dict[str, Any] | None = None) -> dict[str, str]:
    pol = policy if policy is not None else dsi_header_mapping_policy()
    raw = pol.get("exact_target_by_norm") or {}
    return {str(k): str(v) for k, v in raw.items() if k and v} if isinstance(raw, dict) else {}


def _header_is_never_auto_map(header: str, policy: dict[str, Any] | None = None) -> bool:
    """True when template denylist says this header must not receive an auto identity map."""
    pol = policy if policy is not None else dsi_header_mapping_policy()
    lower = _norm_header_lower(header)
    nh = norm_header_key(header)
    for exact in pol.get("never_auto_map_exact_lower") or []:
        if lower == str(exact).strip().lower():
            return True
    for pat in pol.get("never_auto_map_norm_regex") or []:
        try:
            if nh and re.search(str(pat), nh):
                return True
        except re.error:
            continue
    for rule in pol.get("never_auto_map_if") or []:
        if not isinstance(rule, dict):
            continue
        subs = rule.get("all_of_substrings_lower") or []
        if subs and all(str(s).lower() in lower for s in subs):
            return True
    return False


def apply_dsi_never_auto_map_denylist(
    headers: list[str],
    mapping: dict[str, str],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Clear auto maps on denylisted headers (identity poison prevention)."""
    out = dict(mapping or {})
    pol = policy if policy is not None else dsi_header_mapping_policy()
    for h in headers:
        if not _header_is_never_auto_map(h, pol):
            continue
        tgt = out.get(h)
        if tgt in _IDENTITY_TARGETS or tgt in (
            "customer_code",
            "customer_name",
            "dealer_group_token",
            "customer_dealer_token",
        ):
            del out[h]
        elif h in out and tgt in DSI_MEMORY_TARGETS:
            # Denylist is for identity columns — drop any accidental canonical map on listed headers.
            del out[h]
    return out


def _looks_like_dealer_name_group_column(header: str, policy: dict[str, Any] | None = None) -> bool:
    """Account / rollup column — exact norms from template policy, else structural dealer+group."""
    if _header_is_never_auto_map(header, policy):
        return False
    nh = norm_header_key(header)
    exact = _policy_exact_target_by_norm(policy)
    if nh and exact.get(nh) == "dealer_group_token":
        return True
    k = _norm_header_lower(header)
    if not k:
        return False
    return "dealer" in k and "group" in k


def _looks_like_raw_source_customer_name_column(header: str, policy: dict[str, Any] | None = None) -> bool:
    """Source customer label — exact norms from policy, else structural customer+name (not dealer/group)."""
    if _header_is_never_auto_map(header, policy):
        return False
    nh = norm_header_key(header)
    exact = _policy_exact_target_by_norm(policy)
    if nh and exact.get(nh) == "customer_dealer_token":
        return True
    k = _norm_header_lower(header)
    if not k or "to be mapped" in k:
        return False
    if _looks_like_dealer_name_group_column(header, policy):
        return False
    if "customer" in k and "name" in k and "group" not in k and "dealer" not in k:
        return True
    return False


def apply_template_exact_header_targets(
    headers: list[str],
    mapping: dict[str, str],
    *,
    policy: dict[str, Any] | None = None,
    protected_headers: set[str] | None = None,
) -> dict[str, str]:
    """Apply template ``exact_target_by_norm`` for headers not locked by confirmed memory.

    Replaces the former ``apply_exact_raw_customer_header_overrides`` behaviour. Confirmed
    steward memory must win (D-022) — pass those headers in ``protected_headers``.
    """
    out = dict(mapping or {})
    pol = policy if policy is not None else dsi_header_mapping_policy()
    exact = _policy_exact_target_by_norm(pol)
    protected = protected_headers or set()
    if not exact:
        return out
    for h in headers:
        if h in protected or _header_is_never_auto_map(h, pol):
            continue
        nh = norm_header_key(h)
        tgt = exact.get(nh) if nh else None
        if tgt:
            out[h] = tgt
    return out


# Back-compat name used by tests / pipeline — delegates to template policy; does not beat memory.
def apply_exact_raw_customer_header_overrides(
    headers: list[str],
    mapping: dict[str, str],
    *,
    protected_headers: set[str] | None = None,
) -> dict[str, str]:
    return apply_template_exact_header_targets(
        headers, mapping, protected_headers=protected_headers
    )


def apply_dsi_prefer_header_targets(
    headers: list[str],
    mapping: dict[str, str],
    *,
    policy: dict[str, Any] | None = None,
    protected_headers: set[str] | None = None,
) -> dict[str, str]:
    """When multiple headers share a target, keep the preferred norm; demote listed rivals."""
    out = dict(mapping or {})
    pol = policy if policy is not None else dsi_header_mapping_policy()
    protected = protected_headers or set()
    prefer = pol.get("prefer_header_norms_for_target") or {}
    demote = pol.get("demote_header_norms_for_target") or {}
    if not isinstance(prefer, dict):
        prefer = {}
    if not isinstance(demote, dict):
        demote = {}

    by_target: dict[str, list[str]] = {}
    for h in headers:
        tgt = out.get(h)
        if tgt:
            by_target.setdefault(str(tgt), []).append(h)

    for tgt, prefs in prefer.items():
        cols = by_target.get(str(tgt)) or []
        if len(cols) < 2:
            # Still demote rivals that wrongly hold this target
            pass
        pref_norms = [str(p) for p in (prefs or [])]
        ranked = sorted(
            cols,
            key=lambda h: (
                pref_norms.index(norm_header_key(h))
                if norm_header_key(h) in pref_norms
                else 10_000,
                h,
            ),
        )
        keep = None
        for h in ranked:
            if norm_header_key(h) in pref_norms:
                keep = h
                break
        if keep is None and ranked:
            keep = ranked[0]
        if keep is None:
            continue
        for h in cols:
            if h != keep and h not in protected:
                del out[h]

    for tgt, bad_norms in demote.items():
        bad = {str(n) for n in (bad_norms or [])}
        for h in list(headers):
            if h in protected:
                continue
            if out.get(h) == tgt and norm_header_key(h) in bad:
                del out[h]

    # Prefer customer_name over dealer_name for customer_dealer_token when both present
    # even if dealer_name was only assigned by template alias (single-column ASUS case).
    cust_cols = [h for h in headers if out.get(h) == "customer_dealer_token"]
    if len(cust_cols) > 1:
        prefs = list((prefer.get("customer_dealer_token") or []))
        ranked = sorted(
            cust_cols,
            key=lambda h: (
                prefs.index(norm_header_key(h)) if norm_header_key(h) in prefs else 10_000,
                h,
            ),
        )
        keep = ranked[0]
        for h in cust_cols:
            if h != keep and h not in protected:
                del out[h]

    return out


def apply_dsi_customer_column_target_resolution(
    headers: list[str],
    mapping: dict[str, str],
    *,
    policy: dict[str, Any] | None = None,
    protected_headers: set[str] | None = None,
) -> dict[str, str]:
    """Align customer headers with DSI canonicals before sanitize.

    - Dealer Name Group (and similar) → dealer_group_token (Customer account in UI).
    - Customer name (and similar, excluding dealer+group headers) → customer_dealer_token.

    Skips headers locked by confirmed steward memory (D-022).
    """
    out = dict(mapping or {})
    pol = policy if policy is not None else dsi_header_mapping_policy()
    protected = protected_headers or set()
    dealer_cols = [
        h
        for h in headers
        if h not in protected and _looks_like_dealer_name_group_column(h, pol)
    ]
    cust_cols = [
        h
        for h in headers
        if h not in protected and _looks_like_raw_source_customer_name_column(h, pol)
    ]

    if len(dealer_cols) == 1 and len(cust_cols) == 1 and dealer_cols[0] != cust_cols[0]:
        if dealer_cols[0] not in protected:
            out[dealer_cols[0]] = "dealer_group_token"
        if cust_cols[0] not in protected:
            out[cust_cols[0]] = "customer_dealer_token"
        return out

    if len(dealer_cols) == 1 and dealer_cols[0] not in protected:
        out[dealer_cols[0]] = "dealer_group_token"
    if len(cust_cols) == 1 and not (len(dealer_cols) == 1 and cust_cols[0] == dealer_cols[0]):
        if cust_cols[0] not in protected:
            out[cust_cols[0]] = "customer_dealer_token"

    return out


# Legacy targets from shared default_field_mapping() / other importers — map to DSI when unambiguous.
_LEGACY_TARGET_TO_DSI: dict[str, str] = {
    "channel_code": "channel_key_token",
    "sku": "product_identifier",
    "customer_code": "customer_dealer_token",
    "customer_name": "customer_dealer_token",
    "distributor_code": "distributor_token",
    "distributor_name": "distributor_token",
    "region_code": "region_or_province_token",
    "quantity": "quantity_sold",
    "price": "unit_sellout_price_ex_tax_amount",
    "preferred_distributor_code": "distributor_token",
}


def _header_customerish(header: str) -> bool:
    nk = norm_header_key(str(header)) or ""
    return any(
        p in nk
        for p in (
            "customer",
            "dealer",
            "account",
            "reseller",
            "client",
            "buyer",
            "store",
            "ship to",
            "sold to",
            "company",
            "partner",
        )
    )


def _header_productish(header: str) -> bool:
    nk = norm_header_key(str(header)) or ""
    if any(
        p in nk
        for p in (
            "model",
            "sku",
            "part",
            "product",
            "item",
            "mfg",
            "device",
            "variant",
            "catalog",
            "article",
            "style",
            "serial",
            "material",
            "description",
        )
    ):
        return True
    # Bare "name" / "title" from legacy heuristics: only treat as product if not clearly customer-oriented.
    if nk in ("name", "title") and not _header_customerish(header):
        return True
    return False


def sanitize_dsi_field_mapping(
    headers: list[str],
    mapping: dict[str, str],
    *,
    max_notices: int = 12,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Strip or normalize targets that are not in DSI_CANONICAL (PM/customer-master bleed, legacy keys).

    Returns (sanitized_mapping, notices) where notices use codes dsi_target_normalized / dsi_target_dropped.
    """
    header_set = set(headers)
    notices: list[dict[str, str]] = []
    out: dict[str, str] = {}

    def _notice(code: str, message: str) -> None:
        if len(notices) >= max_notices:
            return
        notices.append({"code": code, "message": message})

    for src, tgt_raw in (mapping or {}).items():
        if src not in header_set:
            continue
        tgt = str(tgt_raw).strip() if tgt_raw is not None else ""
        if not tgt:
            continue
        if tgt in DSI_MEMORY_TARGETS:
            out[src] = tgt
            continue
        if tgt in _LEGACY_TARGET_TO_DSI:
            new_t = _LEGACY_TARGET_TO_DSI[tgt]
            out[src] = new_t
            _notice(
                "dsi_target_normalized",
                f"Column {src!r}: legacy target {tgt!r} was mapped to {new_t!r} for this import type.",
            )
            continue
        if tgt == "name":
            if _header_productish(src) and not _header_customerish(src):
                out[src] = "product_identifier"
                _notice(
                    "dsi_target_normalized",
                    f"Column {src!r}: legacy target 'name' was treated as product identifier for DSI.",
                )
            else:
                _notice(
                    "dsi_target_dropped",
                    f"Column {src!r}: legacy target 'name' is not used for DSI (map explicitly to a DSI field).",
                )
            continue
        _notice(
            "dsi_target_dropped",
            f"Column {src!r}: removed invalid DSI target {tgt!r}.",
        )

    # D-022 / BACKLOG-082: never leave denylisted identity headers mapped (incl. legacy
    # customer_code → customer_dealer_token upgrades above, and saved mappings).
    before = set(out.keys())
    out = apply_dsi_never_auto_map_denylist(list(header_set), out)
    for dropped in sorted(before - set(out.keys())):
        _notice(
            "dsi_denylist_cleared",
            f"Column {dropped!r}: cleared — never-auto-map identity header (template denylist).",
        )

    return out, notices


def column_samples_from_schema_dict(schema: dict[str, Any] | None) -> dict[str, list[str]]:
    """Sample cell strings per column from an ``infer_schema`` payload (same shape as ``job.inferred_schema``)."""
    if not schema:
        return {}
    out: dict[str, list[str]] = {}
    for c in schema.get("columns") or []:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        if not name:
            continue
        raw = c.get("sample") or []
        if not isinstance(raw, list):
            continue
        vals: list[str] = []
        for x in raw[:8]:
            if x is None:
                continue
            s = str(x).strip()
            if not s or s.lower() == "nan":
                continue
            vals.append(s[:200])
        if vals:
            out[str(name)] = vals
    return out


def _samples_have_model_or_part_shape(samples: list[str]) -> bool:
    """Heuristic: values look like model / part / technical id tokens (not short category codes)."""
    for raw in samples[:12]:
        s = str(raw).strip()
        if not s or s.lower() in ("nan", "nat", "none", "<na>", "null", "#n/a", "n/a"):
            continue
        if len(s) >= 8 and any(ch.isdigit() for ch in s):
            return True
        if "-" in s and len(s) >= 6 and any(ch.isdigit() for ch in s):
            return True
        if len(s) >= 6 and any(ch.isdigit() for ch in s) and any(ch.isalpha() for ch in s):
            return True
        alnum = sum(1 for ch in s if ch.isalnum())
        if len(s) >= 12 and alnum >= 10:
            return True
    return False


def _samples_look_like_gtin(samples: list[str]) -> bool:
    """True when samples look like EAN/UPC/GTIN digits (resolution tier ahead of sales model)."""
    digitish = 0
    for raw in samples[:12]:
        s = str(raw).strip()
        if not s or s.lower() in ("nan", "nat", "none", "<na>", "null", "#n/a", "n/a"):
            continue
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) in (8, 12, 13, 14) and len(digits) >= len(s) - 2:
            digitish += 1
    return digitish >= 2 or (digitish >= 1 and len([x for x in samples if str(x).strip()]) <= 3)


def _header_is_customer_sku_slot(nk: str) -> bool:
    """Dealer/customer SKU columns are usually empty form slots — not catalog identity."""
    return "customer" in nk and "sku" in nk


def _header_is_gtin_column(nk: str) -> bool:
    return any(t in nk for t in ("ean", "upc", "gtin", "barcode", "bar code"))


def _header_is_item_or_part_column(nk: str) -> bool:
    """Item / SKU / part-number grain — aligns with item_code resolve tier (not sales model)."""
    if _header_is_customer_sku_slot(nk):
        return False
    if _header_is_gtin_column(nk):
        return True
    if any(t in nk for t in ("itemcode", "item_code", "productcode", "product_code", "productsku")):
        return True
    if "sku" in nk:
        return True
    if "part" in nk and any(t in nk for t in ("no", "num", "code", "id")):
        return True
    return False


def _header_is_sales_model_column(nk: str) -> bool:
    if _header_is_item_or_part_column(nk) or _header_is_customer_sku_slot(nk):
        return False
    if "model" in nk:
        return True
    if "salesmodel" in nk.replace(" ", ""):
        return True
    return False


def _header_is_weak_secondary_product_column(nk: str) -> bool:
    """Generic secondary / often-empty labels — not preferred when a stronger column exists."""
    if _header_is_customer_sku_slot(nk):
        return True
    if nk in ("description", "desc", "other", "notes"):
        return True
    # Manufacturer *model* label without part — often blank beside a real model/part column
    if ("mfg" in nk or "manufacturer" in nk) and "part" not in nk:
        return True
    return False


def _bare_product_header_looks_like_category_samples(header: str, samples: list[str]) -> bool:
    """True when header is bare ``PRODUCT`` and samples look like low-cardinality category codes (e.g. NB)."""
    if norm_header_key(header) != "product":
        return False
    vals = [str(s).strip() for s in samples if s is not None and str(s).strip()]
    if not vals:
        return False
    if _samples_have_model_or_part_shape(vals):
        return False
    uniq = {v.lower() for v in vals}
    if len(uniq) > 8:
        return False
    if max(len(v) for v in uniq) > 6:
        return False
    return True


def _product_identifier_column_score(header: str, samples: list[str]) -> float:
    """Score candidate product columns for auto-map tie-break.

    Aligns with DSI resolve order: item/part/EAN ahead of sales-model. Samples outweigh
    header labels. Brand/OEM-specific header names are not special-cased — classifiers
    are generic (part/sku/ean/model/customer-sku/description).
    """
    nk = norm_header_key(header)
    score = 0.0
    has_shape = _samples_have_model_or_part_shape(samples)
    has_gtin = _samples_look_like_gtin(samples) or (_header_is_gtin_column(nk) and has_shape)

    if has_gtin:
        score += 30.0
    elif _header_is_item_or_part_column(nk) and has_shape:
        score += 28.0
    elif _header_is_sales_model_column(nk) and has_shape:
        score += 22.0
    elif has_shape:
        score += 20.0

    if _header_is_gtin_column(nk):
        score += 15.0
    elif _header_is_item_or_part_column(nk):
        score += 12.0
    elif nk in ("modelname", "model_name"):
        score += 6.0
    elif _header_is_sales_model_column(nk):
        score += 5.0

    if _header_is_weak_secondary_product_column(nk):
        score -= 12.0
        if not samples:
            score -= 10.0
    if nk == "product":
        score -= 6.0
        if _bare_product_header_looks_like_category_samples(header, samples):
            score -= 40.0
    return score


def apply_dsi_product_identifier_header_seeds(
    headers: list[str],
    mapping: dict[str, str],
) -> dict[str, str]:
    """Map unmapped item/part/EAN-like headers to product_identifier (generic; any feed)."""
    out = dict(mapping or {})
    for h in headers:
        if out.get(h):
            continue
        nk = norm_header_key(h)
        if _header_is_item_or_part_column(nk) or _header_is_gtin_column(nk):
            out[h] = "product_identifier"
    return out


def apply_dsi_product_identifier_sample_inference(
    headers: list[str],
    mapping: dict[str, str],
    column_samples: dict[str, list[str]],
) -> dict[str, str]:
    """Adjust ``product_identifier`` auto-mapping using inferred column samples (mapping suggestions only).

    - Demotes bare ``PRODUCT`` when samples look like short category codes (e.g. NB), not model/SKU tokens.
    - When multiple columns map to ``product_identifier``, keeps the best-scoring column
      (item/part/EAN ahead of sales-model when samples support it).
    - If nothing maps to ``product_identifier`` after demotion, assigns an unmapped column that strongly
      resembles a catalog identity column from header + samples.
    """
    out = dict(mapping or {})
    for h in list(headers):
        if out.get(h) != "product_identifier":
            continue
        samp = column_samples.get(h) or []
        if _bare_product_header_looks_like_category_samples(h, samp):
            del out[h]

    pi_headers = [h for h in headers if out.get(h) == "product_identifier"]
    if len(pi_headers) > 1:

        def _sort_key(h: str) -> tuple[float, str]:
            return (_product_identifier_column_score(h, column_samples.get(h) or []), h)

        keep = max(pi_headers, key=_sort_key)
        for h in pi_headers:
            if h != keep:
                del out[h]

    if not any(out.get(h) == "product_identifier" for h in headers):
        best: tuple[float, str] | None = None
        for h in headers:
            if out.get(h):
                continue
            sc = _product_identifier_column_score(h, column_samples.get(h) or [])
            if sc >= 18.0:
                cand = (sc, h)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                    best = cand
        if best is not None:
            out[best[1]] = "product_identifier"

    return out


def column_samples_from_inferred(job: ImportJob) -> dict[str, list[str]]:
    """Short sample cell values per column from inferred_schema (no extra file read)."""
    return column_samples_from_schema_dict(job.inferred_schema)


def merge_dsi_template_aliases_from_code(template: dict[str, Any] | None) -> dict[str, Any]:
    """Union DB/effective aliases with IMPORT_TEMPLATE_ROWS so new seeds work before DB refresh."""
    out: dict[str, Any] = dict(template or {})
    row = next((t for t in IMPORT_TEMPLATE_ROWS if t.get("slug") == DSI_TEMPLATE_SLUG), None)
    ec = (row or {}).get("expected_columns") or {}
    if not isinstance(ec, dict):
        return out
    for k, v in ec.items():
        if str(k).startswith("_") or not isinstance(v, dict):
            continue
        code_aliases = [str(a) for a in (v.get("aliases") or [])]
        prev = out.get(k) if isinstance(out.get(k), dict) else {"aliases": []}
        existing = [str(a) for a in (prev.get("aliases") or [])]
        merged = list(dict.fromkeys([*existing, *code_aliases]))
        out[k] = {**prev, "aliases": merged}
    return out


def build_initial_dsi_field_mapping(
    db: Session,
    headers: list[str],
    source: SourceDefinition | None,
    template: dict[str, Any],
    *,
    column_samples: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Template defaults → denylist → exact/heuristic → confirmed memory last (D-022).

    Precedence: confirmed steward memory > template alias/exact > heuristic.
    """
    policy = dsi_header_mapping_policy()
    template = merge_dsi_template_aliases_from_code(template)
    memory = load_by_header_norm(source) if source else {}
    protected: set[str] = set()
    memory_overlay: dict[str, str] = {}
    for h in headers:
        nh = norm_header_key(h)
        entry = memory.get(nh) if nh else None
        if isinstance(entry, dict):
            tgt = entry.get("target")
            if tgt and str(tgt).strip() and str(tgt) in DSI_MEMORY_TARGETS:
                memory_overlay[h] = str(tgt)
                protected.add(h)

    # 1) Template aliases + shared defaults (no memory yet — memory wins at the end).
    mapping = default_field_mapping(headers, template)
    # 2) Denylist clears poisoned identity maps.
    mapping = apply_dsi_never_auto_map_denylist(headers, mapping, policy=policy)
    # 3) Template exact targets (skip memory-protected).
    mapping = apply_template_exact_header_targets(
        headers, mapping, policy=policy, protected_headers=protected
    )
    # 4) Structural customer heuristics (skip memory-protected).
    mapping = apply_dsi_customer_column_target_resolution(
        headers, mapping, policy=policy, protected_headers=protected
    )
    # 5) Prefer / demote among competing headers for the same target.
    mapping = apply_dsi_prefer_header_targets(
        headers, mapping, policy=policy, protected_headers=protected
    )
    # Normalize legacy sku/name → DSI targets before product demotion so weak columns
    # (e.g. customer sku → sku) participate in the single-winner tie-break.
    mapping, _ = sanitize_dsi_field_mapping(headers, mapping)
    mapping = apply_dsi_product_identifier_header_seeds(headers, mapping)
    mapping = apply_dsi_product_identifier_sample_inference(headers, mapping, column_samples or {})
    # Re-apply denylist after product seeds (identity poison stays cleared).
    mapping = apply_dsi_never_auto_map_denylist(headers, mapping, policy=policy)
    # 6) Confirmed memory overlays last.
    mapping.update(memory_overlay)
    sanitized, _ = sanitize_dsi_field_mapping(headers, mapping)
    return sanitized


def dsi_mapping_gate_errors(
    mapping: dict[str, str],
    *,
    file_distributor_satisfied: bool = False,
    file_snapshot_satisfied: bool = False,
) -> list[dict[str, str]]:
    """Blocking issues before running DSI pipeline (column mapping completeness)."""
    vals = set(mapping.values())
    errs: list[dict[str, str]] = []
    if "distributor_token" not in vals and not file_distributor_satisfied:
        errs.append(
            {
                "code": "missing_column_mapping_distributor",
                "message": (
                    "Required: Distributor — map a distributor column, or confirm a per-file "
                    "distributor identity (banner/company) for every included file."
                ),
            }
        )
    if "product_identifier" not in vals:
        errs.append(
            {
                "code": "missing_column_mapping_product",
                "message": "Required column mapping missing: product identifier (SKU / part number / model / product code).",
            }
        )
    needs_inventory_period = "stock_on_hand" in vals and "snapshot_date" not in vals
    has_tx_or_snap_col = "transaction_date" in vals or "snapshot_date" in vals
    has_date = has_tx_or_snap_col or (needs_inventory_period and file_snapshot_satisfied)
    if needs_inventory_period and not file_snapshot_satisfied:
        errs.append(
            {
                "code": "missing_snapshot_period_for_inventory_file",
                "message": (
                    "Inventory rows need an as-of date: map Inventory snapshot date, or confirm "
                    "the Application Date banner period (ISO week → Monday) for this file."
                ),
            }
        )
    elif not has_date:
        errs.append(
            {
                "code": "missing_column_mapping_date",
                "message": "Required column mapping missing: map a date to Transaction / invoice date and/or Inventory snapshot date.",
            }
        )
    has_qty = "quantity_sold" in vals or "stock_on_hand" in vals
    if not has_qty:
        errs.append(
            {
                "code": "missing_column_mapping_quantity",
                "message": "Map at least one of Quantity sold or Stock on hand — the file must contribute sell-out and/or inventory rows.",
            }
        )
    return errs


def merge_dsi_mapping_memory(db: Session, *, source_id: int, field_mapping: dict[str, str]) -> None:
    """Persist confirmed DSI column → canonical mappings on the source (by normalized header)."""
    src = db.get(SourceDefinition, source_id)
    if src is None:
        return
    root: dict[str, Any] = dict(src.column_mapping_memory or {})
    bh: dict[str, Any] = dict(root.get("by_header_norm") or {})

    for header, tgt in field_mapping.items():
        nh = norm_header_key(str(header))
        if not nh:
            continue
        if tgt not in DSI_MEMORY_TARGETS:
            continue
        prev = bh.get(nh) if isinstance(bh.get(nh), dict) else {}
        bh[nh] = {
            "target": tgt,
            "confirmations": int(prev.get("confirmations", 0)) + 1,
        }

    root["by_header_norm"] = bh
    root["schema_version"] = root.get("schema_version") or "1"
    root["dsi_mapping"] = True
    src.column_mapping_memory = root
    db.add(src)


def infer_dsi_job_sync(db: Session, job_id: int) -> ImportJob:
    """Read stored raw file(s), infer headers, set initial field_mapping + file_headers."""
    job = db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job or job.template_slug != "distributor_inventory":
        raise ValueError("infer_dsi_job_sync requires a distributor_inventory import job")

    from app.services.imports.dsi_batch import list_raw_files_for_job
    from app.services.imports.dsi_workbook import (
        DSI_INFER_SAMPLE_ROWS,
        DSI_SINGLE_SHEET_KEY,
        build_dsi_workbook_structure,
        load_dsi_workbook_sheet_frames,
        make_dsi_file_sheet_key,
        persist_dsi_workbook_on_job,
        raw_file_display_name,
    )

    raws = list_raw_files_for_job(db, job_id)
    if not raws:
        raise ValueError(f"DSI job {job_id} has no raw files")

    storage = get_storage_backend()
    multi_file = len(raws) > 1

    nested_mapping: dict[str, dict[str, str]] = {}
    all_headers: list[str] = []
    combined_sheets: list[dict[str, Any]] = []
    total_sheet_count = 0
    any_multi_sheet = False

    for raw in raws:
        filename = raw_file_display_name(raw.storage_key)
        data = storage.read(raw.storage_key)
        # Bounded sample for mapping/automap — full sheet load happens at validate.
        sheet_frames = load_dsi_workbook_sheet_frames(
            filename, data, max_data_rows=DSI_INFER_SAMPLE_ROWS
        )
        structure = build_dsi_workbook_structure(
            filename,
            data,
            max_data_rows=DSI_INFER_SAMPLE_ROWS,
            frames=sheet_frames,
        )
        total_sheet_count += int(structure.get("sheet_count") or len(sheet_frames))
        if structure.get("multi_sheet"):
            any_multi_sheet = True

        mappable_keys = {
            str(s.get("sheet_key"))
            for s in structure.get("sheets", [])
            if isinstance(s, dict) and s.get("sheet_key")
        }

        if len(sheet_frames) > 1:
            for sheet_name, sheet_df, _header_row in sheet_frames:
                inner_key = sheet_name or DSI_SINGLE_SHEET_KEY
                if mappable_keys and inner_key not in mappable_keys:
                    continue
                schema = infer_schema(sheet_df)
                cols = [c["name"] for c in schema["columns"]]
                all_headers.extend(cols)
                source = job.source
                template = effective_mapping_template(source)
                samples = column_samples_from_schema_dict(schema)
                sheet_map = build_initial_dsi_field_mapping(db, cols, source, template, column_samples=samples)
                from app.services.imports.dsi_column_mapping_intel import apply_high_confidence_dsi_automap

                sheet_map, _ = apply_high_confidence_dsi_automap(cols, source, sheet_map, column_samples=samples)
                sheet_map = apply_dsi_never_auto_map_denylist(cols, sheet_map)
                map_key = (
                    make_dsi_file_sheet_key(filename, inner_key) if multi_file else inner_key
                )
                nested_mapping[map_key] = sheet_map
                for sheet_entry in structure.get("sheets", []):
                    if isinstance(sheet_entry, dict) and sheet_entry.get("sheet_key") == inner_key:
                        entry = dict(sheet_entry)
                        entry["source_file"] = filename
                        entry["mapping_key"] = map_key
                        combined_sheets.append(entry)
        else:
            df = sheet_frames[0][1] if sheet_frames else read_tabular(filename, data)
            schema = infer_schema(df)
            cols = [c["name"] for c in schema["columns"]]
            all_headers.extend(cols)
            source = job.source
            template = effective_mapping_template(source)
            samples = column_samples_from_schema_dict(schema)
            mapping = build_initial_dsi_field_mapping(db, cols, source, template, column_samples=samples)
            from app.services.imports.dsi_column_mapping_intel import apply_high_confidence_dsi_automap

            mapping, _ = apply_high_confidence_dsi_automap(cols, source, mapping, column_samples=samples)
            mapping = apply_dsi_never_auto_map_denylist(cols, mapping)
            inner_key = DSI_SINGLE_SHEET_KEY
            map_key = make_dsi_file_sheet_key(filename, inner_key) if multi_file else inner_key
            if multi_file:
                nested_mapping[map_key] = mapping
            else:
                job.inferred_schema = {**schema, "dsi_column_automap_applied": True}
                job.file_headers = cols
                job.field_mapping = mapping
                persist_dsi_workbook_on_job(job, structure)
                try:
                    from app.services.imports.dsi_file_distributor import propose_file_distributors_for_job
                    from app.services.imports.dsi_file_snapshot import propose_file_snapshot_periods_for_job

                    propose_file_distributors_for_job(db, job)
                    propose_file_snapshot_periods_for_job(db, job)
                except Exception:
                    pass
                job.stage = "dsi_mapping_ready"
                job.status = "pending"
                db.add(job)
                db.commit()
                db.refresh(job)
                return job

            for sheet_entry in structure.get("sheets", []):
                if isinstance(sheet_entry, dict):
                    entry = dict(sheet_entry)
                    entry["source_file"] = filename
                    entry["mapping_key"] = map_key
                    combined_sheets.append(entry)

    if nested_mapping:
        job.inferred_schema = {
            "multi_file": multi_file,
            "multi_sheet": any_multi_sheet or len(nested_mapping) > 1,
            "file_count": len(raws),
            "sheet_count": total_sheet_count,
        }
        job.file_headers = sorted(set(all_headers))
        job.field_mapping = nested_mapping
        workbook_structure = {
            "multi_file": multi_file,
            "multi_sheet": any_multi_sheet or len(nested_mapping) > 1,
            "file_count": len(raws),
            "sheet_count": total_sheet_count,
            "sheets": combined_sheets,
            "files": [raw_file_display_name(r.storage_key) for r in raws],
            "skipped_sheets": [],
        }
        persist_dsi_workbook_on_job(job, workbook_structure)

    try:
        from app.services.imports.dsi_file_distributor import propose_file_distributors_for_job
        from app.services.imports.dsi_file_snapshot import propose_file_snapshot_periods_for_job

        propose_file_distributors_for_job(db, job)
        propose_file_snapshot_periods_for_job(db, job)
    except Exception:
        pass

    job.stage = "dsi_mapping_ready"
    job.status = "pending"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def dsi_mapping_state_dict(job: ImportJob) -> dict[str, Any]:
    """Serializable mapping UI payload."""
    from app.services.imports.dsi_column_mapping_intel import (
        DSI_FIELD_TARGET_DESCRIPTIONS,
        suggest_dsi_column_mapping,
    )
    from app.services.imports.dsi_workbook import (
        DSI_SHEET_META_KEY,
        is_nested_dsi_field_mapping,
    )

    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    workbook = meta.get(DSI_SHEET_META_KEY) if isinstance(meta.get(DSI_SHEET_META_KEY), dict) else None
    from app.services.imports.dsi_file_distributor import (
        DSI_FILE_DISTRIBUTORS_KEY,
        distributor_identity_satisfied,
        file_distributors_all_confirmed,
        get_dsi_file_distributors,
    )
    from app.services.imports.dsi_file_snapshot import (
        DSI_FILE_SNAPSHOT_PERIODS_KEY,
        file_snapshot_periods_all_confirmed,
        get_dsi_file_snapshot_periods,
        snapshot_identity_satisfied,
    )
    from app.services.imports.dsi_batch import get_dsi_excluded_mapping_keys

    file_dist_ok = file_distributors_all_confirmed(job)
    file_distributors = get_dsi_file_distributors(job)
    file_snap_ok = file_snapshot_periods_all_confirmed(job)
    file_snapshots = get_dsi_file_snapshot_periods(job)
    excluded_mapping_keys = get_dsi_excluded_mapping_keys(job)

    if is_nested_dsi_field_mapping(job.field_mapping):
        nested = dict(job.field_mapping or {})
        sheet_states: dict[str, Any] = {}
        blocking_all: list[dict[str, str]] = []
        workbook_sheets = workbook.get("sheets") if isinstance(workbook, dict) else None
        sheets_by_key: dict[str, dict[str, Any]] = {}
        if isinstance(workbook_sheets, list):
            for s in workbook_sheets:
                if not isinstance(s, dict):
                    continue
                mk = s.get("mapping_key") or s.get("sheet_key")
                if mk:
                    sheets_by_key[str(mk)] = s
        from app.services.imports.dsi_batch import dsi_layout_signature

        for sheet_key, sheet_map in nested.items():
            if not isinstance(sheet_map, dict):
                continue
            if str(sheet_key) in excluded_mapping_keys:
                continue
            sheet_meta = sheets_by_key.get(str(sheet_key), {})
            headers = list(sheet_meta.get("columns") or [])
            if not headers:
                headers = sorted({str(k) for k in sheet_map.keys()})
            samples_raw = sheet_meta.get("column_samples")
            samples: dict[str, list[str]] = {}
            if isinstance(samples_raw, dict):
                samples = {
                    str(k): [str(x) for x in v] if isinstance(v, list) else []
                    for k, v in samples_raw.items()
                }
            smap, notices = sanitize_dsi_field_mapping(headers, sheet_map)
            sheet_ok = distributor_identity_satisfied(job, smap, mapping_key=str(sheet_key))
            sheet_snap = snapshot_identity_satisfied(job, smap, mapping_key=str(sheet_key))
            gate = dsi_mapping_gate_errors(
                smap,
                file_distributor_satisfied=sheet_ok,
                file_snapshot_satisfied=sheet_snap,
            )
            blocking_all.extend(gate)
            hints = suggest_dsi_column_mapping(
                headers, job.source, column_samples=samples, current_field_mapping=smap
            )
            layout_sig = dsi_layout_signature([str(h) for h in headers])
            sheet_states[str(sheet_key)] = {
                "field_mapping": smap,
                "blocking_mapping_errors": gate,
                "mapping_valid": len(gate) == 0,
                "mapping_adjustment_notices": notices,
                "column_samples": samples,
                "column_mapping_hints": hints,
                "layout_signature": layout_sig,
            }
        # Deduplicate distributor / snapshot gate messages across sheets
        seen_codes: set[str] = set()
        deduped: list[dict[str, str]] = []
        for e in blocking_all:
            code = str(e.get("code") or "")
            if code in (
                "missing_column_mapping_distributor",
                "missing_snapshot_period_for_inventory_file",
            ):
                if code in seen_codes:
                    continue
                seen_codes.add(code)
            deduped.append(e)
        blocking_all = deduped
        # Presentation-grain layout groups (storage stays per file::sheet).
        layout_groups: list[dict[str, Any]] = []
        sig_order: list[str] = []
        sig_to_keys: dict[str, list[str]] = {}
        for sheet_key, st in sheet_states.items():
            sig = str(st.get("layout_signature") or "")
            if not sig:
                continue
            if sig not in sig_to_keys:
                sig_order.append(sig)
                sig_to_keys[sig] = []
            sig_to_keys[sig].append(sheet_key)
        for sig in sig_order:
            keys = sig_to_keys[sig]
            files: list[str] = []
            for k in keys:
                fname = str(k).split("::", 1)[0] if "::" in str(k) else str(k)
                if fname not in files:
                    files.append(fname)
            layout_groups.append(
                {"signature": sig, "mapping_keys": keys, "files": files}
            )
        inferred = job.inferred_schema if isinstance(job.inferred_schema, dict) else {}
        return {
            "id": job.id,
            "stage": job.stage,
            "status": job.status,
            "import_mode": job.import_mode,
            "template_slug": job.template_slug,
            "error_summary": job.error_summary,
            "multi_sheet": True,
            "multi_file": bool(inferred.get("multi_file") or meta.get("dsi_multi_file")),
            "dsi_workbook": workbook,
            "sheet_field_mappings": sheet_states,
            "field_mapping": nested,
            "file_headers": list(job.file_headers or []),
            "blocking_mapping_errors": blocking_all,
            "mapping_valid": len(blocking_all) == 0,
            "canonical_targets": sorted(DSI_MEMORY_TARGETS),
            "field_target_descriptions": dict(DSI_FIELD_TARGET_DESCRIPTIONS),
            "dsi_workflow_mode": meta.get("dsi_workflow_mode"),
            "dsi_workflow_mode_explicit": meta.get("dsi_workflow_mode_explicit"),
            "dsi_predominantly_old_sellout_dates": meta.get("dsi_predominantly_old_sellout_dates"),
            DSI_FILE_DISTRIBUTORS_KEY: file_distributors,
            "dsi_file_distributors_all_confirmed": file_dist_ok,
            DSI_FILE_SNAPSHOT_PERIODS_KEY: file_snapshots,
            "dsi_file_snapshot_periods_all_confirmed": file_snap_ok,
            "layout_groups": layout_groups,
            "dsi_excluded_mapping_keys": sorted(excluded_mapping_keys),
        }

    headers = list(job.file_headers or [])
    raw_mapping = dict(job.field_mapping or {})
    mapping, notices = sanitize_dsi_field_mapping(headers, raw_mapping)
    flat_ok = distributor_identity_satisfied(job, mapping)
    flat_snap = snapshot_identity_satisfied(job, mapping)
    gate = dsi_mapping_gate_errors(
        mapping,
        file_distributor_satisfied=flat_ok,
        file_snapshot_satisfied=flat_snap,
    )
    samples = column_samples_from_inferred(job)
    column_mapping_hints = suggest_dsi_column_mapping(
        headers, job.source, column_samples=samples, current_field_mapping=mapping
    )
    return {
        "id": job.id,
        "stage": job.stage,
        "status": job.status,
        "import_mode": job.import_mode,
        "template_slug": job.template_slug,
        "error_summary": job.error_summary,
        "file_headers": headers,
        "field_mapping": mapping,
        "column_mapping_hints": column_mapping_hints,
        "canonical_targets": sorted(DSI_MEMORY_TARGETS),
        "blocking_mapping_errors": gate,
        "mapping_valid": len(gate) == 0,
        "mapping_adjustment_notices": notices,
        "column_samples": samples,
        "multi_sheet": False,
        "dsi_workbook": workbook,
        "field_target_descriptions": dict(DSI_FIELD_TARGET_DESCRIPTIONS),
        "dsi_workflow_mode": meta.get("dsi_workflow_mode"),
        "dsi_workflow_mode_explicit": meta.get("dsi_workflow_mode_explicit"),
        "dsi_predominantly_old_sellout_dates": meta.get("dsi_predominantly_old_sellout_dates"),
        DSI_FILE_DISTRIBUTORS_KEY: file_distributors,
        "dsi_file_distributors_all_confirmed": file_dist_ok,
        DSI_FILE_SNAPSHOT_PERIODS_KEY: file_snapshots,
        "dsi_file_snapshot_periods_all_confirmed": file_snap_ok,
    }
