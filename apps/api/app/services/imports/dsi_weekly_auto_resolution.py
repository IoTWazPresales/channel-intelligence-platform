"""Weekly DSI token auto-resolution (validate-time + plan tier helpers)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import cast, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Integer

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_customer_intelligence import (
    HistoricalCustomerResolution,
    load_historical_customer_resolutions,
    lookup_historical_customer_resolution,
)
from app.services.imports.dsi_import_state_awareness import AutoResolutionTier
from app.services.imports.distributor_sales_inventory import dsi_historical_workflow_from_import_job

EntityAutoOutcome = Literal["resolved", "conflict", "none"]


@dataclass(frozen=True)
class EntityAutoResolutionResult:
    outcome: EntityAutoOutcome
    entity_id: int | None = None
    conflict_prior: list[dict[str, Any]] | None = None
    resolution_kind: str | None = None


def intelligence_tier_from_job(job: ImportJob) -> AutoResolutionTier:
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    intel = sm.get("intelligence_state")
    if isinstance(intel, dict):
        tier = str(intel.get("auto_resolution_tier") or "").strip().lower()
        if tier in ("none", "supervised", "automatic"):
            return tier  # type: ignore[return-value]
    return "none"


def weekly_auto_resolution_active(job: ImportJob) -> bool:
    if dsi_historical_workflow_from_import_job(job):
        return False
    return str((job.staged_metadata or {}).get("dsi_workflow_mode") or "").strip().lower() == "weekly"


def _dominant_distributor_from_context(ctx: dict[str, Any]) -> int | None:
    dom = ctx.get("dominant_distributor_id")
    if dom is None:
        return None
    try:
        return int(dom)
    except (TypeError, ValueError):
        return None


def _prior_resolved_entity_ids(
    session: Session,
    *,
    source_definition_id: int,
    current_job_id: int,
    entity_type: str,
    normalized_key: str,
    distributor_id: int | None,
    limit: int = 2,
) -> list[tuple[int, int, int | None]]:
    """Return up to ``limit`` tuples (import_job_id, entity_id, distributor_id from context)."""
    nk = (normalized_key or "").strip()[:512]
    if not nk:
        return []

    dom_col = ImportEntityMappingCandidate.context["dominant_distributor_id"].astext
    q = (
        select(
            ImportEntityMappingCandidate.import_job_id,
            ImportEntityMappingCandidate.suggested_entity_id,
            cast(dom_col, Integer),
        )
        .join(ImportJob, ImportJob.id == ImportEntityMappingCandidate.import_job_id)
        .where(
            ImportEntityMappingCandidate.entity_type == entity_type,
            ImportEntityMappingCandidate.source_definition_id == int(source_definition_id),
            ImportEntityMappingCandidate.import_job_id != int(current_job_id),
            ImportEntityMappingCandidate.status == "resolved",
            ImportEntityMappingCandidate.normalized_key == nk,
            ImportEntityMappingCandidate.suggested_entity_id.isnot(None),
        )
        .order_by(ImportJob.completed_at.desc().nullslast(), ImportEntityMappingCandidate.id.desc())
        .limit(50)
    )
    rows = session.execute(q).all()
    out: list[tuple[int, int, int | None]] = []
    for jid, eid, dom in rows:
        if eid is None:
            continue
        if distributor_id is not None and dom is not None and int(dom) != int(distributor_id):
            continue
        out.append((int(jid), int(eid), int(dom) if dom is not None else None))
        if len(out) >= limit:
            break
    return out


def check_customer_auto_resolution_at_validate(
    session: Session,
    *,
    job: ImportJob,
    source_definition_id: int | None,
    distributor_id: int | None,
    normalized_key: str,
    customer_raw: str | None,
    dealer_group_raw: str | None,
    historical_index: dict[tuple[int | None, str], HistoricalCustomerResolution] | None = None,
) -> EntityAutoResolutionResult:
    if not weekly_auto_resolution_active(job):
        return EntityAutoResolutionResult(outcome="none")
    tier = intelligence_tier_from_job(job)
    if tier == "none":
        return EntityAutoResolutionResult(outcome="none")
    if source_definition_id is None:
        return EntityAutoResolutionResult(outcome="none")

    idx = historical_index
    if idx is None:
        idx = load_historical_customer_resolutions(
            session,
            source_definition_id=int(source_definition_id),
            current_job_id=int(job.id),
        )
    hist = lookup_historical_customer_resolution(
        idx,
        distributor_id=distributor_id,
        normalized_key=normalized_key,
        customer_raw=customer_raw,
        dealer_group_raw=dealer_group_raw,
    )
    if hist is None:
        return EntityAutoResolutionResult(outcome="none")

    if tier == "supervised":
        return EntityAutoResolutionResult(
            outcome="none",
            entity_id=int(hist.customer_id),
            resolution_kind=hist.resolution_kind,
        )

    priors = _prior_resolved_entity_ids(
        session,
        source_definition_id=int(source_definition_id),
        current_job_id=int(job.id),
        entity_type="customer_dealer_token",
        normalized_key=normalized_key,
        distributor_id=distributor_id,
        limit=2,
    )
    if len(priors) < 2:
        return EntityAutoResolutionResult(
            outcome="resolved",
            entity_id=int(hist.customer_id),
            resolution_kind=hist.resolution_kind,
        )
    ids = {p[1] for p in priors[:2]}
    if len(ids) == 1:
        return EntityAutoResolutionResult(
            outcome="resolved",
            entity_id=int(next(iter(ids))),
            resolution_kind="historical_steward_consistent",
        )
    return EntityAutoResolutionResult(
        outcome="conflict",
        conflict_prior=[
            {"import_job_id": p[0], "customer_id": p[1], "distributor_id": p[2]}
            for p in priors[:2]
        ],
    )


def check_product_auto_resolution_at_validate(
    session: Session,
    *,
    job: ImportJob,
    source_definition_id: int | None,
    distributor_id: int | None,
    normalized_key: str,
) -> EntityAutoResolutionResult:
    if not weekly_auto_resolution_active(job):
        return EntityAutoResolutionResult(outcome="none")
    if intelligence_tier_from_job(job) != "automatic":
        return EntityAutoResolutionResult(outcome="none")
    if source_definition_id is None:
        return EntityAutoResolutionResult(outcome="none")

    priors = _prior_resolved_entity_ids(
        session,
        source_definition_id=int(source_definition_id),
        current_job_id=int(job.id),
        entity_type="product_identifier",
        normalized_key=normalized_key,
        distributor_id=distributor_id,
        limit=2,
    )
    if len(priors) < 2:
        return EntityAutoResolutionResult(outcome="none")
    ids = {p[1] for p in priors[:2]}
    if len(ids) == 1:
        return EntityAutoResolutionResult(
            outcome="resolved",
            entity_id=int(next(iter(ids))),
            resolution_kind="historical_product_consistent",
        )
    return EntityAutoResolutionResult(
        outcome="conflict",
        conflict_prior=[
            {"import_job_id": p[0], "product_id": p[1], "distributor_id": p[2]}
            for p in priors[:2]
        ],
    )


def check_distributor_auto_resolution_at_validate(
    session: Session,
    *,
    job: ImportJob,
    source_definition_id: int | None,
    normalized_key: str,
    resolved_distributor_id: int | None,
) -> EntityAutoResolutionResult:
    if resolved_distributor_id is not None:
        return EntityAutoResolutionResult(outcome="none")
    if not weekly_auto_resolution_active(job):
        return EntityAutoResolutionResult(outcome="none")
    if intelligence_tier_from_job(job) != "automatic":
        return EntityAutoResolutionResult(outcome="none")
    if source_definition_id is None:
        return EntityAutoResolutionResult(outcome="none")

    from app.services.imports.distributor_sales_inventory import (
        _build_resolution_cache,
        _resolve_distributor_from_cache,
    )

    res_cache = _build_resolution_cache(session, source_definition_id)
    did, _err = _resolve_distributor_from_cache(
        normalized_key,
        source_definition_id,
        res_cache,
    )
    if did is None:
        return EntityAutoResolutionResult(outcome="none")
    return EntityAutoResolutionResult(
        outcome="resolved",
        entity_id=int(did),
        resolution_kind="distributor_alias_or_dim",
    )
