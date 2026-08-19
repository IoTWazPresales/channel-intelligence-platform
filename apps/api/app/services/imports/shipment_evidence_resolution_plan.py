"""Resolution hints for shipment evidence ``ImportEntityMappingCandidate`` rows.

Covers ``shipment_distributor`` and ``shipment_customer_token``. Scores are **UI hints only**;
steward apply paths remain strict (approved alias + explicit dimension choice).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_candidate_names import suggested_name_for_distributor_token
from app.utils.json_safe import to_jsonable


SHIPMENT_DISTRIBUTOR_ENTITY = "shipment_distributor"
SHIPMENT_CUSTOMER_ENTITY = "shipment_customer_token"

# Terminal / closed mapping candidates: do not re-score in enrich passes.
SHIPMENT_CANDIDATE_TERMINAL_STATUSES = frozenset({"resolved", "ignored", "waived_open_channel", "steward_rejected"})


@dataclass
class ShipmentEnrichRefs:
    """One-time preload of the (small) reference tables used to score candidates.

    Lets enrich passes resolve every candidate in-memory instead of issuing per-candidate
    alias queries + full ``dim_distributor`` / ``dim_customer`` scans — which, against a
    remote DB, dominate validate time (round-trip latency × candidate count).
    """

    distributors: list  # list[DimDistributor]
    customers: list  # list[DimCustomer]
    dist_aliases: list  # list[(normalized_token, distributor_id, source_definition_id)] status == approved
    cust_aliases: list  # list[(normalized_token, customer_id, source_definition_id)] status == approved


def build_shipment_enrich_refs(db: Session) -> "ShipmentEnrichRefs":
    """Load distributor/customer dims + approved aliases once for in-memory candidate scoring."""
    distributors = list(db.scalars(select(DimDistributor)).all())
    customers = list(db.scalars(select(DimCustomer)).all())
    dist_aliases = list(
        db.execute(
            select(
                DistributorSourceTokenAlias.normalized_token,
                DistributorSourceTokenAlias.distributor_id,
                DistributorSourceTokenAlias.source_definition_id,
            ).where(DistributorSourceTokenAlias.status == "approved")
        ).all()
    )
    cust_aliases = list(
        db.execute(
            select(
                CustomerSourceTokenAlias.normalized_token,
                CustomerSourceTokenAlias.customer_id,
                CustomerSourceTokenAlias.source_definition_id,
            ).where(CustomerSourceTokenAlias.status == "approved")
        ).all()
    )
    return ShipmentEnrichRefs(
        distributors=distributors,
        customers=customers,
        dist_aliases=dist_aliases,
        cust_aliases=cust_aliases,
    )


def build_unique_approved_customer_alias_id_by_token(
    cust_aliases: list[tuple[str, int, int | None]] | list[tuple[str, int]],
    *,
    redirect: dict[int, int] | None = None,
) -> dict[str, int]:
    """Map ``normalized_token`` → ``customer_id`` when exactly one distinct id is approved.

    Used by lineup parse/backfill and any path that must not guess on ambiguous alias scope.
    Optional ``redirect`` collapses merged loser ids onto the survivor before uniqueness.
    """
    from app.services.merge_redirect import redirect_id

    redir = redirect or {}
    by_token: dict[str, set[int]] = defaultdict(set)
    for row in cust_aliases:
        nt = str(row[0] or "").strip()
        if not nt:
            continue
        cid = int(redirect_id(int(row[1]), redir) or row[1])
        by_token[nt].add(cid)
    return {nt: next(iter(ids)) for nt, ids in by_token.items() if len(ids) == 1}


def _collapse_party_ids(
    db: Session,
    ids: list[int],
    *,
    kind: str,
    refs: "ShipmentEnrichRefs | None" = None,
) -> list[int]:
    from app.services.merge_redirect import (
        build_redirect_map,
        collapse_ids,
        follow_customer_merge_redirect_sync,
        follow_distributor_merge_redirect_sync,
    )

    if not ids:
        return []
    if refs is not None:
        if kind == "customer":
            parent = {
                int(c.id): int(c.merged_into_customer_id) if c.merged_into_customer_id is not None else None
                for c in refs.customers
            }
        else:
            parent = {
                int(d.id): int(d.merged_into_distributor_id) if d.merged_into_distributor_id is not None else None
                for d in refs.distributors
            }
        return collapse_ids(ids, build_redirect_map(parent.items()))
    follow = (
        follow_customer_merge_redirect_sync if kind == "customer" else follow_distributor_merge_redirect_sync
    )
    seen: set[int] = set()
    out: list[int] = []
    for raw in ids:
        tid = follow(db, int(raw)) or int(raw)
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def _alias_source_match(alias_source_id: int | None, source_definition_id: int | None) -> bool:
    """Replicate the source-scoping filter used by the alias queries."""
    if source_definition_id is not None:
        return alias_source_id is None or alias_source_id == source_definition_id
    return alias_source_id is None


def _alias_distributor_ids(
    db: Session,
    *,
    source_definition_id: int | None,
    normalized_token: str,
    refs: "ShipmentEnrichRefs | None" = None,
) -> list[int]:
    if not normalized_token:
        return []
    if refs is not None:
        out = [
            int(did)
            for nt, did, sdid in refs.dist_aliases
            if nt == normalized_token and _alias_source_match(sdid, source_definition_id)
        ]
        return _collapse_party_ids(db, list(dict.fromkeys(out)), kind="distributor", refs=refs)
    q = select(DistributorSourceTokenAlias.distributor_id).where(
        DistributorSourceTokenAlias.normalized_token == normalized_token,
        DistributorSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                DistributorSourceTokenAlias.source_definition_id.is_(None),
                DistributorSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(DistributorSourceTokenAlias.source_definition_id.is_(None))
    rows = list(dict.fromkeys(int(x) for x in db.scalars(q).all()))
    return _collapse_party_ids(db, rows, kind="distributor", refs=None)


def _alias_customer_ids(
    db: Session,
    *,
    source_definition_id: int | None,
    normalized_token: str,
    refs: "ShipmentEnrichRefs | None" = None,
) -> list[int]:
    if not normalized_token:
        return []
    if refs is not None:
        out = [
            int(cid)
            for nt, cid, sdid in refs.cust_aliases
            if nt == normalized_token and _alias_source_match(sdid, source_definition_id)
        ]
        return _collapse_party_ids(db, list(dict.fromkeys(out)), kind="customer", refs=refs)
    q = select(CustomerSourceTokenAlias.customer_id).where(
        CustomerSourceTokenAlias.normalized_token == normalized_token,
        CustomerSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(CustomerSourceTokenAlias.source_definition_id.is_(None))
    rows = list(dict.fromkeys(int(x) for x in db.scalars(q).all()))
    return _collapse_party_ids(db, rows, kind="customer", refs=None)


def _exact_dim_matches(
    db: Session, *, normalized_token: str, refs: "ShipmentEnrichRefs | None" = None
) -> list[int]:
    """Exact dim_distributor match on normalized code or full normalized name (strict)."""
    nk = (normalized_token or "").strip().lower()
    if not nk:
        return []
    rows = refs.distributors if refs is not None else db.scalars(select(DimDistributor)).all()
    out: list[int] = []
    for d in rows:
        code = (d.code or "").strip().lower()
        name = (d.name or "").strip().lower()
        if code == nk or name == nk:
            out.append(int(d.id))
    return sorted(_collapse_party_ids(db, out, kind="distributor", refs=refs))


def _exact_dim_customer_matches(
    db: Session, *, normalized_token: str, refs: "ShipmentEnrichRefs | None" = None
) -> list[int]:
    nk = (normalized_token or "").strip().lower()
    if not nk:
        return []
    rows = refs.customers if refs is not None else db.scalars(select(DimCustomer)).all()
    out: list[int] = []
    for c in rows:
        code = (c.code or "").strip().lower()
        name = (c.name or "").strip().lower()
        if code == nk or name == nk:
            out.append(int(c.id))
    return sorted(_collapse_party_ids(db, out, kind="customer", refs=refs))


def _distributor_display_name_hint(cand: ImportEntityMappingCandidate) -> str:
    """Human label derived at candidate build time (e.g. RECTRON-ZA-EDU → Rectron)."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    hint = (ctx.get("suggested_name") or "").strip()
    if hint:
        return hint
    samples = cand.sample_raw_values
    if isinstance(samples, list):
        for raw in samples:
            if isinstance(raw, str) and raw.strip():
                return suggested_name_for_distributor_token(raw)
    return ""


def score_shipment_distributor_candidate(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    source_definition_id: int | None,
    refs: "ShipmentEnrichRefs | None" = None,
) -> dict[str, Any]:
    """Return plan fields: suggested_action, suggested_entity_id, match_reason, confidence_score."""
    nt = (cand.normalized_key or "").strip()
    alias_ids = _alias_distributor_ids(db, source_definition_id=source_definition_id, normalized_token=nt, refs=refs)
    dim_ids = _exact_dim_matches(db, normalized_token=nt, refs=refs)

    if len(alias_ids) == 1:
        return {
            "suggested_action": "map_distributor",
            "suggested_entity_id": int(alias_ids[0]),
            "match_reason": "approved_distributor_source_token_alias",
            "confidence_score": 1.0,
        }
    if len(alias_ids) > 1:
        return {
            "suggested_action": "needs_review",
            "suggested_entity_id": None,
            "match_reason": "multiple_approved_distributor_aliases_for_token",
            "confidence_score": 0.4,
        }

    if len(dim_ids) == 1:
        return {
            "suggested_action": "map_distributor",
            "suggested_entity_id": int(dim_ids[0]),
            "match_reason": "exact_dim_distributor_code_or_name",
            "confidence_score": 0.95,
        }
    if len(dim_ids) > 1:
        return {
            "suggested_action": "needs_review",
            "suggested_entity_id": None,
            "match_reason": "multiple_dim_distributors_exact_match_token",
            "confidence_score": 0.35,
        }

    display_hint = _distributor_display_name_hint(cand)
    if display_hint:
        hint_nk = _norm_key(display_hint)
        if hint_nk and hint_nk != nt:
            hint_ids = _exact_dim_matches(db, normalized_token=hint_nk, refs=refs)
            if len(hint_ids) == 1:
                return {
                    "suggested_action": "map_distributor",
                    "suggested_entity_id": int(hint_ids[0]),
                    "match_reason": "exact_dim_distributor_name_matches_display_hint",
                    "confidence_score": 0.88,
                }
            if len(hint_ids) > 1:
                return {
                    "suggested_action": "needs_review",
                    "suggested_entity_id": None,
                    "match_reason": "multiple_dim_distributors_match_display_hint",
                    "confidence_score": 0.35,
                }

    return {
        "suggested_action": "create_provisional_distributor",
        "suggested_entity_id": None,
        "match_reason": "no_alias_or_exact_dim_match",
        "confidence_score": 0.2,
    }


def _shipment_customer_lookup_norm_tokens(cand: ImportEntityMappingCandidate) -> list[str]:
    """Normalised lookup tokens: grouped ``source_tokens`` when present, else ``normalized_key``."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("source_tokens")
    out: list[str] = []
    if isinstance(raw, list):
        for x in raw:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s:
                continue
            nk = _norm_key(s)
            if nk and nk not in out:
                out.append(nk)
    if not out:
        nk = (cand.normalized_key or "").strip()
        if nk:
            out.append(nk)
    return out


def score_shipment_customer_token_candidate(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    source_definition_id: int | None,
    refs: "ShipmentEnrichRefs | None" = None,
) -> dict[str, Any]:
    norms = _shipment_customer_lookup_norm_tokens(cand)
    if not norms:
        return {
            "suggested_action": "create_provisional_customer",
            "suggested_entity_id": None,
            "match_reason": "no_alias_or_exact_dim_match",
            "confidence_score": 0.2,
        }

    alias_sets = [
        set(
            int(x)
            for x in _alias_customer_ids(
                db, source_definition_id=source_definition_id, normalized_token=nt, refs=refs
            )
        )
        for nt in norms
    ]
    nonempty = [(nt, s) for nt, s in zip(norms, alias_sets) if s]
    if nonempty:
        if any(len(s) > 1 for _, s in nonempty):
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "multiple_approved_customer_aliases_for_token",
                "confidence_score": 0.4,
            }
        ids = {next(iter(s)) for _, s in nonempty}
        if len(ids) > 1:
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "conflicting_customer_alias_hits_across_source_tokens",
                "confidence_score": 0.35,
            }
        if len(nonempty) < len(norms):
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "partial_customer_alias_coverage_across_source_tokens",
                "confidence_score": 0.45,
            }
        cid = next(iter(ids))
        return {
            "suggested_action": "map_customer",
            "suggested_entity_id": int(cid),
            "match_reason": "approved_customer_source_token_alias",
            "confidence_score": 1.0,
        }

    dim_sets = [
        set(int(x) for x in _exact_dim_customer_matches(db, normalized_token=nt, refs=refs)) for nt in norms
    ]
    dim_nonempty = [(nt, s) for nt, s in zip(norms, dim_sets) if s]
    if dim_nonempty:
        if any(len(s) > 1 for _, s in dim_nonempty):
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "multiple_dim_customers_exact_match_token",
                "confidence_score": 0.35,
            }
        ids = {next(iter(s)) for _, s in dim_nonempty}
        if len(ids) > 1:
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "conflicting_dim_customer_hits_across_source_tokens",
                "confidence_score": 0.33,
            }
        if len(dim_nonempty) < len(norms):
            return {
                "suggested_action": "needs_review",
                "suggested_entity_id": None,
                "match_reason": "partial_dim_customer_match_across_source_tokens",
                "confidence_score": 0.42,
            }
        did = next(iter(ids))
        return {
            "suggested_action": "map_customer",
            "suggested_entity_id": int(did),
            "match_reason": "exact_dim_customer_code_or_name",
            "confidence_score": 0.95,
        }

    return {
        "suggested_action": "create_provisional_customer",
        "suggested_entity_id": None,
        "match_reason": "no_alias_or_exact_dim_match",
        "confidence_score": 0.2,
    }


def enrich_shipment_distributor_candidates(db: Session, *, import_job_id: int, source_definition_id: int | None) -> None:
    """Persist planner hints onto ``shipment_distributor`` candidates for one import job."""
    rows = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(import_job_id),
                ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY,
            )
        ).all()
    )
    refs = build_shipment_enrich_refs(db) if rows else None
    for cand in rows:
        if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
            continue
        plan = score_shipment_distributor_candidate(db, cand, source_definition_id=source_definition_id, refs=refs)
        cand.suggested_entity_id = plan.get("suggested_entity_id")
        cand.match_reason = str(plan.get("match_reason") or "")[:256] or None
        cand.confidence_score = plan.get("confidence_score")
        ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
        ctx["suggested_action"] = plan["suggested_action"]
        cand.context = to_jsonable(ctx)
        db.add(cand)


def enrich_shipment_customer_token_candidates(db: Session, *, import_job_id: int, source_definition_id: int | None) -> None:
    """Persist planner hints onto ``shipment_customer_token`` candidates for one import job."""
    rows = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(import_job_id),
                ImportEntityMappingCandidate.entity_type == SHIPMENT_CUSTOMER_ENTITY,
            )
        ).all()
    )
    refs = build_shipment_enrich_refs(db) if rows else None
    for cand in rows:
        if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
            continue
        plan = score_shipment_customer_token_candidate(db, cand, source_definition_id=source_definition_id, refs=refs)
        cand.suggested_entity_id = plan.get("suggested_entity_id")
        cand.match_reason = str(plan.get("match_reason") or "")[:256] or None
        cand.confidence_score = plan.get("confidence_score")
        ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
        ctx["suggested_action"] = plan["suggested_action"]
        cand.context = to_jsonable(ctx)
        db.add(cand)
