"""Batch provisional customer creation for DSI bulk steward (sync session, single commit)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select, text
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


def _customer_alias_scope_key(
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> tuple[str, int, int]:
    """Approved-alias unique scope per migration 0048 (COALESCE sentinels)."""
    return (
        normalized_token[:512],
        int(source_definition_id) if source_definition_id is not None else -1,
        int(distributor_id) if distributor_id is not None else -1,
    )


def _scope_key_for_dsi_candidate(cand: ImportEntityMappingCandidate) -> tuple[tuple[str, int, int], str] | None:
    raw = _source_customer_alias_raw_for_dsi_candidate(cand)
    if not raw.strip():
        return None
    nt = _norm_key(raw)[:512]
    return _customer_alias_scope_key(nt, cand.source_definition_id, None), nt


def _lookup_approved_customer_alias_for_scope(
    session: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> CustomerSourceTokenAlias | None:
    scope_src = int(source_definition_id) if source_definition_id is not None else -1
    scope_dist = int(distributor_id) if distributor_id is not None else -1
    return session.scalars(
        select(CustomerSourceTokenAlias)
        .where(
            CustomerSourceTokenAlias.status == "approved",
            CustomerSourceTokenAlias.normalized_token == normalized_token[:512],
            func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1) == scope_src,
            func.coalesce(CustomerSourceTokenAlias.distributor_id, -1) == scope_dist,
        )
        .limit(1)
    ).first()


def _load_approved_customer_aliases_for_scopes(
    session: Session,
    scope_keys: set[tuple[str, int, int]],
) -> dict[tuple[str, int, int], CustomerSourceTokenAlias]:
    if not scope_keys:
        return {}
    normalized_tokens = {k[0] for k in scope_keys}
    rows = session.scalars(
        select(CustomerSourceTokenAlias).where(
            CustomerSourceTokenAlias.status == "approved",
            CustomerSourceTokenAlias.normalized_token.in_(normalized_tokens),
        )
    ).all()
    out: dict[tuple[str, int, int], CustomerSourceTokenAlias] = {}
    for row in rows:
        key = _customer_alias_scope_key(row.normalized_token, row.source_definition_id, row.distributor_id)
        if key in scope_keys and key not in out:
            out[key] = row
    return out


def _insert_approved_customer_alias_on_conflict_do_nothing(
    session: Session,
    *,
    customer_id: int,
    raw_token: str,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    dealer_group_token: str | None,
    notes: str,
    created_from_import_job_id: int,
    import_entity_mapping_candidate_id: int,
) -> int | None:
    """Insert alias; return new id or None when uq_cust_src_token_alias_approved_scope blocks insert."""
    row = session.execute(
        text(
            """
            INSERT INTO customer_source_token_alias (
                customer_id, source_definition_id, distributor_id,
                raw_token, normalized_token, dealer_group_token,
                status, notes, created_from_import_job_id,
                import_entity_mapping_candidate_id, created_at, updated_at
            )
            VALUES (
                :customer_id, :source_definition_id, :distributor_id,
                :raw_token, :normalized_token, :dealer_group_token,
                'approved', :notes, :created_from_import_job_id,
                :import_entity_mapping_candidate_id, NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {
            "customer_id": int(customer_id),
            "source_definition_id": source_definition_id,
            "distributor_id": distributor_id,
            "raw_token": raw_token[:512],
            "normalized_token": normalized_token[:512],
            "dealer_group_token": dealer_group_token[:512] if dealer_group_token else None,
            "notes": notes,
            "created_from_import_job_id": int(created_from_import_job_id),
            "import_entity_mapping_candidate_id": int(import_entity_mapping_candidate_id),
        },
    ).first()
    if row is not None and row[0] is not None:
        return int(row[0])
    return None


def _bind_candidate_to_reused_customer(
    cand: ImportEntityMappingCandidate,
    customer: DimCustomer,
    *,
    alias_id: int | None,
    reuse_kind: str,
) -> dict[str, Any]:
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer.id)
    cand.match_reason = "steward_reused_approved_customer_alias"
    return {
        "ok": True,
        "reused": True,
        "reuse_kind": reuse_kind,
        "customer_id": customer.id,
        "customer_code": customer.code,
        "alias_id": alias_id,
        "candidate_id": cand.id,
    }


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
    approved_alias_by_scope: dict[tuple[str, int, int], CustomerSourceTokenAlias] | None = None,
    batch_customer_id_by_scope: dict[tuple[str, int, int], int] | None = None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)

    if (
        cand.status == "resolved"
        and cand.match_reason
        in ("steward_created_provisional_customer", "steward_reused_approved_customer_alias")
        and cand.suggested_entity_id
    ):
        cust = session.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            alias_row = session.scalars(
                select(CustomerSourceTokenAlias).where(
                    CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand.id
                )
            ).first()
            if alias_row is None and cand.match_reason == "steward_reused_approved_customer_alias":
                scope_meta = _scope_key_for_dsi_candidate(cand)
                if scope_meta is not None:
                    scope_key, nt = scope_meta
                    alias_row = _lookup_approved_customer_alias_for_scope(
                        session,
                        normalized_token=nt,
                        source_definition_id=cand.source_definition_id,
                        distributor_id=None,
                    )
                    if alias_row is None and approved_alias_by_scope is not None:
                        alias_row = approved_alias_by_scope.get(scope_key)
            return {
                "ok": True,
                "idempotent": True,
                "reused": cand.match_reason == "steward_reused_approved_customer_alias",
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

    scope_meta = _scope_key_for_dsi_candidate(cand)
    if scope_meta is None:
        raise StewardOpError("Candidate has no usable source customer alias evidence", status_code=400)
    scope_key, nt = scope_meta

    alias_lookup = approved_alias_by_scope if approved_alias_by_scope is not None else {}
    batch_lookup = batch_customer_id_by_scope if batch_customer_id_by_scope is not None else {}

    existing_alias = alias_lookup.get(scope_key)
    if existing_alias is None:
        existing_alias = _lookup_approved_customer_alias_for_scope(
            session,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
        )
        if existing_alias is not None:
            alias_lookup[scope_key] = existing_alias

    if existing_alias is not None:
        cust = session.get(DimCustomer, int(existing_alias.customer_id))
        if cust is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        return _bind_candidate_to_reused_customer(
            cand,
            cust,
            alias_id=int(existing_alias.id),
            reuse_kind="existing_alias",
        )

    batch_customer_id = batch_lookup.get(scope_key)
    if batch_customer_id is not None:
        cust = session.get(DimCustomer, int(batch_customer_id))
        if cust is None:
            raise StewardOpError("Batch reuse customer missing", status_code=409)
        return _bind_candidate_to_reused_customer(
            cand,
            cust,
            alias_id=None,
            reuse_kind="batch",
        )

    notes = (notes_summary or "").strip() or None
    base_note = f"Provisional customer created from DSI import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note

    existing_cust = find_existing_provisional_customer_by_canonical_name(session, proposal)
    if existing_cust is not None:
        row = existing_cust
        created_new_customer = False
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
        created_new_customer = True

    raw = raw_evidence
    alias_notes = f"Alias from provisional customer create (candidate {cand.id})"
    alias_id = _insert_approved_customer_alias_on_conflict_do_nothing(
        session,
        customer_id=int(row.id),
        raw_token=raw,
        normalized_token=nt,
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        notes=alias_notes,
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    if alias_id is None:
        race_alias = _lookup_approved_customer_alias_for_scope(
            session,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
        )
        if race_alias is None:
            raise StewardOpError("Could not create or reuse customer alias for scope", status_code=409)
        alias_lookup[scope_key] = race_alias
        keeper = session.get(DimCustomer, int(race_alias.customer_id))
        if keeper is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        if created_new_customer and row.id != keeper.id:
            session.delete(row)
        return _bind_candidate_to_reused_customer(
            cand,
            keeper,
            alias_id=int(race_alias.id),
            reuse_kind="race",
        )

    alias_lookup[scope_key] = session.get(CustomerSourceTokenAlias, alias_id)
    batch_lookup[scope_key] = int(row.id)
    cand.status = "resolved"
    cand.suggested_entity_id = row.id
    cand.match_reason = "steward_created_provisional_customer"

    return {
        "ok": True,
        "created": True,
        "customer_id": row.id,
        "customer_code": row.code,
        "alias_id": alias_id,
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

    scope_keys: set[tuple[str, int, int]] = set()
    for cand in found.values():
        if cand.entity_type != "customer_dealer_token":
            continue
        meta = _scope_key_for_dsi_candidate(cand)
        if meta is not None:
            scope_keys.add(meta[0])
    approved_alias_by_scope = _load_approved_customer_aliases_for_scopes(session, scope_keys)
    batch_customer_id_by_scope: dict[tuple[str, int, int], int] = {}

    results: list[dict[str, Any]] = []
    total = len(candidate_ids)
    applied_before_commit = 0
    created_count = 0
    reused_count = 0
    skipped_count = 0

    for idx, cid in enumerate(candidate_ids):
        if on_progress is not None:
            on_progress(idx + 1, total)
        cand = found.get(cid)
        if cand is None:
            skipped_count += 1
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
                approved_alias_by_scope=approved_alias_by_scope,
                batch_customer_id_by_scope=batch_customer_id_by_scope,
            )
            applied_before_commit += 1
            if out.get("created"):
                created_count += 1
            elif out.get("reused") or out.get("idempotent"):
                reused_count += 1
            else:
                created_count += 1
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
            skipped_count += 1
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
        "counts": {
            "created": created_count,
            "reused": reused_count,
            "skipped": skipped_count,
        },
        "results": results,
        "totals": {
            "ok_count": ok_n,
            "not_ok_count": len(results) - ok_n,
            "staging_rows_affected": rows_affected,
            "total_units_affected": units,
            "total_reported_value_affected": value,
        },
    }
