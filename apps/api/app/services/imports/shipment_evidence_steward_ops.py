"""Steward apply for shipment evidence mapping candidates (sync Session).

Distributor apply updates ``ShipmentEvidenceLine`` rows in place (``distributor_id`` + resolution).
Customer apply sets ``customer_resolution_status`` to ``resolved`` and stamps ``customer_id`` on
scoped lines after alias creation. ``customer_dealer_token`` is refreshed from import upserts
without clearing steward resolution (upsert omits resolution columns).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import (
    CustomerContact,
    CustomerLocation,
    DimChannel,
    DimCustomer,
    DimDistributor,
    DimRegion,
    DistributorContact,
    DistributorLocation,
)
from app.models.facts import FactInboundShipment, FactInventoryDistributor, FactSalesSellin, FactSalesSellout
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.utils.json_safe import to_jsonable
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
from app.services.imports.provisional_entity_consolidation import _repoint_customer_id_references
from app.services.imports.provisional_entity_identity import (
    canonical_provisional_entity_name_key,
    find_existing_provisional_customer_by_canonical_name,
    find_existing_provisional_distributor_by_canonical_name,
    is_non_entity_customer_provisional_token,
)
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CANDIDATE_TERMINAL_STATUSES,
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    enrich_shipment_customer_token_candidates,
    enrich_shipment_distributor_candidates,
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
    if not line_ids:
        return
    jid = int(cand.import_job_id)
    unique_ids = list(dict.fromkeys(int(x) for x in line_ids))
    found = {
        int(x)
        for x in db.scalars(
            select(ShipmentEvidenceLine.id).where(
                ShipmentEvidenceLine.id.in_(unique_ids),
                ShipmentEvidenceLine.import_job_id == jid,
            )
        ).all()
    }
    for lid in unique_ids:
        if lid not in found:
            raise ShipmentStewardOpError(f"Line {lid} not in scope for candidate job {jid}", status_code=400)


def _update_lines_resolved(
    db: Session,
    *,
    line_ids: list[int],
    distributor_id: int,
    resolution_token: str,
) -> int:
    if not line_ids:
        return 0
    unique_ids = list(dict.fromkeys(int(x) for x in line_ids))
    tok = (resolution_token or "")[:512]
    result = db.execute(
        update(ShipmentEvidenceLine)
        .where(ShipmentEvidenceLine.id.in_(unique_ids))
        .values(
            distributor_id=int(distributor_id),
            distributor_resolution_status="resolved",
            distributor_resolution_token=tok,
        )
    )
    return int(result.rowcount or 0)


def _apply_map_shipment_distributor_without_commit(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
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
    return {
        "ok": True,
        "alias_id": int(alias.id),
        "distributor_id": int(distributor_id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def execute_map_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    out = _apply_map_shipment_distributor_without_commit(
        db, cand, distributor_id=distributor_id, raw_token=raw_token
    )
    db.commit()
    alias = db.get(DistributorSourceTokenAlias, int(out["alias_id"]))
    if alias is not None:
        db.refresh(alias)
    return out


def _apply_create_provisional_shipment_distributor_without_commit(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    distributor_code: str | None,
    confirm_for_suspicious_token: bool,
    bypass_suspicious_token_gate: bool = False,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)

    raw = _first_sample_raw(cand)
    nt = _norm_key(raw)
    if not nt:
        raise ShipmentStewardOpError("Token empty after normalization", status_code=400)
    if (
        nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
        and not confirm_for_suspicious_token
        and not bypass_suspicious_token_gate
    ):
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
    existing_dist = find_existing_provisional_distributor_by_canonical_name(db, name)
    if existing_dist is not None:
        row = existing_dist
    else:
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
    return {
        "ok": True,
        "distributor_id": int(row.id),
        "distributor_code": row.code,
        "alias_id": int(alias.id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def execute_create_provisional_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    distributor_code: str | None,
    confirm_for_suspicious_token: bool,
    bypass_suspicious_token_gate: bool = False,
) -> dict[str, Any]:
    out = _apply_create_provisional_shipment_distributor_without_commit(
        db,
        cand,
        display_name=display_name,
        distributor_code=distributor_code,
        confirm_for_suspicious_token=confirm_for_suspicious_token,
        bypass_suspicious_token_gate=bypass_suspicious_token_gate,
    )
    db.commit()
    dist = db.get(DimDistributor, int(out["distributor_id"]))
    alias = db.get(DistributorSourceTokenAlias, int(out["alias_id"]))
    if dist is not None:
        db.refresh(dist)
    if alias is not None:
        db.refresh(alias)
    return out


def _allocate_tmp_customer_code(db: Session) -> str:
    for _ in range(32):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        code_candidate = f"TMP-CUST-{stamp}-{secrets.token_hex(2).upper()}"[:64]
        exists = db.scalar(select(DimCustomer.id).where(DimCustomer.code == code_candidate))
        if exists is None:
            return code_candidate
    raise ShipmentStewardOpError("Could not allocate temporary customer code", status_code=503)


def _re_enrich_shipment_customer_candidates_for_job(
    db: Session, *, import_job_id: int, source_definition_id: int | None
) -> None:
    """Rescore non-terminal shipment customer candidates after aliases change (same import job)."""
    enrich_shipment_customer_token_candidates(
        db,
        import_job_id=int(import_job_id),
        source_definition_id=source_definition_id,
    )


def _re_enrich_open_shipment_customer_candidates(db: Session, cand: ImportEntityMappingCandidate) -> None:
    _re_enrich_shipment_customer_candidates_for_job(
        db,
        import_job_id=int(cand.import_job_id),
        source_definition_id=int(cand.source_definition_id) if cand.source_definition_id is not None else None,
    )


def _mark_customer_lines_resolved(db: Session, line_ids: list[int], customer_id: int) -> int:
    if not line_ids:
        return 0
    unique_ids = list(dict.fromkeys(int(x) for x in line_ids))
    cid = int(customer_id)
    result = db.execute(
        update(ShipmentEvidenceLine)
        .where(ShipmentEvidenceLine.id.in_(unique_ids))
        .values(customer_resolution_status="resolved", customer_id=cid)
    )
    return int(result.rowcount or 0)


def _apply_map_shipment_customer_without_commit(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
    bypass_partner_text_guards: bool = False,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_customer_token candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    if (
        not bypass_partner_text_guards
        and _special_category_from_context(cand) in ("noise_only", "internal_note")
    ):
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

    _mark_customer_lines_resolved(db, line_ids, int(customer_id))
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer_id)
    cand.match_reason = "steward_map_existing_customer"
    db.add(cand)
    return {
        "ok": True,
        "alias_id": int(alias_ids[0]),
        "alias_ids": alias_ids,
        "customer_id": int(customer_id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }


def execute_map_shipment_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
    bypass_partner_text_guards: bool = False,
) -> dict[str, Any]:
    out = _apply_map_shipment_customer_without_commit(
        db,
        cand,
        customer_id=customer_id,
        raw_token=raw_token,
        bypass_partner_text_guards=bypass_partner_text_guards,
    )
    _re_enrich_open_shipment_customer_candidates(db, cand)
    db.commit()
    return out


def _apply_create_provisional_shipment_customer_without_commit(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    region_id: int | None,
    channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
    bypass_partner_text_guards: bool = False,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_customer_token candidate", status_code=400)
    if (
        not bypass_partner_text_guards
        and _special_category_from_context(cand) in ("noise_only", "internal_note")
    ):
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
            line_ids = _line_ids_from_context(cand)
            n_stamp = _mark_customer_lines_resolved(db, line_ids, int(cust.id)) if line_ids else 0
            return {
                "ok": True,
                "idempotent": True,
                "candidate_id": cand.id,
                "customer_id": cust.id,
                "customer_code": cust.code,
                "alias_id": int(alias_ids[0]) if alias_ids else None,
                "alias_ids": alias_ids,
                "lines_updated": n_stamp,
            }

    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
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
    if is_non_entity_customer_provisional_token(raw_token=raw0, display_name=proposal):
        raise ShipmentStewardOpError(
            "Token or display name looks like policy/note text (not a customer entity); "
            "ignore or map to an existing customer instead.",
            status_code=400,
        )
    notes = (notes_summary or "").strip() or None
    base_note = f"Provisional customer created from shipment evidence import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note

    existing_cust = find_existing_provisional_customer_by_canonical_name(db, proposal)
    if existing_cust is not None:
        row = existing_cust
    else:
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

    _mark_customer_lines_resolved(db, line_ids, int(row.id))
    cand.status = "resolved"
    cand.suggested_entity_id = int(row.id)
    cand.match_reason = "steward_created_provisional_customer"
    db.add(cand)
    return {
        "ok": True,
        "customer_id": int(row.id),
        "customer_code": row.code,
        "alias_id": int(alias_ids[0]),
        "alias_ids": alias_ids,
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
    bypass_partner_text_guards: bool = False,
) -> dict[str, Any]:
    out = _apply_create_provisional_shipment_customer_without_commit(
        db,
        cand,
        display_name=display_name,
        region_id=region_id,
        channel_id=channel_id,
        preferred_distributor_id=preferred_distributor_id,
        partner_tier=partner_tier,
        notes_summary=notes_summary,
        bypass_partner_text_guards=bypass_partner_text_guards,
    )
    _re_enrich_open_shipment_customer_candidates(db, cand)
    db.commit()
    if not out.get("idempotent"):
        row = db.get(DimCustomer, int(out["customer_id"]))
        if row is not None:
            db.refresh(row)
    return out


def _provisional_customer_bulk_group_key(cand: ImportEntityMappingCandidate, per: dict[int, str]) -> str:
    """Stable bucket for bulk provisional: same effective display name → one DimCustomer."""
    tokens = _source_tokens_from_context(cand)
    raw0 = tokens[0] if tokens else ""
    dn = per.get(int(cand.id))
    disp = _display_name_from_context_or_sample(cand, dn, raw0).strip()
    nk = _norm_key(disp)
    if nk:
        return nk
    return f"__singleton_candidate_{int(cand.id)}__"


def _apply_attach_shipment_customer_candidate_without_commit(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    notes_summary: str | None,
) -> dict[str, Any]:
    """Attach a second (or later) mapping candidate to an existing provisional customer (aliases + line stamp)."""
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_customer_token candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    if _special_category_from_context(cand) in ("noise_only", "internal_note"):
        raise ShipmentStewardOpError(
            "This candidate is a special category row; it cannot be attached to a customer",
            status_code=400,
        )
    cust = db.get(DimCustomer, int(customer_id))
    if not cust:
        raise ShipmentStewardOpError("customer_id not found", status_code=404)

    tokens = _source_tokens_from_context(cand)
    if not tokens:
        fb = _first_sample_raw(cand)
        tokens = [fb] if fb.strip() else []
    if not tokens or not any(_norm_key(t) for t in tokens):
        raise ShipmentStewardOpError("Token empty — no usable source evidence for this candidate", status_code=400)

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    base_note = f"Alias from grouped provisional customer (shipment evidence candidate {cand.id}, job {cand.import_job_id})"
    extra = (notes_summary or "").strip()
    alias_note = f"{base_note} {extra}" if extra else base_note

    alias_ids = _append_customer_aliases_for_shipment_candidate(
        db,
        customer_id=int(customer_id),
        cand=cand,
        raw_tokens=tokens,
        notes=alias_note,
    )
    if not alias_ids:
        raise ShipmentStewardOpError("No customer aliases were created (tokens normalised to empty)", status_code=400)

    _mark_customer_lines_resolved(db, line_ids, int(customer_id))
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer_id)
    cand.match_reason = "steward_created_provisional_customer"
    db.add(cand)
    return {
        "ok": True,
        "customer_id": int(customer_id),
        "candidate_id": int(cand.id),
        "alias_id": int(alias_ids[0]),
        "alias_ids": alias_ids,
        "lines_updated": len(line_ids),
        "grouped_attach": True,
    }


def execute_attach_shipment_customer_candidate_to_existing_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    notes_summary: str | None,
) -> dict[str, Any]:
    out = _apply_attach_shipment_customer_candidate_without_commit(
        db, cand, customer_id=customer_id, notes_summary=notes_summary
    )
    _re_enrich_open_shipment_customer_candidates(db, cand)
    db.commit()
    return out


ALLOWED_MANUAL_SPECIAL_CATEGORIES = frozenset({"noise_only", "internal_note"})


def execute_manual_special_category_shipment_candidate(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    special_category: str,
) -> dict[str, Any]:
    """Steward: mark candidate as manual special category (no provisional); lines unchanged; terminal ``ignored``."""
    if cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
        raise ShipmentStewardOpError("Unsupported entity type for shipment mapping candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    sc = (special_category or "").strip()
    if sc not in ALLOWED_MANUAL_SPECIAL_CATEGORIES:
        raise ShipmentStewardOpError(
            "special_category must be one of: noise_only, internal_note",
            status_code=400,
        )
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    ctx["special_category"] = sc
    ctx["steward_manual_special_category"] = True
    cand.context = to_jsonable(ctx)
    cand.match_reason = "steward_manual_special_category"
    cand.status = "ignored"
    db.add(cand)
    db.commit()
    return {
        "ok": True,
        "candidate_id": int(cand.id),
        "status": cand.status,
        "special_category": sc,
    }


def execute_clear_special_category_shipment_candidate(
    db: Session,
    cand: ImportEntityMappingCandidate,
) -> dict[str, Any]:
    """Steward: remove special-category flags from context and return candidate to ``needs_review``."""
    if cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
        raise ShipmentStewardOpError("Unsupported entity type for shipment mapping candidate", status_code=400)
    if cand.status not in ("needs_review", "ignored"):
        raise ShipmentStewardOpError(
            "Clear special category is only for candidates in needs_review or ignored (manual special category)",
            status_code=400,
        )
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    if "special_category" not in ctx and not ctx.get("steward_manual_special_category"):
        raise ShipmentStewardOpError("No special category flag is set on this candidate", status_code=400)
    ctx.pop("special_category", None)
    ctx.pop("steward_manual_special_category", None)
    cand.context = to_jsonable(ctx)
    cand.status = "needs_review"
    cand.match_reason = None
    cand.suggested_entity_id = None
    db.add(cand)
    db.commit()
    jid = int(cand.import_job_id)
    sid = int(cand.source_definition_id) if cand.source_definition_id is not None else None
    if cand.entity_type == SHIPMENT_CUSTOMER_ENTITY:
        enrich_shipment_customer_token_candidates(db, import_job_id=jid, source_definition_id=sid)
    else:
        enrich_shipment_distributor_candidates(db, import_job_id=jid, source_definition_id=sid)
    db.commit()
    return {"ok": True, "candidate_id": int(cand.id), "status": cand.status}


def execute_reject_shipment_mapping_candidate(db: Session, cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    """Steward: reject candidate — no resolution, no auto-apply; evidence lines stay as-is."""
    if cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
        raise ShipmentStewardOpError("Unsupported entity type for shipment mapping candidate", status_code=400)
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    cand.status = "steward_rejected"
    cand.match_reason = "steward_rejected"
    db.add(cand)
    db.commit()
    return {"ok": True, "candidate_id": int(cand.id), "status": cand.status}


def execute_bulk_apply_shipment_candidate_plans(
    db: Session,
    *,
    import_job_id: int,
    candidate_ids: list[int],
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Apply persisted planner ``suggested_action`` for selected ``needs_review`` candidates.

    Used after import apply when rows were blocked only by name-review / special-category heuristics:
    partner-text guards are bypassed so the **existing** plan (map or provisional create) can execute.

    ``on_progress(current, total)`` is invoked once per candidate processed (for the background
    task UI); it is optional and defaults to a no-op so the synchronous call sites are unchanged.
    """
    applied: list[int] = []
    errors: list[dict[str, Any]] = []
    any_customer = False
    any_distributor = False
    total = len(candidate_ids)
    for processed, raw_id in enumerate(candidate_ids, start=1):
        if on_progress is not None:
            on_progress(processed, total)
        cid = int(raw_id)
        cand = db.get(ImportEntityMappingCandidate, cid)
        if not cand or int(cand.import_job_id) != int(import_job_id):
            errors.append({"candidate_id": cid, "reason": "not_found_or_wrong_job"})
            continue
        if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
            errors.append({"candidate_id": cid, "reason": "terminal_status"})
            continue
        if cand.status != "needs_review":
            errors.append({"candidate_id": cid, "reason": "status_not_needs_review"})
            continue
        ctx = cand.context if isinstance(cand.context, dict) else {}
        action = (str(ctx.get("suggested_action") or "")).strip()
        try:
            if cand.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY:
                any_distributor = True
                if action == "map_distributor":
                    eid = cand.suggested_entity_id
                    if eid is None:
                        raise ShipmentStewardOpError("plan missing suggested_entity_id", status_code=400)
                    _apply_map_shipment_distributor_without_commit(
                        db, cand, distributor_id=int(eid), raw_token=None
                    )
                    applied.append(cid)
                elif action == "create_provisional_distributor":
                    raw = _first_sample_raw(cand)
                    dn = _display_name_from_context_or_sample(cand, None, raw)
                    _apply_create_provisional_shipment_distributor_without_commit(
                        db,
                        cand,
                        display_name=dn.strip() or None,
                        distributor_code=None,
                        confirm_for_suspicious_token=False,
                        bypass_suspicious_token_gate=True,
                    )
                    applied.append(cid)
                else:
                    errors.append({"candidate_id": cid, "reason": f"unsupported_plan:{action or 'empty'}"})
            elif cand.entity_type == SHIPMENT_CUSTOMER_ENTITY:
                any_customer = True
                if action == "map_customer":
                    eid = cand.suggested_entity_id
                    if eid is None:
                        raise ShipmentStewardOpError("plan missing suggested_entity_id", status_code=400)
                    _apply_map_shipment_customer_without_commit(
                        db,
                        cand,
                        customer_id=int(eid),
                        raw_token=None,
                        bypass_partner_text_guards=True,
                    )
                    applied.append(cid)
                elif action == "create_provisional_customer":
                    raw = _first_sample_raw(cand)
                    dn = _display_name_from_context_or_sample(cand, None, raw)
                    _apply_create_provisional_shipment_customer_without_commit(
                        db,
                        cand,
                        display_name=dn.strip() or None,
                        region_id=None,
                        channel_id=None,
                        preferred_distributor_id=None,
                        partner_tier="unmanaged",
                        notes_summary=None,
                        bypass_partner_text_guards=True,
                    )
                    applied.append(cid)
                else:
                    errors.append({"candidate_id": cid, "reason": f"unsupported_plan:{action or 'empty'}"})
            else:
                errors.append({"candidate_id": cid, "reason": "unsupported_entity_type"})
        except ShipmentStewardOpError as exc:
            errors.append({"candidate_id": cid, "reason": str(exc.detail)})

    if applied:
        sid: int | None = None
        for cid in reversed(applied):
            c = db.get(ImportEntityMappingCandidate, cid)
            if c is not None:
                sid = int(c.source_definition_id) if c.source_definition_id is not None else None
                break
        if any_customer:
            enrich_shipment_customer_token_candidates(db, import_job_id=int(import_job_id), source_definition_id=sid)
            db.commit()
        if any_distributor:
            enrich_shipment_distributor_candidates(db, import_job_id=int(import_job_id), source_definition_id=sid)
            db.commit()

    return {"applied": applied, "errors": errors}


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
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Run provisional customer create for many candidates, grouping by effective display name (one DimCustomer per group).

    ``on_progress(current, total)`` is invoked once per group bucket processed (optional, defaults to
    a no-op) so the background task can surface progress without changing the synchronous call sites.
    """
    from collections import defaultdict

    per = per_candidate_display_name or {}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    cands: list[ImportEntityMappingCandidate] = []
    for cid in candidate_ids:
        cand = db.get(ImportEntityMappingCandidate, int(cid))
        if not cand or int(cand.import_job_id) != int(job_id):
            errors.append({"candidate_id": int(cid), "message": "Candidate not found for this job"})
            continue
        if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
            errors.append({"candidate_id": int(cid), "message": "Not shipment_customer_token"})
            continue
        cands.append(cand)

    buckets: dict[str, list[ImportEntityMappingCandidate]] = defaultdict(list)
    for cand in cands:
        buckets[_provisional_customer_bulk_group_key(cand, per)].append(cand)

    total_groups = len(buckets)
    for group_index, (_gk, group) in enumerate(buckets.items(), start=1):
        if on_progress is not None:
            on_progress(group_index, total_groups)
        group.sort(key=lambda c: int(c.id))
        leader = group[0]
        dn_leader = per.get(int(leader.id))
        try:
            out = _apply_create_provisional_shipment_customer_without_commit(
                db,
                leader,
                display_name=dn_leader,
                region_id=region_id,
                channel_id=channel_id,
                preferred_distributor_id=preferred_distributor_id,
                partner_tier=partner_tier,
                notes_summary=notes_summary,
            )
            results.append(out)
            cust_id = int(out["customer_id"])
            for follower in group[1:]:
                try:
                    out2 = _apply_attach_shipment_customer_candidate_without_commit(
                        db,
                        follower,
                        customer_id=cust_id,
                        notes_summary=notes_summary,
                    )
                    results.append(out2)
                except ShipmentStewardOpError as exc:
                    errors.append({"candidate_id": int(follower.id), "message": exc.detail})
        except ShipmentStewardOpError as exc:
            for c in group:
                errors.append({"candidate_id": int(c.id), "message": exc.detail})

    if results:
        sid: int | None = None
        for cand in cands:
            if cand.source_definition_id is not None:
                sid = int(cand.source_definition_id)
                break
        _re_enrich_shipment_customer_candidates_for_job(
            db, import_job_id=int(job_id), source_definition_id=sid
        )
        db.commit()

    return {"ok": len(errors) == 0, "results": results, "errors": errors}


def execute_bulk_map_shipment_customers(
    db: Session,
    *,
    customer_id: int,
    candidate_ids: list[int],
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Map many shipment customer candidates to one customer; enrich and commit once at the end.

    ``on_progress(current, total)`` is invoked once per candidate processed (optional, defaults to a
    no-op) so the background task can surface progress without changing the synchronous call sites.
    """
    mapped: list[int] = []
    errors: list[dict[str, Any]] = []
    job_id: int | None = None
    source_definition_id: int | None = None
    total = len(candidate_ids)
    for processed, cid in enumerate(candidate_ids, start=1):
        if on_progress is not None:
            on_progress(processed, total)
        cand = db.get(ImportEntityMappingCandidate, int(cid))
        if not cand or cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
            errors.append({"candidate_id": int(cid), "reason": "candidate_not_found_or_wrong_entity"})
            continue
        if job_id is None:
            job_id = int(cand.import_job_id)
        elif int(cand.import_job_id) != job_id:
            errors.append({"candidate_id": int(cid), "reason": "candidate_not_same_import_job"})
            continue
        if source_definition_id is None and cand.source_definition_id is not None:
            source_definition_id = int(cand.source_definition_id)
        try:
            _apply_map_shipment_customer_without_commit(
                db, cand, customer_id=int(customer_id), raw_token=None
            )
            mapped.append(int(cid))
        except ShipmentStewardOpError as exc:
            errors.append({"candidate_id": int(cid), "reason": str(exc.detail)})
    if mapped and job_id is not None:
        _re_enrich_shipment_customer_candidates_for_job(
            db, import_job_id=int(job_id), source_definition_id=source_definition_id
        )
        db.commit()
    return {"mapped": mapped, "errors": errors}


def merge_duplicate_shipment_provisional_customers_by_display_name(
    db: Session,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Merge unverified ``TMP-CUST-%`` customers that share the same normalised display ``name``.

    For each duplicate group the lowest ``id`` is kept. Aliases and shipment line ``customer_id``
    references are moved to the survivor; duplicate customers are deleted when they have no
    locations or contacts (otherwise the merge for that loser is skipped).

    Intended for one-off cleanup after bulk provisional created duplicates. Call with ``dry_run=True``
    first to inspect ``planned_merges``."""
    from collections import defaultdict

    rows = list(
        db.scalars(
            select(DimCustomer).where(
                DimCustomer.code.like("TMP-CUST-%"),
                DimCustomer.customer_status == "unverified",
            )
        ).all()
    )
    groups: dict[str, list[DimCustomer]] = defaultdict(list)
    for c in rows:
        nk = canonical_provisional_entity_name_key(c.name or "")
        key = nk if nk else f"__noname_{int(c.id)}"
        groups[key].append(c)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    planned: list[dict[str, Any]] = []
    for k, lst in sorted(dup_groups.items(), key=lambda kv: kv[0]):
        lst.sort(key=lambda x: int(x.id))
        keeper = lst[0]
        losers = lst[1:]
        planned.append(
            {
                "normalized_name_key": k,
                "keeper_id": int(keeper.id),
                "keeper_code": keeper.code,
                "keeper_name": keeper.name,
                "loser_ids": [int(x.id) for x in losers],
            }
        )

    out: dict[str, Any] = {
        "dry_run": dry_run,
        "planned_merges": planned,
        "merge_group_count": len(planned),
    }
    if dry_run:
        return out

    deleted: list[int] = []
    skipped: list[dict[str, Any]] = []
    for entry in planned:
        kid = int(entry["keeper_id"])
        for lid in entry["loser_ids"]:
            n_loc = int(
                db.scalar(select(func.count()).select_from(CustomerLocation).where(CustomerLocation.customer_id == lid))
                or 0
            )
            n_con = int(
                db.scalar(select(func.count()).select_from(CustomerContact).where(CustomerContact.customer_id == lid))
                or 0
            )
            if n_loc > 0 or n_con > 0:
                skipped.append({"customer_id": lid, "reason": "has_locations_or_contacts"})
                continue
            _repoint_customer_id_references(db, loser_id=lid, keeper_id=kid)
            aliases = list(
                db.scalars(select(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.customer_id == lid)).all()
            )
            for al in aliases:
                dup = db.scalars(
                    select(CustomerSourceTokenAlias)
                    .where(
                        CustomerSourceTokenAlias.customer_id == kid,
                        CustomerSourceTokenAlias.normalized_token == al.normalized_token,
                        CustomerSourceTokenAlias.raw_token == al.raw_token,
                    )
                    .limit(1)
                ).first()
                if dup is not None:
                    db.delete(al)
                else:
                    al.customer_id = kid
                    db.add(al)
            loser_row = db.get(DimCustomer, lid)
            if loser_row is not None:
                db.delete(loser_row)
            deleted.append(lid)
            db.flush()
    db.commit()
    out["deleted_customer_ids"] = deleted
    out["skipped"] = skipped
    return out


def _repoint_distributor_id_references(db: Session, *, loser_id: int, keeper_id: int) -> None:
    """Point foreign keys at ``keeper_id`` before deleting duplicate ``dim_distributor`` ``loser_id``."""
    db.execute(
        update(DimCustomer).where(DimCustomer.preferred_distributor_id == loser_id).values(preferred_distributor_id=keeper_id)
    )
    db.execute(
        update(FactSalesSellout).where(FactSalesSellout.distributor_id == loser_id).values(distributor_id=keeper_id)
    )
    db.execute(
        update(FactSalesSellin).where(FactSalesSellin.distributor_id == loser_id).values(distributor_id=keeper_id)
    )
    db.execute(
        update(FactInventoryDistributor).where(FactInventoryDistributor.distributor_id == loser_id).values(distributor_id=keeper_id)
    )
    db.execute(
        update(FactInboundShipment).where(FactInboundShipment.distributor_id == loser_id).values(distributor_id=keeper_id)
    )
    db.execute(
        update(ImportDistributorSiStagingLine)
        .where(ImportDistributorSiStagingLine.resolved_distributor_id == loser_id)
        .values(resolved_distributor_id=keeper_id)
    )
    db.execute(
        update(ImportEntityMappingCandidate)
        .where(
            ImportEntityMappingCandidate.suggested_entity_id == loser_id,
            ImportEntityMappingCandidate.entity_type.in_(("distributor_token", "shipment_distributor")),
        )
        .values(suggested_entity_id=keeper_id)
    )
    db.execute(
        update(CustomerSourceTokenAlias)
        .where(CustomerSourceTokenAlias.distributor_id == loser_id)
        .values(distributor_id=keeper_id)
    )


def merge_duplicate_shipment_provisional_distributors_by_display_name(
    db: Session,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Merge ``TMP-DIST-%`` distributors that share the same normalised display ``name``.

    For each duplicate group the lowest ``id`` is kept. Aliases and ``ShipmentEvidenceLine.distributor_id``
    are moved to the survivor; common FK references are repointed; duplicate rows are deleted when they
    have no distributor locations or contacts (otherwise that loser is skipped).

    Intended for one-off cleanup after bulk provisional created duplicates. Call with ``dry_run=True``
    first to inspect ``planned_merges``."""
    from collections import defaultdict

    rows = list(db.scalars(select(DimDistributor).where(DimDistributor.code.like("TMP-DIST-%"))).all())
    groups: dict[str, list[DimDistributor]] = defaultdict(list)
    for d in rows:
        nk = canonical_provisional_entity_name_key(d.name or "")
        key = nk if nk else f"__noname_{int(d.id)}"
        groups[key].append(d)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    planned: list[dict[str, Any]] = []
    for k, lst in sorted(dup_groups.items(), key=lambda kv: kv[0]):
        lst.sort(key=lambda x: int(x.id))
        keeper = lst[0]
        losers = lst[1:]
        planned.append(
            {
                "normalized_name_key": k,
                "keeper_id": int(keeper.id),
                "keeper_code": keeper.code,
                "keeper_name": keeper.name,
                "loser_ids": [int(x.id) for x in losers],
            }
        )

    out: dict[str, Any] = {
        "dry_run": dry_run,
        "planned_merges": planned,
        "merge_group_count": len(planned),
    }
    if dry_run:
        return out

    deleted: list[int] = []
    skipped: list[dict[str, Any]] = []
    for entry in planned:
        kid = int(entry["keeper_id"])
        for lid in entry["loser_ids"]:
            n_loc = int(
                db.scalar(
                    select(func.count()).select_from(DistributorLocation).where(DistributorLocation.distributor_id == lid)
                )
                or 0
            )
            n_con = int(
                db.scalar(
                    select(func.count()).select_from(DistributorContact).where(DistributorContact.distributor_id == lid)
                )
                or 0
            )
            if n_loc > 0 or n_con > 0:
                skipped.append({"distributor_id": lid, "reason": "has_locations_or_contacts"})
                continue
            _repoint_distributor_id_references(db, loser_id=lid, keeper_id=kid)
            aliases = list(
                db.scalars(select(DistributorSourceTokenAlias).where(DistributorSourceTokenAlias.distributor_id == lid)).all()
            )
            for al in aliases:
                dup = db.scalars(
                    select(DistributorSourceTokenAlias)
                    .where(
                        DistributorSourceTokenAlias.distributor_id == kid,
                        DistributorSourceTokenAlias.normalized_token == al.normalized_token,
                        DistributorSourceTokenAlias.raw_token == al.raw_token,
                    )
                    .limit(1)
                ).first()
                if dup is not None:
                    db.delete(al)
                else:
                    al.distributor_id = kid
                    db.add(al)
            db.execute(
                update(ShipmentEvidenceLine).where(ShipmentEvidenceLine.distributor_id == lid).values(distributor_id=kid)
            )
            db.execute(
                update(ImportEntityMappingCandidate)
                .where(
                    ImportEntityMappingCandidate.suggested_entity_id == lid,
                    ImportEntityMappingCandidate.entity_type.in_(("distributor_token", "shipment_distributor")),
                )
                .values(suggested_entity_id=kid)
            )
            loser_row = db.get(DimDistributor, lid)
            if loser_row is not None:
                db.delete(loser_row)
            deleted.append(lid)
            db.flush()
    db.commit()
    out["deleted_distributor_ids"] = deleted
    out["skipped"] = skipped
    return out
