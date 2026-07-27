"""Deterministic entity resolution for historical CPOR staging (never auto-create)."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor_historical import ImportCporHistoricalStagingLine
from app.models.dimensions import DimCustomer, DimDistributor
from app.services.cpor.claim_evidence import load_product_resolution_index, resolve_claim_product_id
from app.services.cpor.historical_import.token_surrogate import get_or_create_token_surrogate
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    ProductResolutionProductRow,
    _product_token_key,
)

PlanClass = Literal["ready_to_map", "ambiguous_eligible", "no_match", "needs_review"]

# Align with web confidenceBand / AI_AUTO_RESOLVE_THRESHOLD.
_HIGH_SCORE = 0.90
_MEDIUM_SCORE = 0.70
_MAX_SUGGESTIONS = 5
_MIN_PREFIX_LEN = 3

PLAN_CLASS_ORDER: tuple[PlanClass, ...] = (
    "ready_to_map",
    "ambiguous_eligible",
    "needs_review",
    "no_match",
)


def _norm(token: str | None) -> str:
    return " ".join(str(token or "").strip().upper().split())


def _load_party_token_index(
    db: Session, *, model: type[DimCustomer] | type[DimDistributor]
) -> tuple[dict[str, list[int]], dict[int, str]]:
    idx: dict[str, list[int]] = defaultdict(list)
    labels: dict[int, str] = {}
    for did, code, name in db.execute(select(model.id, model.code, model.name)).all():
        dim_id = int(did)
        label = (str(name or "").strip() or str(code or "").strip() or str(dim_id))
        labels[dim_id] = label
        for raw in (code, name):
            key = _norm(raw)
            if key and dim_id not in idx[key]:
                idx[key].append(dim_id)
    return idx, labels


def _load_customer_token_index(db: Session) -> dict[str, list[int]]:
    idx, _labels = _load_party_token_index(db, model=DimCustomer)
    return idx


def _load_distributor_token_index(db: Session) -> dict[str, list[int]]:
    idx, _labels = _load_party_token_index(db, model=DimDistributor)
    return idx


def _product_label(row: ProductResolutionProductRow | None, dim_id: int) -> str:
    if row is None:
        return str(dim_id)
    return (
        (row.sales_model_name or "").strip()
        or (row.marketing_name or "").strip()
        or (row.model_name or "").strip()
        or (row.sku or "").strip()
        or str(dim_id)
    )


def _suggestion(dim_id: int, label: str, score: float, reason: str) -> dict[str, Any]:
    return {
        "dim_id": int(dim_id),
        "label": label,
        "score": round(float(score), 4),
        "reason": reason,
    }


def _score_fuzzy_key(token_key: str, index_key: str) -> tuple[float, str] | None:
    """Deterministic prefix / similarity score. None = below medium bar."""
    if not token_key or not index_key or token_key == index_key:
        return None
    if len(token_key) >= _MIN_PREFIX_LEN and (
        index_key.startswith(token_key) or token_key.startswith(index_key)
    ):
        return 0.92, "prefix_match"
    ratio = SequenceMatcher(None, token_key, index_key).ratio()
    if ratio >= _HIGH_SCORE:
        return float(ratio), "fuzzy_high"
    if ratio >= _MEDIUM_SCORE:
        return float(ratio), "fuzzy_medium"
    return None


def _fuzzy_suggestions_from_index(
    *,
    token_key: str,
    key_to_ids: dict[str, list[int]] | dict[str, tuple[int, ...]],
    labels: dict[int, str],
) -> list[dict[str, Any]]:
    best: dict[int, dict[str, Any]] = {}
    for index_key, raw_ids in key_to_ids.items():
        scored = _score_fuzzy_key(token_key, str(index_key))
        if scored is None:
            continue
        score, reason = scored
        for dim_id in raw_ids:
            did = int(dim_id)
            prev = best.get(did)
            if prev is None or score > float(prev["score"]):
                best[did] = _suggestion(did, labels.get(did, str(did)), score, reason)
    ranked = sorted(best.values(), key=lambda s: (-float(s["score"]), int(s["dim_id"])))
    return ranked[:_MAX_SUGGESTIONS]


def _classify_from_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    forced_class: PlanClass | None = None,
) -> tuple[PlanClass, float | None, str | None]:
    if forced_class is not None:
        top = suggestions[0] if suggestions else None
        return (
            forced_class,
            float(top["score"]) if top else None,
            str(top["reason"]) if top else None,
        )
    if not suggestions:
        return "no_match", None, None
    top = suggestions[0]
    confidence = float(top["score"])
    match_reason = str(top["reason"])
    high = [s for s in suggestions if float(s["score"]) >= _HIGH_SCORE]
    if len(high) == 1:
        return "ready_to_map", confidence, match_reason
    return "needs_review", confidence, match_reason


def suggest_party_token(
    token: str,
    *,
    index: dict[str, list[int]],
    labels: dict[int, str],
) -> dict[str, Any]:
    """Ranked suggestions + plan_class for a customer/distributor token (never creates dims)."""
    key = _norm(token)
    exact_ids = list(index.get(key) or [])
    if len(exact_ids) > 1:
        suggestions = [
            _suggestion(did, labels.get(did, str(did)), 1.0, "exact_key_collision")
            for did in exact_ids
        ]
        plan_class, confidence, match_reason = _classify_from_suggestions(
            suggestions, forced_class="ambiguous_eligible"
        )
    elif len(exact_ids) == 1:
        did = exact_ids[0]
        suggestions = [_suggestion(did, labels.get(did, str(did)), 1.0, "exact_key")]
        plan_class, confidence, match_reason = _classify_from_suggestions(
            suggestions, forced_class="ready_to_map"
        )
    else:
        suggestions = _fuzzy_suggestions_from_index(
            token_key=key, key_to_ids=index, labels=labels
        )
        plan_class, confidence, match_reason = _classify_from_suggestions(suggestions)
    return {
        "suggestions": suggestions,
        "confidence": confidence,
        "plan_class": plan_class,
        "match_reason": match_reason,
    }


def _product_exact_ids(
    product_index: ProductResolutionIndex, token: str
) -> tuple[list[int], str]:
    """Return (ids, tier_reason) for exact identity hits used by claim resolve."""
    sm_key = _product_token_key(token)
    sm_ids = [int(x) for x in (product_index.sales_model_name_to_ids.get(sm_key) or ())]
    if len(sm_ids) >= 1:
        return sm_ids, "sales_model_name"

    _pid, _tok, status = resolve_claim_product_id(product_index, item_code=token)
    if status == "ambiguous":
        sku_key = _product_token_key(token)
        part_ids = [int(x) for x in (product_index.part_number_to_ids.get(sku_key) or ())]
        if part_ids:
            return part_ids, "part_number"
    if status == "resolved" and _pid is not None:
        return [int(_pid)], "item_code"
    return [], "none"


def suggest_product_token(token: str, *, product_index: ProductResolutionIndex) -> dict[str, Any]:
    """Ranked suggestions + plan_class for a sales-model token (never creates dims)."""
    labels = {
        pid: _product_label(row, pid) for pid, row in product_index.products_by_id.items()
    }
    exact_ids, tier = _product_exact_ids(product_index, token)
    if len(exact_ids) > 1:
        suggestions = [
            _suggestion(did, labels.get(did, str(did)), 1.0, f"exact_key_collision:{tier}")
            for did in exact_ids
        ]
        plan_class, confidence, match_reason = _classify_from_suggestions(
            suggestions, forced_class="ambiguous_eligible"
        )
    elif len(exact_ids) == 1:
        did = exact_ids[0]
        suggestions = [_suggestion(did, labels.get(did, str(did)), 1.0, f"exact_key:{tier}")]
        plan_class, confidence, match_reason = _classify_from_suggestions(
            suggestions, forced_class="ready_to_map"
        )
    else:
        # Bounded fuzzy over sales-model / model / marketing identity maps only.
        merged: dict[str, list[int]] = defaultdict(list)
        for mmap in (
            product_index.sales_model_name_to_ids,
            product_index.model_name_to_ids,
            product_index.marketing_name_to_ids,
        ):
            for k, ids in mmap.items():
                for did in ids:
                    if int(did) not in merged[str(k)]:
                        merged[str(k)].append(int(did))
        suggestions = _fuzzy_suggestions_from_index(
            token_key=_product_token_key(token),
            key_to_ids=merged,
            labels=labels,
        )
        plan_class, confidence, match_reason = _classify_from_suggestions(suggestions)
    return {
        "suggestions": suggestions,
        "confidence": confidence,
        "plan_class": plan_class,
        "match_reason": match_reason,
    }


def enrich_unresolved_candidate(
    *,
    entity: str,
    token: str,
    row_count: int,
    product_index: ProductResolutionIndex | None = None,
    customer_index: dict[str, list[int]] | None = None,
    customer_labels: dict[int, str] | None = None,
    distributor_index: dict[str, list[int]] | None = None,
    distributor_labels: dict[int, str] | None = None,
    candidate_id: int | None = None,
    sample_raw_values: list[str] | None = None,
    case_codes: list[str] | None = None,
    total_units: float | None = None,
    total_reported_value: float | None = None,
) -> dict[str, Any]:
    """Build one steward candidate dict with suggestions / plan_class (no DB writes).

    ``candidate_id`` (Unit C, D-014) is the stable numeric token-surrogate id — callers that
    already resolved/created one (e.g. :func:`list_unresolved_candidates`) pass it through so
    it lands on the returned dict as ``"id"``. ``sample_raw_values`` / ``case_codes`` /
    ``total_units`` / ``total_reported_value`` are optional S6/S4 enrichment aggregates from
    staging lines (Unit C Phase 2) — omitted fields default to empty/``None``.
    """
    entity_l = entity.strip().lower()
    if entity_l == "product":
        if product_index is None:
            raise ValueError("product_index required")
        intel = suggest_product_token(token, product_index=product_index)
    elif entity_l == "customer":
        intel = suggest_party_token(
            token,
            index=customer_index or {},
            labels=customer_labels or {},
        )
    elif entity_l == "distributor":
        intel = suggest_party_token(
            token,
            index=distributor_index or {},
            labels=distributor_labels or {},
        )
    else:
        raise ValueError(f"unsupported entity: {entity}")

    return {
        "id": int(candidate_id) if candidate_id is not None else None,
        "entity": entity_l,
        "token": token,
        "row_count": int(row_count),
        "status": "unresolved",
        "confidence": intel["confidence"],
        "plan_class": intel["plan_class"],
        "match_reason": intel["match_reason"],
        "suggestions": intel["suggestions"],
        "sample_raw_values": list(sample_raw_values) if sample_raw_values else [],
        "case_codes": list(case_codes) if case_codes else [],
        "total_units": total_units,
        "total_reported_value": total_reported_value,
    }


def plan_class_counts(
    candidates_by_entity: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    """Per-entity plan_class breakdown for summary / queue chips."""
    out: dict[str, dict[str, int]] = {}
    for entity, rows in candidates_by_entity.items():
        counts = {pc: 0 for pc in PLAN_CLASS_ORDER}
        for row in rows:
            pc = str(row.get("plan_class") or "needs_review")
            if pc not in counts:
                counts[pc] = 0
            counts[pc] += 1
        out[entity] = counts
    return out


def resolve_staging_entities(db: Session, *, job_id: int) -> dict[str, Any]:
    """Fill resolved_*_id where an exact single match exists. Never creates dims."""
    rows = list(
        db.scalars(
            select(ImportCporHistoricalStagingLine).where(
                ImportCporHistoricalStagingLine.import_job_id == job_id
            )
        ).all()
    )
    if not rows:
        return {"rows": 0, "products_resolved": 0, "customers_resolved": 0, "distributors_resolved": 0}

    product_index = load_product_resolution_index(db)
    customers = _load_customer_token_index(db)
    distributors = _load_distributor_token_index(db)

    p_n = c_n = d_n = 0
    for row in rows:
        if row.resolved_product_id is None and row.sales_model_token:
            pid, _tok, status = resolve_claim_product_id(
                product_index, sales_model=row.sales_model_token
            )
            if status == "resolved" and pid is not None:
                row.resolved_product_id = pid
                p_n += 1

        if row.resolved_customer_id is None and row.customer_token:
            ids = customers.get(_norm(row.customer_token)) or []
            if len(ids) == 1:
                row.resolved_customer_id = ids[0]
                c_n += 1

        if row.resolved_distributor_id is None and row.distributor_token:
            ids = distributors.get(_norm(row.distributor_token)) or []
            if len(ids) == 1:
                row.resolved_distributor_id = ids[0]
                d_n += 1

    db.flush()
    return {
        "rows": len(rows),
        "products_resolved": p_n,
        "customers_resolved": c_n,
        "distributors_resolved": d_n,
    }


def map_staging_token(
    db: Session,
    *,
    job_id: int,
    entity: str,
    token: str,
    dim_id: int,
) -> int:
    """Steward map: set resolved_*_id for all staging rows matching token. Returns updated count."""
    return map_staging_tokens(db, job_id=job_id, entity=entity, tokens=[token], dim_id=dim_id)


def map_staging_tokens(
    db: Session,
    *,
    job_id: int,
    entity: str,
    tokens: list[str],
    dim_id: int,
) -> int:
    """Bulk steward map: one dim_id applied to many tokens of the same entity."""
    entity_l = entity.strip().lower()
    wanted = {_norm(t) for t in tokens if (t or "").strip()}
    if not wanted:
        return 0

    q = select(ImportCporHistoricalStagingLine).where(
        ImportCporHistoricalStagingLine.import_job_id == job_id
    )
    rows = list(db.scalars(q).all())
    updated = 0
    for row in rows:
        if entity_l == "product" and _norm(row.sales_model_token) in wanted:
            row.resolved_product_id = dim_id
            updated += 1
        elif entity_l == "customer" and _norm(row.customer_token) in wanted:
            row.resolved_customer_id = dim_id
            updated += 1
        elif entity_l == "distributor" and _norm(row.distributor_token) in wanted:
            row.resolved_distributor_id = dim_id
            updated += 1
    db.flush()
    return updated


def _new_token_aggregate() -> dict[str, Any]:
    return {
        "row_count": 0,
        "samples": [],
        "case_codes": set(),
        "total_units": 0.0,
        "total_reported_value": 0.0,
        "has_reported_value": False,
    }


def _raw_sample_for_token(row: ImportCporHistoricalStagingLine, token: str) -> str:
    """Best-effort original (un-normalized) raw value for ``token`` from the source row.

    Falls back to the resolved token string itself when no raw value round-trips to the
    same normalized key (e.g. tenant column-map surprises) — never blocks enrichment.
    """
    norm_token = _norm(token)
    raw = row.raw_source_row if isinstance(row.raw_source_row, dict) else {}
    for value in raw.values():
        if isinstance(value, str) and _norm(value) == norm_token:
            return value.strip()
    return token


def _accumulate_token(agg: dict[str, Any], row: ImportCporHistoricalStagingLine, token: str) -> None:
    agg["row_count"] += 1
    if len(agg["samples"]) < 3:
        sample = _raw_sample_for_token(row, token)
        if sample and sample not in agg["samples"]:
            agg["samples"].append(sample)
    code = (row.case_code or "").strip()
    if code:
        agg["case_codes"].add(code)
    unit_val = row.result_qty if row.result_qty is not None else row.estimate_qty
    if unit_val is not None:
        agg["total_units"] += float(unit_val)
    if row.ttl_result_usd is not None:
        agg["total_reported_value"] += float(row.ttl_result_usd)
        agg["has_reported_value"] = True


def list_unresolved_candidates(db: Session, *, job_id: int) -> dict[str, list[dict[str, Any]]]:
    """Group unresolved tokens for steward workspace tabs — with ranked suggestions.

    Also get-or-creates a stable numeric token-surrogate id per (entity, token) — see
    :func:`app.services.cpor.historical_import.token_surrogate.get_or_create_token_surrogate`
    (Unit C, D-014). Callers own the transaction; commit to persist newly created surrogate
    rows (they are flushed via a SAVEPOINT so a race is harmless, but remain uncommitted
    until the caller commits).
    """
    rows = list(
        db.scalars(
            select(ImportCporHistoricalStagingLine).where(
                ImportCporHistoricalStagingLine.import_job_id == job_id,
                ImportCporHistoricalStagingLine.skip_apply.is_(False),
            )
        ).all()
    )
    products: dict[str, dict[str, Any]] = defaultdict(_new_token_aggregate)
    customers: dict[str, dict[str, Any]] = defaultdict(_new_token_aggregate)
    distributors: dict[str, dict[str, Any]] = defaultdict(_new_token_aggregate)
    for row in rows:
        if row.sales_model_token and row.resolved_product_id is None:
            tok = str(row.sales_model_token).strip()
            _accumulate_token(products[tok], row, tok)
        if row.customer_token and row.resolved_customer_id is None:
            tok = str(row.customer_token).strip()
            _accumulate_token(customers[tok], row, tok)
        if row.distributor_token and row.resolved_distributor_id is None:
            tok = str(row.distributor_token).strip()
            _accumulate_token(distributors[tok], row, tok)

    product_index = load_product_resolution_index(db) if products else None
    customer_index, customer_labels = (
        _load_party_token_index(db, model=DimCustomer) if customers else ({}, {})
    )
    distributor_index, distributor_labels = (
        _load_party_token_index(db, model=DimDistributor) if distributors else ({}, {})
    )

    def _pack(d: dict[str, dict[str, Any]], entity: str) -> list[dict[str, Any]]:
        packed: list[dict[str, Any]] = []
        for tok, agg in sorted(d.items(), key=lambda x: (-x[1]["row_count"], x[0].lower())):
            candidate_id = get_or_create_token_surrogate(db, job_id=job_id, entity=entity, token=tok)
            packed.append(
                enrich_unresolved_candidate(
                    entity=entity,
                    token=tok,
                    row_count=agg["row_count"],
                    product_index=product_index,
                    customer_index=customer_index,
                    customer_labels=customer_labels,
                    distributor_index=distributor_index,
                    distributor_labels=distributor_labels,
                    candidate_id=candidate_id,
                    sample_raw_values=agg["samples"],
                    case_codes=sorted(agg["case_codes"]),
                    total_units=round(agg["total_units"], 4),
                    total_reported_value=(
                        round(agg["total_reported_value"], 4) if agg["has_reported_value"] else None
                    ),
                )
            )
        return packed

    return {
        "product": _pack(products, "product"),
        "customer": _pack(customers, "customer"),
        "distributor": _pack(distributors, "distributor"),
    }


def case_apply_blockers(row: ImportCporHistoricalStagingLine) -> list[str]:
    """Hard blockers for a staging line's case (FLAG≠BLOCK: parity alone does not block)."""
    blockers: list[str] = []
    flags = list((row.flags_json or {}).get("flags") or [])
    for f in (
        "case_code_collision_native",
        "duplicate_line_grain",
        "missing_window",
        "missing_customer_token",
        "missing_product_token",
    ):
        if f in flags:
            blockers.append(f)
    if row.resolved_product_id is None:
        blockers.append("unresolved_product")
    if row.resolved_customer_id is None:
        blockers.append("unresolved_customer")
    if (row.distributor_token or "").strip() and row.resolved_distributor_id is None:
        blockers.append("unresolved_distributor")
    if not row.window_start or not row.window_end:
        blockers.append("missing_window")
    return sorted(set(blockers))
