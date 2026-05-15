"""Distributor sales & inventory: header infer, initial field mapping, gate checks, source mapping memory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ingestion.infer import infer_schema, read_tabular
from app.ingestion.pipeline import default_field_mapping, effective_mapping_template
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.distributor_sales_inventory import CANONICAL as DSI_CANONICAL
from app.services.imports.pm_mapping_memory import load_by_header_norm, norm_header_key
from app.storage.local import get_storage_backend

# Targets persisted in column_mapping_memory (same JSON shape as PM: {target, confirmations}).
DSI_MEMORY_TARGETS = frozenset(DSI_CANONICAL)


def _norm_header_lower(h: str) -> str:
    return (h or "").strip().lower()


def _looks_like_dealer_name_group_column(header: str) -> bool:
    """RAW-style account / rollup column (Dealer Name Group, dealer + group, etc.)."""
    k = _norm_header_lower(header)
    if not k:
        return False
    if k in ("dealer name group", "dealer_name_group", "dealer group", "dealer_group"):
        return True
    return "dealer" in k and "group" in k


def _looks_like_raw_source_customer_name_column(header: str) -> bool:
    """RAW-style source customer label column (Customer name); not the account rollup column."""
    k = _norm_header_lower(header)
    if not k or "to be mapped" in k:
        return False
    if _looks_like_dealer_name_group_column(header):
        return False
    if k in ("customer name", "customer_name"):
        return True
    if "customer" in k and "name" in k and "group" not in k and "dealer" not in k:
        return True
    return False


def apply_exact_raw_customer_header_overrides(headers: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """Force canonical RAW workbook customer columns regardless of learned memory or generic heuristics.

    Matches ``Customer name`` / ``Dealer Name Group`` (case- and norm-insensitive). Runs before fuzzy
    :func:`apply_dsi_customer_column_target_resolution` so extra customer-like headers do not block
    the primary RAW pair.
    """
    out = dict(mapping or {})
    dealer_h: str | None = None
    cust_h: str | None = None
    for h in headers:
        k = _norm_header_lower(h)
        nh = norm_header_key(h)
        if dealer_h is None and (nh == "dealer_name_group" or k in ("dealer name group", "dealer_name_group")):
            dealer_h = h
        if cust_h is None and (nh == "customer_name" or k in ("customer name", "customer_name")):
            cust_h = h
    if dealer_h is not None:
        out[dealer_h] = "dealer_group_token"
    if cust_h is not None:
        out[cust_h] = "customer_dealer_token"
    return out


def apply_dsi_customer_column_target_resolution(headers: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """Align RAW-style customer headers with DSI canonicals before sanitize.

    - Dealer Name Group (and similar) → dealer_group_token (Customer account in UI).
    - Customer name (and similar, excluding dealer+group headers) → customer_dealer_token (Source customer name).

    Runs after template defaults + optional header memory so legacy swaps and the shared
    ``name`` heuristic (``dealer name group`` contains ``name``) are corrected. Used on
    initial DSI infer and on pipeline auto-mapping when the job has no saved ``field_mapping``;
    saved job mappings from the admin UI are not reprocessed through this helper on validate/apply.
    """
    out = dict(mapping or {})
    dealer_cols = [h for h in headers if _looks_like_dealer_name_group_column(h)]
    cust_cols = [h for h in headers if _looks_like_raw_source_customer_name_column(h)]

    if len(dealer_cols) == 1 and len(cust_cols) == 1 and dealer_cols[0] != cust_cols[0]:
        out[dealer_cols[0]] = "dealer_group_token"
        out[cust_cols[0]] = "customer_dealer_token"
        return out

    if len(dealer_cols) == 1:
        out[dealer_cols[0]] = "dealer_group_token"
    if len(cust_cols) == 1 and not (len(dealer_cols) == 1 and cust_cols[0] == dealer_cols[0]):
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
    nk = norm_header_key(header)
    score = 0.0
    if nk in ("modelname", "model_name"):
        score += 12.0
    elif "model" in nk and "name" in nk:
        score += 10.0
    elif "model" in nk:
        score += 6.0
    if _samples_have_model_or_part_shape(samples):
        score += 22.0
    if nk == "product":
        score -= 6.0
        if _bare_product_header_looks_like_category_samples(header, samples):
            score -= 40.0
    return score


def apply_dsi_product_identifier_sample_inference(
    headers: list[str],
    mapping: dict[str, str],
    column_samples: dict[str, list[str]],
) -> dict[str, str]:
    """Adjust ``product_identifier`` auto-mapping using inferred column samples (mapping suggestions only).

    - Demotes bare ``PRODUCT`` when samples look like short category codes (e.g. NB), not model/SKU tokens.
    - When multiple columns map to ``product_identifier``, keeps the best-scoring column (prefers ModelName-style).
    - If nothing maps to ``product_identifier`` after demotion, assigns an unmapped column that strongly
      resembles a model/SKU column from header + samples.
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


def build_initial_dsi_field_mapping(
    db: Session,
    headers: list[str],
    source: SourceDefinition | None,
    template: dict[str, Any],
    *,
    column_samples: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Template + default_field_mapping, overlaid with saved per-header targets for this source."""
    memory = load_by_header_norm(source) if source else {}
    mapping: dict[str, str] = {}
    for h in headers:
        nh = norm_header_key(h)
        entry = memory.get(nh) if nh else None
        if isinstance(entry, dict):
            tgt = entry.get("target")
            if tgt and str(tgt).strip() and str(tgt) in DSI_MEMORY_TARGETS:
                mapping[h] = str(tgt)
    defaults = default_field_mapping(headers, template)
    for h, tgt in defaults.items():
        if h not in mapping:
            mapping[h] = tgt
    mapping = apply_exact_raw_customer_header_overrides(headers, mapping)
    mapping = apply_dsi_customer_column_target_resolution(headers, mapping)
    mapping = apply_dsi_product_identifier_sample_inference(headers, mapping, column_samples or {})
    sanitized, _ = sanitize_dsi_field_mapping(headers, mapping)
    return sanitized


def dsi_mapping_gate_errors(mapping: dict[str, str]) -> list[dict[str, str]]:
    """Blocking issues before running DSI pipeline (column mapping completeness)."""
    vals = set(mapping.values())
    errs: list[dict[str, str]] = []
    if "distributor_token" not in vals:
        errs.append(
            {
                "code": "missing_column_mapping_distributor",
                "message": "Required column mapping missing: Distributor.",
            }
        )
    if "product_identifier" not in vals:
        errs.append(
            {
                "code": "missing_column_mapping_product",
                "message": "Required column mapping missing: product identifier (SKU / part number / model / product code).",
            }
        )
    has_date = "transaction_date" in vals or "snapshot_date" in vals
    if not has_date:
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
    """Read stored raw file, infer headers, set initial field_mapping + file_headers (no DSI pipeline run)."""
    job = db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job or job.template_slug != "distributor_inventory":
        raise ValueError("infer_dsi_job_sync requires a distributor_inventory import job")

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    storage = get_storage_backend()
    data = storage.read(raw.storage_key)

    df = read_tabular(job.file_name, data)
    schema = infer_schema(df)
    cols = [c["name"] for c in schema["columns"]]

    source = job.source
    template = effective_mapping_template(source)
    samples = column_samples_from_schema_dict(schema)
    mapping = build_initial_dsi_field_mapping(db, cols, source, template, column_samples=samples)

    from app.services.imports.dsi_column_mapping_intel import apply_high_confidence_dsi_automap

    mapping, auto_applied = apply_high_confidence_dsi_automap(cols, source, mapping, column_samples=samples)

    job.inferred_schema = {**schema, "dsi_column_automap_applied": auto_applied}
    job.file_headers = cols
    job.field_mapping = mapping
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

    headers = list(job.file_headers or [])
    raw_mapping = dict(job.field_mapping or {})
    mapping, notices = sanitize_dsi_field_mapping(headers, raw_mapping)
    gate = dsi_mapping_gate_errors(mapping)
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
        "column_samples": samples,
        "mapping_adjustment_notices": notices,
        "field_target_descriptions": dict(DSI_FIELD_TARGET_DESCRIPTIONS),
    }
