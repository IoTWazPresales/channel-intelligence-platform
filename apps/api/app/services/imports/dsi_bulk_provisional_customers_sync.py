"""Batch provisional customer creation for DSI bulk steward (sync session, single commit)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimRegion
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry
from app.services.imports.dsi_geo_resolution_cache import DSIGeoResolutionCache, collect_geo_tokens_from_candidates
from app.services.imports.dsi_resolution_plan import derive_effective_provisional_customer_geo_sync
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    _resolved_provisional_display_name,
    _source_customer_alias_raw_for_dsi_candidate,
)
from app.services.imports.provisional_entity_identity import (
    find_existing_provisional_customer_by_canonical_name,
    is_non_entity_customer_provisional_token,
)


def _generate_tmp_customer_code_sync(session: Session) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        code_candidate = f"TMP-CUST-{stamp}-{secrets.token_hex(2).upper()}"
        exists = session.scalar(select(DimCustomer.id).where(DimCustomer.code == code_candidate))
        if exists is None:
            return code_candidate
    raise StewardOpError(
        "Unable to generate a temporary customer code; retry.",
        status_code=503,
    )


def _effective_geo_for_bulk(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    geo_cache: DSIGeoResolutionCache,
    *,
    fallback_region_id: int | None,
    fallback_channel_id: int | None,
    explicit_region_id: int | None = None,
    explicit_channel_id: int | None = None,
) -> tuple[int | None, int | None]:
    if explicit_region_id is not None or explicit_channel_id is not None:
        er = int(explicit_region_id) if explicit_region_id is not None else None
        ec = int(explicit_channel_id) if explicit_channel_id is not None else None
        return er, ec
    g = derive_effective_provisional_customer_geo_sync(
        session,
        cand,
        default_region_id=fallback_region_id,
        default_channel_id=fallback_channel_id,
        import_job=job,
        geo_cache=geo_cache,
    )
    er = g.get("effective_region_id")
    ec = g.get("effective_channel_id")
    return int(er) if er is not None else None, int(ec) if ec is not None else None


def _apply_one_provisional_customer_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    geo_cache: DSIGeoResolutionCache,
    *,
    fallback_region_id: int | None,
    fallback_channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
    explicit_region_id: int | None = None,
    explicit_channel_id: int | None = None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)

    if (
        cand.status == "resolved"
        and cand.match_reason == "steward_created_provisional_customer"
        and cand.suggested_entity_id
    ):
        cust = session.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            alias_row = session.scalars(
                select(CustomerSourceTokenAlias).where(
                    CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand.id
                )
            ).first()
            return {
                "ok": True,
                "idempotent": True,
                "candidate_id": cand.id,
                "customer_id": cust.id,
                "customer_code": cust.code,
                "alias_id": int(alias_row.id) if alias_row else None,
            }

    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise StewardOpError("Candidate already terminal", status_code=400)

    region_id, channel_id = _effective_geo_for_bulk(
        session,
        cand,
        job,
        geo_cache,
        fallback_region_id=fallback_region_id,
        fallback_channel_id=fallback_channel_id,
        explicit_region_id=explicit_region_id,
        explicit_channel_id=explicit_channel_id,
    )

    if region_id is not None and session.get(DimRegion, region_id) is None:
        raise StewardOpError("Invalid region_id", status_code=400)
    if channel_id is not None and session.get(DimChannel, channel_id) is None:
        raise StewardOpError("Invalid channel_id", status_code=400)
    if preferred_distributor_id is not None and session.get(DimDistributor, preferred_distributor_id) is None:
        raise StewardOpError("Invalid preferred_distributor_id", status_code=400)

    tier = (partner_tier or "unmanaged").strip().lower()
    if tier not in {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}:
        raise StewardOpError("Invalid partner_tier", status_code=400)

    raw_evidence = _source_customer_alias_raw_for_dsi_candidate(cand)
    if not raw_evidence.strip():
        raise StewardOpError("Candidate has no usable source customer alias evidence", status_code=400)

    proposal = _resolved_provisional_display_name(None, cand)
    if is_non_entity_customer_provisional_token(raw_token=raw_evidence, display_name=proposal):
        raise StewardOpError(
            "Token or display name looks like policy/note text (not a customer entity)",
            status_code=400,
        )
    notes = (notes_summary or "").strip() or None
    base_note = f"Provisional customer created from DSI import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note

    existing_cust = find_existing_provisional_customer_by_canonical_name(session, proposal)
    if existing_cust is not None:
        row = existing_cust
    else:
        code = _generate_tmp_customer_code_sync(session)
        row = DimCustomer(
            code=code,
            name=proposal.strip()[:256],
            customer_status="unverified",
            partner_tier=tier,
            notes_summary=merged_notes[:512],
            region_id=region_id,
            channel_id=channel_id,
            preferred_distributor_id=preferred_distributor_id,
        )
        session.add(row)
        session.flush()

    raw = raw_evidence
    nt = _norm_key(raw)
    alias = CustomerSourceTokenAlias(
        customer_id=row.id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        status="approved",
        notes=f"Alias from provisional customer create (candidate {cand.id})",
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    session.add(alias)
    cand.status = "resolved"
    cand.suggested_entity_id = row.id
    cand.match_reason = "steward_created_provisional_customer"

    return {
        "ok": True,
        "customer_id": row.id,
        "customer_code": row.code,
        "alias_id": alias.id,
        "candidate_id": cand.id,
    }


def run_dsi_bulk_provisional_customers_sync(
    session: Session,
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Create provisional customers for all candidate_ids in one transaction."""
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise ValueError("Job is not a distributor sales & inventory import")

    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    fallback_region_id = payload.get("region_id")
    fallback_channel_id = payload.get("channel_id")
    fallback_region_id = int(fallback_region_id) if fallback_region_id is not None else None
    fallback_channel_id = int(fallback_channel_id) if fallback_channel_id is not None else None
    preferred_distributor_id = payload.get("preferred_distributor_id")
    preferred_distributor_id = (
        int(preferred_distributor_id) if preferred_distributor_id is not None else None
    )
    partner_tier = payload.get("partner_tier")
    notes_summary = payload.get("provisional_notes_summary")

    geo_by_candidate: dict[int, tuple[int | None, int | None]] = {}
    for raw_geo in payload.get("per_candidate_geo") or []:
        if not isinstance(raw_geo, dict):
            continue
        cid_raw = raw_geo.get("candidate_id")
        if cid_raw is None:
            continue
        try:
            cid = int(cid_raw)
        except (TypeError, ValueError):
            continue
        er = raw_geo.get("region_id")
        ec = raw_geo.get("channel_id")
        geo_by_candidate[cid] = (
            int(er) if er is not None else None,
            int(ec) if ec is not None else None,
        )

    found = {
        int(c.id): c
        for c in session.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(job_id),
                ImportEntityMappingCandidate.id.in_(candidate_ids),
            )
        ).all()
    }

    geo_cache = DSIGeoResolutionCache.build(session)
    geo_cache.preload_aliases(collect_geo_tokens_from_candidates(list(found.values()), job))

    results: list[dict[str, Any]] = []
    total = len(candidate_ids)
    applied_before_commit = 0

    for idx, cid in enumerate(candidate_ids):
        if on_progress is not None:
            on_progress(idx + 1, total)
        cand = found.get(cid)
        if cand is None:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "detail": "Candidate not found for this job",
                    "row_count": None,
                    "total_units": None,
                    "total_reported_value": None,
                }
            )
            continue
        rc = cand.row_count
        tu = float(cand.total_units) if cand.total_units is not None else None
        trv = float(cand.total_reported_value) if cand.total_reported_value is not None else None
        try:
            ex_r, ex_c = geo_by_candidate.get(int(cid), (None, None))
            out = _apply_one_provisional_customer_sync(
                session,
                cand,
                job,
                geo_cache,
                fallback_region_id=fallback_region_id,
                fallback_channel_id=fallback_channel_id,
                preferred_distributor_id=preferred_distributor_id,
                partner_tier=partner_tier,
                notes_summary=notes_summary,
                explicit_region_id=ex_r,
                explicit_channel_id=ex_c,
            )
            applied_before_commit += 1
            results.append(
                {
                    "candidate_id": cid,
                    "ok": True,
                    "entity_type": cand.entity_type,
                    "result": out,
                    "row_count": rc,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )
        except StewardOpError as exc:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "detail": exc.detail,
                    "row_count": rc,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )

    if applied_before_commit > 0:
        try:
            commit_session_with_transient_retry(session)
        except IntegrityError as exc:
            session.rollback()
            raise StewardOpError("Could not commit bulk provisional customers", status_code=409) from exc

    ok_n = sum(1 for r in results if r.get("ok"))
    rows_affected = sum(int(r.get("row_count") or 0) for r in results if r.get("ok"))
    units = sum(float(r.get("total_units") or 0) for r in results if r.get("ok"))
    value = sum(float(r.get("total_reported_value") or 0) for r in results if r.get("ok"))

    return {
        "import_job_id": job_id,
        "action": "create_provisional_customer",
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
        "totals": {
            "ok_count": ok_n,
            "not_ok_count": len(results) - ok_n,
            "staging_rows_affected": rows_affected,
            "total_units_affected": units,
            "total_reported_value_affected": value,
        },
    }
