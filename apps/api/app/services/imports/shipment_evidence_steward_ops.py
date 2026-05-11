"""Steward apply for shipment evidence mapping candidates (sync Session).

Distributor apply updates ``ShipmentEvidenceLine`` rows in place (``distributor_id`` + resolution).
Customer apply sets ``customer_resolution_status`` to ``resolved`` on scoped lines after alias creation
(no ``customer_id`` FK); ``customer_token_raw`` is preserved for audit / upsert refresh.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimRegion
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    enrich_shipment_customer_token_candidates,
)


class ShipmentStewardOpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = message


def _first_sample_raw(cand: ImportEntityMappingCandidate) -> str:
    toks = _source_tokens_from_context(cand)
    if toks:
        return toks[0][:512]
    samples = cand.sample_raw_values or []
    for s in samples:
        if isinstance(s, str) and s.strip():
            return s.strip()[:512]
    return (cand.normalized_key or "").strip()[:512]


def _source_tokens_from_context(cand: ImportEntityMappingCandidate) -> list[str]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("source_tokens")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            t = x.strip()[:512]
            if t not in out:
                out.append(t)
    return out


def _special_category_from_context(cand: ImportEntityMappingCandidate) -> str | None:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    v = ctx.get("special_category")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _conflicting_customer_alias(
    db: Session,
    *,
    target_customer_id: int,
    normalized_token: str,
    source_definition_id: int | None,
) -> CustomerSourceTokenAlias | None:
    nt = (normalized_token or "").strip()[:512]
    if not nt:
        return None
    q = select(CustomerSourceTokenAlias).where(
        CustomerSourceTokenAlias.normalized_token == nt,
        CustomerSourceTokenAlias.status == "approved",
        CustomerSourceTokenAlias.customer_id != int(target_customer_id),
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.source_definition_id == int(source_definition_id),
            )
        )
    else:
        q = q.where(CustomerSourceTokenAlias.source_definition_id.is_(None))
    return db.scalars(q.limit(1)).first()


def _append_customer_aliases_for_shipment_candidate(
    db: Session,
    *,
    customer_id: int,
    cand: ImportEntityMappingCandidate,
    raw_tokens: list[str],
    notes: str,
) -> list[int]:
    """Create approved ``CustomerSourceTokenAlias`` rows for each raw token (skips exact duplicates)."""
    alias_ids: list[int] = []
    sid = cand.source_definition_id
    jid = cand.import_job_id
    cid = cand.id
    seen_raw: set[str] = set()
    for raw in raw_tokens:
        raw_s = (raw or "").strip()[:512]
        if not raw_s or raw_s in seen_raw:
            continue
        seen_raw.add(raw_s)
        nt = _norm_key(raw_s)
        if not nt:
            continue
        conds = [
            CustomerSourceTokenAlias.customer_id == int(customer_id),
            CustomerSourceTokenAlias.raw_token == raw_s,
            CustomerSourceTokenAlias.normalized_token == nt[:512],
            CustomerSourceTokenAlias.status == "approved",
        ]
        if sid is not None:
            conds.append(
                or_(
                    CustomerSourceTokenAlias.source_definition_id.is_(None),
                    CustomerSourceTokenAlias.source_definition_id == int(sid),
                )
            )
        else:
            conds.append(CustomerSourceTokenAlias.source_definition_id.is_(None))
        existing_id = db.scalar(select(CustomerSourceTokenAlias.id).where(*conds))
        if existing_id is not None:
            alias_ids.append(int(existing_id))
            continue
        conflict = _conflicting_customer_alias(
            db,
            target_customer_id=customer_id,
            normalized_token=nt,
            source_definition_id=sid,
        )
        if conflict is not None:
            raise ShipmentStewardOpError(
                "A source token normalises to an approved alias for a different customer",
                status_code=409,
            )
        alias = CustomerSourceTokenAlias(
            customer_id=int(customer_id),
            raw_token=raw_s,
            normalized_token=nt[:512],
            source_definition_id=sid,
            distributor_id=None,
            dealer_group_token=None,
            status="approved",
            notes=notes[:1024] if notes else None,
            created_from_import_job_id=jid,
            import_entity_mapping_candidate_id=cid,
        )
        try:
            with db.begin_nested():
                db.add(alias)
                db.flush()
        except IntegrityError:
            dup = db.scalars(
                select(CustomerSourceTokenAlias)
                .where(
                    CustomerSourceTokenAlias.customer_id == int(customer_id),
                    CustomerSourceTokenAlias.raw_token == raw_s,
                    CustomerSourceTokenAlias.normalized_token == nt[:512],
                )
                .limit(1)
            ).first()
            if dup is not None:
                alias_ids.append(int(dup.id))
                continue
            raise ShipmentStewardOpError(
                "Could not create customer alias (duplicate or conflict)",
                status_code=409,
            ) from None
        alias_ids.append(int(alias.id))
    return alias_ids


def _allocate_tmp_distributor_code(db: Session) -> str:
    for _ in range(32):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cand = f"TMP-DIST-{stamp}-{secrets.token_hex(3).upper()}"[:32]
        exists = db.scalar(select(DimDistributor.id).where(DimDistributor.code == cand))
        if exists is None:
            return cand
    raise ShipmentStewardOpError("Could not allocate temporary distributor code", status_code=503)


def _line_ids_from_context(cand: ImportEntityMappingCandidate) -> list[int]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("line_ids")
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _display_name_from_context_or_sample(
    cand: ImportEntityMappingCandidate, display_name: str | None, raw_fallback: str
) -> str:
    d = (display_name or "").strip()
    if d:
        return d[:256]
    ctx = cand.context if isinstance(cand.context, dict) else {}
    sn = ctx.get("suggested_name")
    if isinstance(sn, str) and sn.strip():
        return sn.strip()[:256]
    r = (raw_fallback or "").strip()
    return r[:256] if r else ""


_VALID_SHIPMENT_CUSTOMER_PARTNER_TIERS = frozenset(
    {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}
)


def _verify_line_scope(db: Session, cand: ImportEntityMappingCandidate, line_ids: list[int]) -> None:
    jid = int(cand.import_job_id)
    for lid in line_ids:
        row = db.get(ShipmentEvidenceLine, lid)
        if not row or int(row.import_job_id) != jid:
            raise ShipmentStewardOpError(f"Line {lid} not in scope for candidate job {jid}", status_code=400)


def _update_lines_resolved(
    db: Session,
    *,
    line_ids: list[int],
    distributor_id: int,
    resolution_token: str,
) -> int:
    n = 0
    tok = (resolution_token or "")[:512]
    for lid in line_ids:
        line = db.get(ShipmentEvidenceLine, lid)
        if line is None:
            continue
        line.distributor_id = int(distributor_id)
        line.distributor_resolution_status = "resolved"
        line.distributor_resolution_token = tok
        n += 1
    return n


def execute_map_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    dist = db.get(DimDistributor, int(distributor_id))
    if not dist:
        raise ShipmentStewardOpError("distributor_id not found", status_code=404)
    raw = (raw_token or _first_sample_raw(cand)).strip()
    if not raw:
        raise ShipmentStewardOpError("raw_token required", status_code=400)
    nt = _norm_key(raw)
    if not nt:
        raise ShipmentStewardOpError("raw_token empty after normalization", status_code=400)

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    alias = DistributorSourceTokenAlias(
        distributor_id=int(distributor_id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Mapped from shipment evidence candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ShipmentStewardOpError("Could not create distributor alias (duplicate or conflict)", status_code=409) from exc

    _update_lines_resolved(db, line_ids=line_ids, distributor_id=int(distributor_id), resolution_token=raw)
    cand.status = "resolved"
    cand.suggested_entity_id = int(distributor_id)
    cand.match_reason = "steward_map_existing_distributor"
    db.add(cand)
    db.commit()
    db.refresh(alias)
    return {"ok": True, "alias_id": int(alias.id), "distributor_id": int(distributor_id), "candidate_id": int(cand.id), "lines_updated": len(line_ids)}


def execute_create_provisional_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    distributor_code: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)

    raw = _first_sample_raw(cand)
    nt = _norm_key(raw)
    if not nt:
        raise ShipmentStewardOpError("Token empty after normalization", status_code=400)
    if nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS and not confirm_for_suspicious_token:
        raise ShipmentStewardOpError(
            "suspicious_token_requires_confirm — set confirm_for_suspicious_token=true",
            status_code=400,
        )

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    code = (distributor_code or "").strip()[:32] or _allocate_tmp_distributor_code(db)
    if db.scalar(select(DimDistributor.id).where(DimDistributor.code == code)) is not None:
        raise ShipmentStewardOpError("distributor_code already exists", status_code=409)

    name = _display_name_from_context_or_sample(cand, display_name, raw) or code
    row = DimDistributor(code=code, name=name)
    db.add(row)
    db.flush()

    alias = DistributorSourceTokenAlias(
        distributor_id=int(row.id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Provisional distributor from shipment evidence candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ShipmentStewardOpError("Could not create provisional distributor or alias", status_code=409) from exc

    _update_lines_resolved(db, line_ids=line_ids, distributor_id=int(row.id), resolution_token=raw)
    cand.status = "resolved"
    cand.suggested_entity_id = int(row.id)
    cand.match_reason = "steward_created_provisional_distributor"
    db.add(cand)
    db.commit()
    db.refresh(row)
    db.refresh(alias)
    return {
        "ok": True,
        "distributor_id": int(row.id),
        "distributor_code": row.code,
        "alias_id": int(alias.id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def _allocate_tmp_customer_code(db: Session) -> str:
    for _ in range(32):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        code_candidate = f"TMP-CUST-{stamp}-{secrets.token_hex(2).upper()}"[:64]
        exists = db.scalar(select(DimCustomer.id).where(DimCustomer.code == code_candidate))
        if exists is None:
            return code_candidate
    raise ShipmentStewardOpError("Could not allocate temporary customer code", status_code=503)


def _re_enrich_open_shipment_customer_candidates(db: Session, cand: ImportEntityMappingCandidate) -> None:
    """Rescore non-terminal shipment customer candidates after aliases change (same import job)."""
    enrich_shipment_customer_token_candidates(
        db,
        import_job_id=int(cand.import_job_id),
        source_definition_id=int(cand.source_definition_id) if cand.source_definition_id is not None else None,
    )


def _mark_customer_lines_resolved(db: Session, line_ids: list[int]) -> int:
    n = 0
    for lid in line_ids:
        line = db.get(ShipmentEvidenceLine, lid)
        if line is None:
            continue
        line.customer_resolution_status = "resolved"
        db.add(line)
        n += 1
    return n


def execute_map_shipment_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_customer_token candidate", status_code=400)
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    if _special_category_from_context(cand) in ("noise_only", "internal_note"):
        raise ShipmentStewardOpError(
            "This candidate is a special category row (not a channel partner name); it cannot be mapped to a customer",
            status_code=400,
        )
    cust = db.get(DimCustomer, int(customer_id))
    if not cust:
        raise ShipmentStewardOpError("customer_id not found", status_code=404)

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    tokens = _source_tokens_from_context(cand)
    if not tokens:
        alt = (raw_token or "").strip() or _first_sample_raw(cand)
        tokens = [alt] if alt else []
    if not tokens:
        raise ShipmentStewardOpError("No source tokens available for this candidate", status_code=400)

    notes = f"Mapped from shipment evidence candidate {cand.id} (job {cand.import_job_id})"
    alias_ids = _append_customer_aliases_for_shipment_candidate(
        db,
        customer_id=int(customer_id),
        cand=cand,
        raw_tokens=tokens,
        notes=notes,
    )
    if not alias_ids:
        raise ShipmentStewardOpError("No customer aliases were created (tokens normalised to empty)", status_code=400)

    _mark_customer_lines_resolved(db, line_ids)
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer_id)
    cand.match_reason = "steward_map_existing_customer"
    db.add(cand)
    _re_enrich_open_shipment_customer_candidates(db, cand)
    db.commit()
    return {
        "ok": True,
        "alias_id": int(alias_ids[0]),
        "alias_ids": alias_ids,
        "customer_id": int(customer_id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def execute_create_provisional_shipment_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    region_id: int | None,
    channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_customer_token candidate", status_code=400)
    if _special_category_from_context(cand) in ("noise_only", "internal_note"):
        raise ShipmentStewardOpError(
            "This candidate is a special category row (for example retail, sample-only text, or an internal note). "
            "Create provisional customer is disabled until the source data represents a real partner name.",
            status_code=400,
        )
    if (
        cand.status == "resolved"
        and cand.match_reason == "steward_created_provisional_customer"
        and cand.suggested_entity_id
    ):
        cust = db.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            tokens = _source_tokens_from_context(cand)
            if not tokens:
                fb = _first_sample_raw(cand)
                tokens = [fb] if fb.strip() else []
            notes = f"Alias from provisional customer create (shipment evidence candidate {cand.id})"
            alias_ids = _append_customer_aliases_for_shipment_candidate(
                db,
                customer_id=int(cust.id),
                cand=cand,
                raw_tokens=tokens,
                notes=notes,
            )
            _re_enrich_open_shipment_customer_candidates(db, cand)
            db.commit()
            return {
                "ok": True,
                "idempotent": True,
                "candidate_id": cand.id,
                "customer_id": cust.id,
                "customer_code": cust.code,
                "alias_id": int(alias_ids[0]) if alias_ids else None,
                "alias_ids": alias_ids,
                "lines_updated": 0,
            }

    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)

    tier = (partner_tier or "unmanaged").strip().lower()
    if tier not in _VALID_SHIPMENT_CUSTOMER_PARTNER_TIERS:
        raise ShipmentStewardOpError("Invalid partner_tier", status_code=400)

    if region_id is not None and db.get(DimRegion, int(region_id)) is None:
        raise ShipmentStewardOpError("region_id not found", status_code=400)
    if channel_id is not None and db.get(DimChannel, int(channel_id)) is None:
        raise ShipmentStewardOpError("channel_id not found", status_code=400)
    if preferred_distributor_id is not None and db.get(DimDistributor, int(preferred_distributor_id)) is None:
        raise ShipmentStewardOpError("preferred_distributor_id not found", status_code=400)

    tokens = _source_tokens_from_context(cand)
    if not tokens:
        fb = _first_sample_raw(cand)
        tokens = [fb] if fb.strip() else []
    if not tokens or not any(_norm_key(t) for t in tokens):
        raise ShipmentStewardOpError("Token empty — no usable source evidence for this candidate", status_code=400)

    raw0 = tokens[0]
    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    proposal = _display_name_from_context_or_sample(cand, display_name, raw0).strip()
    if not proposal:
        proposal = "Unknown customer"
    notes = (notes_summary or "").strip() or None
    base_note = f"Provisional customer created from shipment evidence import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note

    code = _allocate_tmp_customer_code(db)
    row = DimCustomer(
        code=code,
        name=proposal[:256],
        customer_status="unverified",
        partner_tier=tier,
        notes_summary=merged_notes[:512],
        region_id=region_id,
        channel_id=channel_id,
        preferred_distributor_id=preferred_distributor_id,
    )
    db.add(row)
    db.flush()

    alias_note = f"Alias from provisional customer create (shipment evidence candidate {cand.id})"
    try:
        alias_ids = _append_customer_aliases_for_shipment_candidate(
            db,
            customer_id=int(row.id),
            cand=cand,
            raw_tokens=tokens,
            notes=alias_note,
        )
    except ShipmentStewardOpError:
        db.rollback()
        raise
    if not alias_ids:
        db.rollback()
        raise ShipmentStewardOpError("Could not create customer aliases for source tokens", status_code=409)

    _mark_customer_lines_resolved(db, line_ids)
    cand.status = "resolved"
    cand.suggested_entity_id = int(row.id)
    cand.match_reason = "steward_created_provisional_customer"
    db.add(cand)
    _re_enrich_open_shipment_customer_candidates(db, cand)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "customer_id": int(row.id),
        "customer_code": row.code,
        "alias_id": int(alias_ids[0]),
        "alias_ids": alias_ids,
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def execute_bulk_create_provisional_shipment_customers(
    db: Session,
    *,
    job_id: int,
    candidate_ids: list[int],
    per_candidate_display_name: dict[int, str] | None,
    region_id: int | None,
    channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
) -> dict[str, Any]:
    """Run provisional customer create for many candidates (one commit per inner call)."""
    per = per_candidate_display_name or {}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for cid in candidate_ids:
        cand = db.get(ImportEntityMappingCandidate, int(cid))
        if not cand or int(cand.import_job_id) != int(job_id):
            errors.append({"candidate_id": cid, "message": "Candidate not found for this job"})
            continue
        if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
            errors.append({"candidate_id": cid, "message": "Not shipment_customer_token"})
            continue
        try:
            dn = per.get(int(cid))
            out = execute_create_provisional_shipment_customer(
                db,
                cand,
                display_name=dn,
                region_id=region_id,
                channel_id=channel_id,
                preferred_distributor_id=preferred_distributor_id,
                partner_tier=partner_tier,
                notes_summary=notes_summary,
            )
            results.append(out)
        except ShipmentStewardOpError as exc:
            errors.append({"candidate_id": cid, "message": exc.detail})
    return {"ok": len(errors) == 0, "results": results, "errors": errors}
