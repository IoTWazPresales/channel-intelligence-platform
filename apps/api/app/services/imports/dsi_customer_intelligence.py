"""DSI customer duplicate hints and cross-job resolution signals (no embedding models)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_customer_name_normalization import (
    DSI_DUPLICATE_FULL_STRING_THRESHOLD,
    evaluate_dealer_group_duplicate,
    dsi_duplicate_similarity_score,
    normalize_customer_name_for_similarity,
    normalize_customer_name_token,
)
from app.services.imports.provisional_entity_identity import customer_source_token_alias_key


def _norm_key(s: str | None) -> str:
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

# Default full-string threshold (distinctive stem must pass first — see ``dsi_duplicate_similarity_score``).
DSI_DUPLICATE_SIMILARITY_THRESHOLD: float = DSI_DUPLICATE_FULL_STRING_THRESHOLD

_STEWARD_RESOLVED_REASONS = frozenset(
    {
        "steward_created_provisional_customer",
        "steward_map_existing_customer",
    }
)


@dataclass(frozen=True)
class HistoricalCustomerResolution:
    customer_id: int
    import_job_id: int
    match_reason: str | None
    confidence: float
    resolution_kind: str  # historical_steward | historical_alias


@dataclass(frozen=True)
class JobCustomerSiblingMapping:
    normalized_key: str
    customer_id: int
    match_reason: str | None


def _sellout_distributor_id_set(data: dict[str, Any]) -> set[int]:
    raw = data.get("sellout_distributor_ids")
    if isinstance(raw, set):
        return {int(x) for x in raw}
    if isinstance(raw, (list, tuple)):
        return {int(x) for x in raw}
    return set()


def _duplicate_distributor_scope_allows_compare(da: dict[str, Any], db: dict[str, Any]) -> bool:
    """Only flag duplicates when sell-out distributor scope overlaps (reduces cross-distributor false positives)."""
    ids_a = _sellout_distributor_id_set(da)
    ids_b = _sellout_distributor_id_set(db)
    if not ids_a and not ids_b:
        return True
    if not ids_a or not ids_b:
        return False
    return bool(ids_a & ids_b)


def duplicate_review_decision(ctx: dict[str, Any] | None) -> str | None:
    if not isinstance(ctx, dict):
        return None
    dr = ctx.get("duplicate_review")
    if not isinstance(dr, dict):
        return None
    dec = dr.get("decision")
    return str(dec).strip() if dec is not None and str(dec).strip() else None


def dsi_candidate_duplicate_review_unresolved(cand: ImportEntityMappingCandidate) -> bool:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    hints = ctx.get("possible_duplicate_of")
    if not isinstance(hints, list) or len(hints) == 0:
        return False
    return duplicate_review_decision(ctx) is None


def gate_dsi_plan_row_duplicate_review(
    cand: ImportEntityMappingCandidate, row: dict[str, Any]
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        return row
    if not dsi_candidate_duplicate_review_unresolved(cand):
        return row
    blockers = [str(b) for b in (row.get("resolution_blockers") or []) if b]
    if "duplicate_review_required" not in blockers:
        blockers.append("duplicate_review_required")
    return {
        **row,
        "ready": False,
        "plan_status": "needs_review",
        "resolution_blockers": blockers,
        "duplicate_review_required": True,
        "reason": (
            str(row.get("reason") or "")
            + (" — " if row.get("reason") else "")
            + "Possible duplicate name match in this job — confirm same or different entity before applying"
        ).strip(),
    }


def _display_name_for_customer_agg(data: dict[str, Any]) -> str:
    dg = (data.get("dealer_group_raw") or "").strip()
    if dg:
        return dg
    samples = data.get("source_customer_raw_samples") or []
    if isinstance(samples, list):
        for s in samples:
            if isinstance(s, str) and s.strip():
                return s.strip()
    return ""


# Source-customer duplicate path — aligned with ``SENTINEL_CUSTOMER_TOKENS`` in distributor_sales_inventory.
_SOURCE_CUSTOMER_DUPLICATE_PLACEHOLDER_SUBSTRINGS = (
    "to be mapped",
    "tbd",
    "unknown",
    "pending mapping",
)
_SOURCE_CUSTOMER_DUPLICATE_SENTINELS = frozenset(
    {
        "cash sale",
        "end user",
        "consumer",
        "walk-in",
        "walk in",
        "unknown",
        "dealer",
        "misc",
        "n/a",
        "na",
        "tbd",
        "__blank__",
    }
)


def _source_customer_norm_is_placeholder(norm: str, raw: str | None = None) -> bool:
    if not norm or norm in _SOURCE_CUSTOMER_DUPLICATE_SENTINELS:
        return True
    r = (raw or "").strip().lower()
    return any(p in r for p in _SOURCE_CUSTOMER_DUPLICATE_PLACEHOLDER_SUBSTRINGS)


def _source_customer_evidence_norm_set(data: dict[str, Any]) -> set[str]:
    norms: set[str] = set()
    for item in data.get("source_customer_evidence_norms") or []:
        if not isinstance(item, str) or not item.strip():
            continue
        norm = item.strip()
        if not _source_customer_norm_is_placeholder(norm):
            norms.add(norm)
    for raw in data.get("source_customer_raw_samples") or []:
        if not isinstance(raw, str) or not raw.strip():
            continue
        norm = normalize_customer_name_token(raw)
        if norm and not _source_customer_norm_is_placeholder(norm, raw):
            norms.add(norm)
    return norms


def _dealer_group_display_norm(data: dict[str, Any]) -> str:
    dg = (data.get("dealer_group_raw") or "").strip()
    if not dg:
        return ""
    return normalize_customer_name_for_similarity(dg)


def _build_distributor_name_norm_index(distributors: list[Any]) -> frozenset[str]:
    norms: set[str] = set()
    for dist in distributors:
        dist_name = str(getattr(dist, "name", "") or "").strip()
        if not dist_name:
            continue
        for raw in (dist_name, str(getattr(dist, "code", "") or "")):
            norm = normalize_customer_name_for_similarity(raw)
            if len(norm) >= 4:
                norms.add(norm)
    return frozenset(norms)


def _dealer_group_shared_label_different_counterparty(
    da: dict[str, Any], db: dict[str, Any]
) -> tuple[float, str, str] | None:
    """Same dealer-group label in file with different source-customer strings — steward must confirm."""
    dg_a = _dealer_group_display_norm(da)
    dg_b = _dealer_group_display_norm(db)
    if not dg_a or dg_a != dg_b:
        return None
    sa = _source_customer_evidence_norm_set(da)
    sb = _source_customer_evidence_norm_set(db)
    if not sa or not sb or sa == sb:
        return None
    return (
        0.92,
        dg_a,
        "Same dealer-group label with different counterparty strings in file — confirm same legal entity or branch",
    )


def _best_source_customer_similar_score(sa: set[str], sb: set[str]) -> float | None:
    best: float | None = None
    for a in sa:
        for b in sb:
            if a == b:
                continue
            score = dsi_duplicate_similarity_score(a, b)
            if score is None:
                continue
            if best is None or score > best:
                best = score
    return best


def _shared_source_customer_exact_norm(
    da: dict[str, Any], db: dict[str, Any], *, distributor_norms: frozenset[str]
) -> str | None:
    sa = _source_customer_evidence_norm_set(da)
    sb = _source_customer_evidence_norm_set(db)
    if not sa or not sb:
        return None
    shared = sa & sb
    if len(shared) != 1:
        return None
    norm = next(iter(shared))
    if norm in distributor_norms:
        return None
    return norm


def annotate_dsi_customer_distributor_name_collisions(
    agg: dict[tuple[str, str], dict[str, Any]],
    distributors: list[Any],
) -> None:
    """Flag customer tokens whose normalised name matches a ``dim_distributor`` (inter-disti counterparty hint)."""
    by_norm: dict[str, dict[str, Any]] = {}
    for dist in distributors:
        dist_id = int(getattr(dist, "id", 0) or 0)
        dist_name = str(getattr(dist, "name", "") or "").strip()
        if not dist_id or not dist_name:
            continue
        for raw in (dist_name, str(getattr(dist, "code", "") or "")):
            norm = normalize_customer_name_for_similarity(raw)
            if len(norm) < 4:
                continue
            if norm not in by_norm:
                by_norm[norm] = {"distributor_id": dist_id, "distributor_name": dist_name}

    for (etype, nkey), data in agg.items():
        if etype != "customer_dealer_token":
            continue
        keys_to_try: list[str] = []
        nk = (nkey or "").strip().lower()
        if nk and nk != "__blank__":
            keys_to_try.append(nk)
        display = _display_name_for_customer_agg(data)
        dn = normalize_customer_name_token(display)
        if dn and dn not in keys_to_try:
            keys_to_try.append(dn)
        for k in keys_to_try:
            hit = by_norm.get(k)
            if hit:
                data["distributor_master_collision"] = dict(hit)
                break


def annotate_dsi_customer_candidate_duplicates(
    agg: dict[tuple[str, str], dict[str, Any]],
    *,
    similarity_threshold: float = DSI_DUPLICATE_SIMILARITY_THRESHOLD,
    distributors: list[Any] | None = None,
) -> None:
    """Set ``possible_duplicate_of`` on customer_dealer_token buckets (pre-persist)."""
    distributor_norms = _build_distributor_name_norm_index(distributors or [])
    items = [
        (nk, data)
        for (etype, nk), data in agg.items()
        if etype == "customer_dealer_token"
    ]
    for i, (nk_a, da) in enumerate(items):
        name_a = _display_name_for_customer_agg(da)
        if not name_a.strip():
            continue
        for nk_b, db in items[i + 1 :]:
            if not _duplicate_distributor_scope_allows_compare(da, db):
                continue
            name_b = _display_name_for_customer_agg(db)
            if not name_b.strip():
                continue
            scope = sorted(_sellout_distributor_id_set(da) | _sellout_distributor_id_set(db)) or None
            shared_label = _dealer_group_shared_label_different_counterparty(da, db)
            if shared_label is not None:
                score, dg_norm, reason = shared_label
                _append_duplicate_hint(
                    da,
                    nk_b,
                    score,
                    match_basis="dealer_group_shared_label_different_counterparty",
                    dealer_group_norm=dg_norm,
                    distributor_scope=scope,
                    evidence_reason=reason,
                )
                _append_duplicate_hint(
                    db,
                    nk_a,
                    score,
                    match_basis="dealer_group_shared_label_different_counterparty",
                    dealer_group_norm=dg_norm,
                    distributor_scope=scope,
                    evidence_reason=reason,
                )
                continue
            dealer_eval = evaluate_dealer_group_duplicate(
                name_a,
                name_b,
                full_string_threshold=similarity_threshold,
            )
            if dealer_eval is not None:
                _append_duplicate_hint(
                    da,
                    nk_b,
                    dealer_eval.score,
                    match_basis=dealer_eval.match_basis,
                    distributor_scope=scope,
                )
                _append_duplicate_hint(
                    db,
                    nk_a,
                    dealer_eval.score,
                    match_basis=dealer_eval.match_basis,
                    distributor_scope=scope,
                )
                continue
            shared_customer = _shared_source_customer_exact_norm(
                da, db, distributor_norms=distributor_norms
            )
            if shared_customer is not None:
                _append_duplicate_hint(
                    da,
                    nk_b,
                    1.0,
                    match_basis="source_customer_exact",
                    source_customer_norm=shared_customer,
                    distributor_scope=scope,
                )
                _append_duplicate_hint(
                    db,
                    nk_a,
                    1.0,
                    match_basis="source_customer_exact",
                    source_customer_norm=shared_customer,
                    distributor_scope=scope,
                )
                continue
            sa = _source_customer_evidence_norm_set(da)
            sb = _source_customer_evidence_norm_set(db)
            sim_score = _best_source_customer_similar_score(sa, sb) if sa and sb else None
            if sim_score is not None:
                _append_duplicate_hint(
                    da,
                    nk_b,
                    sim_score,
                    match_basis="source_customer_similar",
                    distributor_scope=scope,
                    evidence_reason="Similar source-customer counterparty strings — confirm same or different entity",
                )
                _append_duplicate_hint(
                    db,
                    nk_a,
                    sim_score,
                    match_basis="source_customer_similar",
                    distributor_scope=scope,
                    evidence_reason="Similar source-customer counterparty strings — confirm same or different entity",
                )


def build_duplicate_review_record(
    *,
    decision: str,
    paired_normalized_key: str,
    similarity_score: float | None,
    customer_id: int | None = None,
    audit_note: str | None = None,
    hints_snapshot: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "paired_normalized_key": paired_normalized_key,
        "similarity_score": similarity_score,
        "customer_id": customer_id,
        "audit_note": (audit_note or "").strip()[:2000] or None,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "hints_at_decision": list(hints_snapshot or [])[:16],
    }


def similarity_score_for_duplicate_peer(ctx: dict[str, Any], peer_normalized_key: str) -> float | None:
    hints = ctx.get("possible_duplicate_of")
    if not isinstance(hints, list):
        return None
    nk = (peer_normalized_key or "").strip()
    for h in hints:
        if isinstance(h, dict) and str(h.get("normalized_key") or "").strip() == nk:
            try:
                return float(h.get("similarity_score"))
            except (TypeError, ValueError):
                return None
    return None


def _append_duplicate_hint(
    bucket: dict[str, Any],
    other_normalized_key: str,
    score: float,
    *,
    match_basis: str | None = None,
    matched_value: str | None = None,
    matched_field: str | None = None,
    dealer_group_norm: str | None = None,
    source_customer_norm: str | None = None,
    distributor_scope: list[int] | None = None,
    evidence_reason: str | None = None,
) -> None:
    from app.services.imports.dsi_duplicate_hint_contract import (
        DUPLICATE_HINT_OPTIONAL_EVIDENCE_KEYS,
        build_duplicate_hint_entry,
    )

    hints: list[dict[str, Any]] = bucket.setdefault("possible_duplicate_of", [])
    if not isinstance(hints, list):
        hints = []
        bucket["possible_duplicate_of"] = hints
    entry = build_duplicate_hint_entry(
        normalized_key=other_normalized_key,
        similarity_score=score,
        match_basis=match_basis,
        matched_value=matched_value,
        matched_field=matched_field,
        dealer_group_norm=dealer_group_norm,
        source_customer_norm=source_customer_norm,
        distributor_scope=distributor_scope,
        evidence_reason=evidence_reason,
    )
    basis = entry.get("match_basis")
    for h in hints:
        if isinstance(h, dict) and h.get("normalized_key") == other_normalized_key:
            if float(h.get("similarity_score") or 0) < score:
                h["similarity_score"] = entry["similarity_score"]
                if basis:
                    h["match_basis"] = basis
            elif basis and not h.get("match_basis"):
                h["match_basis"] = basis
            for key in DUPLICATE_HINT_OPTIONAL_EVIDENCE_KEYS:
                if key in entry and key not in h:
                    h[key] = entry[key]
            return
    hints.append(entry)


def load_historical_customer_resolutions(
    session: Session,
    *,
    source_definition_id: int | None,
    current_job_id: int,
) -> dict[tuple[int | None, str], HistoricalCustomerResolution]:
    """Preload best prior steward/alias resolutions keyed by (distributor_id, normalized_key)."""
    out: dict[tuple[int | None, str], HistoricalCustomerResolution] = {}
    if source_definition_id is None:
        return out

    dom_col = ImportEntityMappingCandidate.context["dominant_distributor_id"].astext
    cand_rows = session.execute(
        select(
            ImportEntityMappingCandidate.normalized_key,
            ImportEntityMappingCandidate.suggested_entity_id,
            ImportEntityMappingCandidate.match_reason,
            ImportEntityMappingCandidate.import_job_id,
            ImportJob.completed_at,
            dom_col,
        )
        .join(ImportJob, ImportJob.id == ImportEntityMappingCandidate.import_job_id)
        .where(
            ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            ImportEntityMappingCandidate.source_definition_id == int(source_definition_id),
            ImportEntityMappingCandidate.import_job_id != int(current_job_id),
            ImportEntityMappingCandidate.status == "resolved",
            ImportEntityMappingCandidate.suggested_entity_id.isnot(None),
        )
        .order_by(ImportJob.completed_at.desc().nullslast(), ImportEntityMappingCandidate.id.desc())
        .limit(5000)
    ).all()

    for nk, cid, reason, jid, _completed, dom_raw in cand_rows:
        key = nk if isinstance(nk, str) else str(nk or "")
        if not key or cid is None:
            continue
        dist_key: int | None = None
        if dom_raw is not None and str(dom_raw).strip().isdigit():
            dist_key = int(str(dom_raw).strip())
        nk_norm = _norm_key(key)
        slot_scoped = (dist_key, nk_norm)
        if dist_key is not None and slot_scoped not in out:
            mr = (reason or "").strip()
            out[slot_scoped] = HistoricalCustomerResolution(
                customer_id=int(cid),
                import_job_id=int(jid),
                match_reason=mr or None,
                confidence=0.94 if mr in _STEWARD_RESOLVED_REASONS else 0.88,
                resolution_kind="historical_steward",
            )
        slot_global = (None, nk_norm)
        if slot_global in out:
            continue
        mr = (reason or "").strip()
        out[slot_global] = HistoricalCustomerResolution(
            customer_id=int(cid),
            import_job_id=int(jid),
            match_reason=mr or None,
            confidence=0.94 if mr in _STEWARD_RESOLVED_REASONS else 0.88,
            resolution_kind="historical_steward",
        )

    alias_rows = session.scalars(
        select(CustomerSourceTokenAlias).where(
            CustomerSourceTokenAlias.status == "approved",
            CustomerSourceTokenAlias.created_from_import_job_id.isnot(None),
            CustomerSourceTokenAlias.created_from_import_job_id != int(current_job_id),
        )
    ).all()
    for alias in alias_rows:
        if source_definition_id is not None and alias.source_definition_id is not None:
            if int(alias.source_definition_id) != int(source_definition_id):
                continue
        nt = (alias.normalized_token or "").strip()
        if not nt:
            continue
        dist_id = int(alias.distributor_id) if alias.distributor_id is not None else None
        slot = (dist_id, nt)
        existing = out.get(slot)
        conf = 0.92 if dist_id is not None else 0.85
        if existing is not None and existing.confidence >= conf:
            continue
        jid = int(alias.created_from_import_job_id) if alias.created_from_import_job_id else 0
        out[slot] = HistoricalCustomerResolution(
            customer_id=int(alias.customer_id),
            import_job_id=jid,
            match_reason="historical_approved_alias",
            confidence=conf,
            resolution_kind="historical_alias",
        )

    return out


def _dealer_group_norm_from_candidate_context(ctx: dict[str, Any], dealer_group_token: str | None) -> str:
    dg_raw = ctx.get("dealer_group_account_raw") if isinstance(ctx.get("dealer_group_account_raw"), str) else None
    if not dg_raw and dealer_group_token:
        dg_raw = str(dealer_group_token).strip()
    if not dg_raw:
        return ""
    return normalize_customer_name_for_similarity(dg_raw)


def build_job_customer_sibling_index(
    candidates: list[ImportEntityMappingCandidate],
) -> dict[str, tuple[JobCustomerSiblingMapping, ...]]:
    """In-job mappings keyed by normalised dealer-group label (plan suggestion only)."""
    buckets: dict[str, list[JobCustomerSiblingMapping]] = {}
    for cand in candidates:
        if cand.entity_type != "customer_dealer_token":
            continue
        ctx = cand.context if isinstance(cand.context, dict) else {}
        dg_norm = _dealer_group_norm_from_candidate_context(ctx, cand.dealer_group_token)
        if not dg_norm:
            continue
        cid: int | None = None
        reason: str | None = None
        if cand.suggested_entity_id is not None:
            cid = int(cand.suggested_entity_id)
            reason = (cand.match_reason or "").strip() or "suggested_entity_on_job"
        else:
            dr = ctx.get("duplicate_review")
            if isinstance(dr, dict) and str(dr.get("decision") or "").strip() == "same_entity":
                try:
                    cid = int(dr.get("customer_id")) if dr.get("customer_id") is not None else None
                except (TypeError, ValueError):
                    cid = None
                reason = "duplicate_review_same_entity"
        if cid is None:
            continue
        nk = (cand.normalized_key or "").strip()
        if not nk:
            continue
        buckets.setdefault(dg_norm, []).append(
            JobCustomerSiblingMapping(normalized_key=nk, customer_id=cid, match_reason=reason)
        )
    return {k: tuple(v) for k, v in buckets.items()}


def lookup_job_customer_sibling_mapping(
    index: dict[str, tuple[JobCustomerSiblingMapping, ...]],
    *,
    dealer_group_norm: str,
    exclude_normalized_key: str,
) -> JobCustomerSiblingMapping | None:
    entries = index.get((dealer_group_norm or "").strip())
    if not entries:
        return None
    ex = (exclude_normalized_key or "").strip()
    for entry in entries:
        if entry.normalized_key != ex:
            return entry
    return None


def lookup_historical_customer_resolution(
    index: dict[tuple[int | None, str], HistoricalCustomerResolution],
    *,
    distributor_id: int | None,
    normalized_key: str,
    customer_raw: str | None,
    dealer_group_raw: str | None,
) -> HistoricalCustomerResolution | None:
    """Prefer distributor-scoped historical match, then source-wide steward history."""
    nk = _norm_key(normalized_key)
    if distributor_id is not None:
        hit = index.get((int(distributor_id), nk))
        if hit is not None:
            return hit
    hit = index.get((None, nk))
    if hit is not None:
        return hit
    for raw in (dealer_group_raw, customer_raw):
        if not raw or not str(raw).strip():
            continue
        alt = normalize_customer_name_for_similarity(str(raw))
        if len(alt) < 4:
            continue
        if distributor_id is not None:
            hit = index.get((int(distributor_id), alt))
            if hit is not None:
                return hit
        hit = index.get((None, alt))
        if hit is not None:
            return hit
    return None


def resolve_customer_id_distributor_scoped_alias(
    res_cache: Any,
    *,
    source_id: int | None,
    distributor_id: int | None,
    normalized_customer: str,
) -> int | None:
    """Approved alias match restricted to the same distributor (stronger than global alias)."""
    if not normalized_customer or distributor_id is None:
        return None
    lookup_key = customer_source_token_alias_key(normalized_customer)
    if not lookup_key:
        return None
    matches: list[int] = []
    for a in res_cache.cust_aliases:
        if a.match_key != lookup_key:
            continue
        if a.distributor_id is None or int(a.distributor_id) != int(distributor_id):
            continue
        if (
            source_id is not None
            and a.source_definition_id is not None
            and int(a.source_definition_id) != int(source_id)
        ):
            continue
        matches.append(int(a.customer_id))
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None
