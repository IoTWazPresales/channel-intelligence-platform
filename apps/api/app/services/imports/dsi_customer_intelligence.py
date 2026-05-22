"""DSI customer duplicate hints and cross-job resolution signals (no embedding models)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity


def _norm_key(s: str | None) -> str:
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

# Text similarity threshold for within-job duplicate hints (difflib ratio on normalised names).
DSI_DUPLICATE_SIMILARITY_THRESHOLD: float = 0.82
_MIN_COMPARE_LEN: int = 4

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


def annotate_dsi_customer_candidate_duplicates(
    agg: dict[tuple[str, str], dict[str, Any]],
    *,
    similarity_threshold: float = DSI_DUPLICATE_SIMILARITY_THRESHOLD,
) -> None:
    """Set ``possible_duplicate_of`` on customer_dealer_token buckets (pre-persist)."""
    items = [
        (nk, data)
        for (etype, nk), data in agg.items()
        if etype == "customer_dealer_token"
    ]
    for i, (nk_a, da) in enumerate(items):
        name_a = _display_name_for_customer_agg(da)
        norm_a = normalize_customer_name_for_similarity(name_a)
        if len(norm_a) < _MIN_COMPARE_LEN:
            continue
        for nk_b, db in items[i + 1 :]:
            name_b = _display_name_for_customer_agg(db)
            norm_b = normalize_customer_name_for_similarity(name_b)
            if len(norm_b) < _MIN_COMPARE_LEN:
                continue
            ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
            if ratio < similarity_threshold:
                continue
            score = round(float(ratio), 4)
            _append_duplicate_hint(da, nk_b, score)
            _append_duplicate_hint(db, nk_a, score)


def _append_duplicate_hint(bucket: dict[str, Any], other_normalized_key: str, score: float) -> None:
    hints: list[dict[str, Any]] = bucket.setdefault("possible_duplicate_of", [])
    if not isinstance(hints, list):
        hints = []
        bucket["possible_duplicate_of"] = hints
    for h in hints:
        if isinstance(h, dict) and h.get("normalized_key") == other_normalized_key:
            if float(h.get("similarity_score") or 0) < score:
                h["similarity_score"] = score
            return
    hints.append({"normalized_key": other_normalized_key, "similarity_score": score})


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

    cand_rows = session.execute(
        select(
            ImportEntityMappingCandidate.normalized_key,
            ImportEntityMappingCandidate.suggested_entity_id,
            ImportEntityMappingCandidate.match_reason,
            ImportEntityMappingCandidate.import_job_id,
            ImportJob.completed_at,
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

    for nk, cid, reason, jid, _completed in cand_rows:
        key = nk if isinstance(nk, str) else str(nk or "")
        if not key or cid is None:
            continue
        dist_key: int | None = None  # steward rows are source-scoped; distributor from alias pass
        slot = (dist_key, _norm_key(key))
        if slot in out:
            continue
        mr = (reason or "").strip()
        out[slot] = HistoricalCustomerResolution(
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
    nt = _norm_key(normalized_customer)
    if not nt:
        return None
    matches: list[int] = []
    for a in res_cache.cust_aliases:
        if a.normalized_token != nt:
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
