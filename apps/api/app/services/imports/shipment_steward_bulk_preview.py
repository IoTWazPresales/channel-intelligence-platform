"""Read-only preview helpers for shipment steward bulk operations (sync Session).

Mirrors validation gates from ``shipment_evidence_steward_ops`` apply/execute paths without
writing to the database.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimRegion
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
from app.services.imports.provisional_entity_identity import (
    find_existing_provisional_customer_by_canonical_name,
    find_existing_provisional_distributor_by_canonical_name,
    is_non_entity_customer_provisional_token,
)
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CANDIDATE_TERMINAL_STATUSES,
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    _display_name_from_context_or_sample,
    _first_sample_raw,
    _line_ids_from_context,
    _source_tokens_from_context,
    _special_category_from_context,
    _verify_line_scope,
    _VALID_SHIPMENT_CUSTOMER_PARTNER_TIERS,
)


def _preview_line_scope(db: Session, cand: ImportEntityMappingCandidate, line_ids: list[int]) -> tuple[bool, str | None]:
    try:
        _verify_line_scope(db, cand, line_ids)
        return True, None
    except ShipmentStewardOpError as exc:
        return False, str(exc.detail)


def preview_reject_shipment_candidate(cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    """Preview bulk ignore (steward reject — ``steward_rejected`` terminal status)."""
    if cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Unsupported entity type for shipment mapping candidate",
        }
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    return {"ok": True, "detail": "Would set status steward_rejected"}


def preview_map_shipment_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Not a shipment_customer_token candidate",
        }
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    if _special_category_from_context(cand) in ("noise_only", "internal_note"):
        return {
            "ok": False,
            "skip_reason": "special_category",
            "detail": "This candidate is a special category row (not a channel partner name); it cannot be mapped to a customer",
        }
    cust = db.get(DimCustomer, int(customer_id))
    if not cust:
        return {"ok": False, "skip_reason": "customer_not_found", "detail": "customer_id not found"}

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        return {
            "ok": False,
            "skip_reason": "missing_line_ids",
            "detail": "candidate.context.line_ids missing or empty",
        }
    ok_scope, scope_detail = _preview_line_scope(db, cand, line_ids)
    if not ok_scope:
        return {"ok": False, "skip_reason": "line_scope", "detail": scope_detail or "Line scope invalid"}

    tokens = _source_tokens_from_context(cand)
    if not tokens:
        alt = (raw_token or "").strip() or _first_sample_raw(cand)
        tokens = [alt] if alt else []
    if not tokens:
        return {
            "ok": False,
            "skip_reason": "missing_token",
            "detail": "No source tokens available for this candidate",
        }
    if not any(_norm_key(t) for t in tokens):
        return {
            "ok": False,
            "skip_reason": "empty_norm",
            "detail": "No customer aliases would be created (tokens normalised to empty)",
        }

    raw_preview = tokens[0][:160]
    nt = _norm_key(tokens[0])
    return {
        "ok": True,
        "detail": "Would create CustomerSourceTokenAlias and stamp customer on evidence lines",
        "customer_id": int(customer_id),
        "customer_code": cust.code,
        "customer_name": cust.name,
        "alias_raw_preview": raw_preview,
        "alias_normalized_token": nt[:160] if nt else None,
        "lines_affected": len(line_ids),
    }


def preview_map_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Not a shipment_distributor candidate",
        }
    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    dist = db.get(DimDistributor, int(distributor_id))
    if not dist:
        return {"ok": False, "skip_reason": "distributor_not_found", "detail": "distributor_id not found"}
    raw = (raw_token or _first_sample_raw(cand)).strip()
    if not raw:
        return {"ok": False, "skip_reason": "missing_token", "detail": "raw_token required"}
    nt = _norm_key(raw)
    if not nt:
        return {"ok": False, "skip_reason": "empty_norm", "detail": "raw_token empty after normalization"}

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        return {
            "ok": False,
            "skip_reason": "missing_line_ids",
            "detail": "candidate.context.line_ids missing or empty",
        }
    ok_scope, scope_detail = _preview_line_scope(db, cand, line_ids)
    if not ok_scope:
        return {"ok": False, "skip_reason": "line_scope", "detail": scope_detail or "Line scope invalid"}

    return {
        "ok": True,
        "detail": "Would create DistributorSourceTokenAlias and stamp distributor on evidence lines",
        "distributor_id": int(distributor_id),
        "distributor_code": dist.code,
        "alias_raw_preview": raw[:160],
        "alias_normalized_token": nt[:160],
        "lines_affected": len(line_ids),
    }


def preview_create_provisional_shipment_customer(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    region_id: int | None = None,
    channel_id: int | None = None,
    preferred_distributor_id: int | None = None,
    partner_tier: str | None = None,
    notes_summary: str | None = None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Not a shipment_customer_token candidate",
        }
    if _special_category_from_context(cand) in ("noise_only", "internal_note"):
        return {
            "ok": False,
            "skip_reason": "special_category",
            "detail": "This candidate is a special category row; create provisional customer is disabled",
        }

    if (
        cand.status == "resolved"
        and cand.match_reason == "steward_created_provisional_customer"
        and cand.suggested_entity_id
    ):
        cust = db.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            return {
                "ok": True,
                "idempotent_noop": True,
                "detail": "Already resolved with provisional customer",
                "proposed_display_name": cust.name[:256],
                "customer_id": cust.id,
                "customer_code": cust.code,
            }

    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}

    tier = (partner_tier or "unmanaged").strip().lower()
    if tier not in _VALID_SHIPMENT_CUSTOMER_PARTNER_TIERS:
        return {"ok": False, "skip_reason": "invalid_partner_tier", "detail": "Invalid partner_tier"}

    if region_id is not None and db.get(DimRegion, int(region_id)) is None:
        return {"ok": False, "skip_reason": "region_not_found", "detail": "region_id not found"}
    if channel_id is not None and db.get(DimChannel, int(channel_id)) is None:
        return {"ok": False, "skip_reason": "channel_not_found", "detail": "channel_id not found"}
    if preferred_distributor_id is not None and db.get(DimDistributor, int(preferred_distributor_id)) is None:
        return {
            "ok": False,
            "skip_reason": "preferred_distributor_not_found",
            "detail": "preferred_distributor_id not found",
        }

    tokens = _source_tokens_from_context(cand)
    if not tokens:
        fb = _first_sample_raw(cand)
        tokens = [fb] if fb.strip() else []
    if not tokens or not any(_norm_key(t) for t in tokens):
        return {
            "ok": False,
            "skip_reason": "missing_token",
            "detail": "Token empty — no usable source evidence for this candidate",
        }

    raw0 = tokens[0]
    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        return {
            "ok": False,
            "skip_reason": "missing_line_ids",
            "detail": "candidate.context.line_ids missing or empty",
        }
    ok_scope, scope_detail = _preview_line_scope(db, cand, line_ids)
    if not ok_scope:
        return {"ok": False, "skip_reason": "line_scope", "detail": scope_detail or "Line scope invalid"}

    proposal = _display_name_from_context_or_sample(cand, display_name_override, raw0).strip()
    if not proposal:
        proposal = "Unknown customer"
    if is_non_entity_customer_provisional_token(raw_token=raw0, display_name=proposal):
        return {
            "ok": False,
            "skip_reason": "non_entity_token",
            "detail": "Token or display name looks like policy/note text (not a customer entity)",
        }

    existing = find_existing_provisional_customer_by_canonical_name(db, proposal)
    reused = existing is not None
    return {
        "ok": True,
        "detail": "Would create dim_customer (or reuse provisional) and CustomerSourceTokenAlias",
        "proposed_display_name": proposal[:256],
        "partner_tier": tier,
        "region_id": region_id,
        "channel_id": channel_id,
        "preferred_distributor_id": preferred_distributor_id,
        "reused_provisional_customer": reused,
        "existing_customer_id": int(existing.id) if existing is not None else None,
        "alias_raw_preview": raw0[:160],
        "lines_affected": len(line_ids),
        "notes_summary": (notes_summary or "").strip() or None,
    }


def preview_create_provisional_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    distributor_code_override: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Not a shipment_distributor candidate",
        }

    if (
        cand.status == "resolved"
        and cand.match_reason == "steward_created_provisional_distributor"
        and cand.suggested_entity_id
    ):
        dist = db.get(DimDistributor, int(cand.suggested_entity_id))
        if dist:
            return {
                "ok": True,
                "idempotent_noop": True,
                "detail": "Already resolved with provisional distributor",
                "proposed_display_name": dist.name[:256],
                "distributor_id": dist.id,
                "distributor_code": dist.code,
            }

    if cand.status in SHIPMENT_CANDIDATE_TERMINAL_STATUSES:
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}

    raw = _first_sample_raw(cand)
    nt = _norm_key(raw)
    if not nt:
        return {"ok": False, "skip_reason": "empty_norm", "detail": "Token empty after normalization"}
    suspicious = nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
    if suspicious and not confirm_for_suspicious_token:
        proposal = _display_name_from_context_or_sample(cand, display_name_override, raw)
        return {
            "ok": False,
            "skip_reason": "suspicious_token_requires_confirm",
            "detail": "suspicious_token_requires_confirm — set confirm_for_suspicious_distributor_token=true",
            "suspicious_token": True,
            "proposed_display_name": proposal[:256] if proposal else None,
        }

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        return {
            "ok": False,
            "skip_reason": "missing_line_ids",
            "detail": "candidate.context.line_ids missing or empty",
        }
    ok_scope, scope_detail = _preview_line_scope(db, cand, line_ids)
    if not ok_scope:
        return {"ok": False, "skip_reason": "line_scope", "detail": scope_detail or "Line scope invalid"}

    code = (distributor_code_override or "").strip()[:32]
    if code and db.scalar(select(DimDistributor.id).where(DimDistributor.code == code)) is not None:
        return {"ok": False, "skip_reason": "distributor_code_exists", "detail": "distributor_code already exists"}

    proposal = _display_name_from_context_or_sample(cand, display_name_override, raw) or code or "(auto TMP-DIST)"
    existing = find_existing_provisional_distributor_by_canonical_name(db, proposal)
    code_preview = code or "(auto-generated TMP-DIST-…)"
    return {
        "ok": True,
        "detail": "Would create dim_distributor (or reuse provisional) and DistributorSourceTokenAlias",
        "proposed_display_name": proposal[:256],
        "distributor_code_preview": code_preview,
        "alias_raw_preview": raw[:160],
        "normalized_token_preview": nt[:160],
        "suspicious_token": suspicious,
        "reused_provisional_distributor": existing is not None,
        "existing_distributor_id": int(existing.id) if existing is not None else None,
        "lines_affected": len(line_ids),
    }


def shipment_bulk_totals_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate row/units/value counts from bulk preview or apply result rows."""
    ok_idx = [r for r in rows if r.get("ok")]
    rows_affected = sum(int(r.get("row_count") or 0) for r in ok_idx)
    units = sum(float(r.get("total_units") or 0) for r in ok_idx)
    value = sum(float(r.get("total_reported_value") or 0) for r in ok_idx)
    return {
        "ok_count": len(ok_idx),
        "not_ok_count": len(rows) - len(ok_idx),
        "staging_rows_affected": rows_affected,
        "total_units_affected": units,
        "total_reported_value_affected": value,
    }
