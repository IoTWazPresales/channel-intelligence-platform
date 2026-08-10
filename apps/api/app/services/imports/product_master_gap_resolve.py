"""BACKLOG-072 — catalogue-gap scan / preview / confirm-apply (no schema).

Tier matching: ``resolve_product_id_single_match`` + steward/exact alias only (no fuzzy).
Repoint: shipment evidence (+ fact resolution FKs) + DSI staging + CPOR claims + CST staging.
DSI facts: FLAG only — ``source_key`` includes product_id (STOP until designed).
Observations are append-only — never mutated here.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.cpor import CporClaimEvidenceLine
from app.models.import_distributor_si import ImportDistributorSiStagingLine, ImportEntityMappingCandidate
from app.models.mapping import ProductAlias
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _product_token_key
from app.services.imports.product_resolution_index_cache import (
    get_product_resolution_index,
    invalidate_product_resolution_index_cache,
)
from app.services.imports.product_resolution_standard import resolve_product_id_single_match
from app.utils.json_safe import to_jsonable

_SHIPMENT_UNRESOLVED = frozenset({"no_match", "inactive_only", "ambiguous", "no_identifier"})
ProgressCb = Callable[[dict[str, Any]], None] | None


def _norm_token(raw: str | None) -> str:
    """Worklist-aligned display/compare key (upper, collapsed whitespace)."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().upper())


def match_token_to_product(
    session: Session,
    token: str,
) -> dict[str, Any]:
    """Exact-tier match only. Never auto-creates dim_product."""
    display = _norm_token(token)
    key = _product_token_key(token)
    if not key:
        return {"token": display or (token or ""), "matched": False, "reason": "blank_token"}

    idx = get_product_resolution_index(session)

    steward = idx.steward_alias_by_key.get(key)
    if steward is not None:
        return {
            "token": display,
            "matched": True,
            "product_id": int(steward),
            "match_tier": "steward_alias",
        }

    alias_ids = idx.alias_value_to_ids.get(key) or ()
    if len(alias_ids) == 1:
        return {
            "token": display,
            "matched": True,
            "product_id": int(alias_ids[0]),
            "match_tier": "alias",
        }
    if len(alias_ids) > 1:
        return {"token": display, "matched": False, "reason": "ambiguous_alias"}

    pid = resolve_product_id_single_match(idx, token)
    if pid is None:
        return {"token": display, "matched": False, "reason": "no_tier_match"}
    return {
        "token": display,
        "matched": True,
        "product_id": int(pid),
        "match_tier": "pm_tier",
    }


def preview_gap_resolve(
    session: Session,
    tokens: list[str],
) -> dict[str, Any]:
    """Read-only: match + affected counts by source. No writes."""
    items: list[dict[str, Any]] = []
    for raw in tokens:
        m = match_token_to_product(session, raw)
        tok = m.get("token") or _norm_token(raw)
        ship_n, ship_jobs = _count_shipment(session, tok)
        dsi_n, dsi_jobs = _count_dsi_staging(session, tok)
        claim_n, claim_jobs = _count_cpor_claims(session, tok)
        cst_n, cst_jobs = _count_cst_staging(session, tok)
        flags: list[str] = []
        flag_detail: str | None = None
        if dsi_n > 0:
            flags.append("dsi_facts_repoint_deferred")
            flag_detail = (
                "DSI fact source_key includes product_id — staging-only repoint this unit; "
                "leftovers remain FLAG not BLOCK"
            )
        items.append(
            {
                **m,
                "counts": {
                    "shipment": ship_n,
                    "dsi_staging": dsi_n,
                    "cpor_claim": claim_n,
                    "cst_staging": cst_n,
                    "dsi_facts": 0,
                },
                "flags": flags,
                "flag_detail": flag_detail,
                "affected_job_ids": sorted(ship_jobs | dsi_jobs | claim_jobs | cst_jobs),
            }
        )
    return {
        "items": items,
        "matched_count": sum(1 for i in items if i.get("matched")),
        "unmatched_count": sum(1 for i in items if not i.get("matched")),
        "data_unavailable": False,
    }


def _count_shipment(session: Session, tok: str) -> tuple[int, set[int]]:
    jobs: set[int] = set()
    n = 0
    lines = session.scalars(
        select(ShipmentEvidenceLine).where(
            ShipmentEvidenceLine.product_id.is_(None),
            ShipmentEvidenceLine.product_resolution_status.in_(tuple(_SHIPMENT_UNRESOLVED)),
        )
    ).all()
    for line in lines:
        if _line_token_match(line, tok):
            n += 1
            if line.import_job_id is not None:
                jobs.add(int(line.import_job_id))
    return n, jobs


def _line_token_match(line: ShipmentEvidenceLine, tok: str) -> bool:
    for field in (
        line.product_resolution_token,
        line.item_code,
        line.ean_code,
        line.upc_code,
        line.sales_model_name,
        line.customer_item,
        line.mpor_item_no,
    ):
        if _norm_token(field) == tok:
            return True
    return False


def _count_dsi_staging(session: Session, tok: str) -> tuple[int, set[int]]:
    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    jobs: set[int] = set()
    n = 0
    for c in cands:
        if _norm_token(getattr(c, "normalized_key", None)) == tok:
            n += 1
            if c.import_job_id is not None:
                jobs.add(int(c.import_job_id))
    return n, jobs


def _count_cpor_claims(session: Session, tok: str) -> tuple[int, set[int]]:
    rows = session.scalars(
        select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.product_id.is_(None))
    ).all()
    jobs: set[int] = set()
    n = 0
    for r in rows:
        if _norm_token(r.source_model_token) == tok:
            n += 1
            if r.import_job_id is not None:
                jobs.add(int(r.import_job_id))
    return n, jobs


def _count_cst_staging(session: Session, tok: str) -> tuple[int, set[int]]:
    from app.services.imports.cst_mapping_candidates import CST_PRODUCT_ENTITY

    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY,
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    jobs: set[int] = set()
    n = 0
    for c in cands:
        if _norm_token(getattr(c, "normalized_key", None)) == tok:
            n += int(c.row_count or 1)
            if c.import_job_id is not None:
                jobs.add(int(c.import_job_id))
    return n, jobs


def apply_gap_resolve(
    session: Session,
    *,
    tokens: list[str],
    confirm: bool,
    write_alias: bool = True,
    actor: str | None = None,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Steward-confirmed set-based repoint. Idempotent for already-resolved rows."""
    if not confirm:
        return {"ok": False, "error": "confirm_required", "applied": False}

    preview = preview_gap_resolve(session, tokens)
    applied: list[dict[str, Any]] = []
    total = len(preview["items"])

    for i, item in enumerate(preview["items"]):
        if on_progress:
            on_progress({"phase": "apply", "index": i, "total": total, "token": item.get("token")})
        if not item.get("matched"):
            applied.append({**item, "action": "skipped_unmatched"})
            continue
        pid = int(item["product_id"])
        tok = str(item["token"])
        ship_u = _repoint_shipment(session, tok, pid)
        dsi_u = _repoint_dsi_staging(session, tok, pid)
        claim_u = _repoint_cpor_claims(session, tok, pid)
        cst_u = _repoint_cst_staging(session, tok, pid)
        alias_written = False
        alias_skipped_conflict = False
        if write_alias and (ship_u or dsi_u or claim_u or cst_u):
            alias_written, alias_skipped_conflict = _ensure_product_alias(session, tok, pid)
        applied.append(
            {
                "token": tok,
                "product_id": pid,
                "match_tier": item.get("match_tier"),
                "action": "repointed",
                "updated": {
                    "shipment_lines": ship_u,
                    "dsi_staging_candidates": dsi_u,
                    "cpor_claim_lines": claim_u,
                    "cst_staging_candidates": cst_u,
                    "dsi_facts": 0,
                },
                "flags": item.get("flags") or [],
                "flag_detail": item.get("flag_detail"),
                "alias_written": alias_written,
                "alias_skipped_conflict": alias_skipped_conflict,
                "actor": actor,
            }
        )

    session.flush()
    invalidate_product_resolution_index_cache()
    return {
        "ok": True,
        "applied": True,
        "items": applied,
        "summary": {
            "tokens": total,
            "repointed": sum(1 for a in applied if a.get("action") == "repointed"),
            "skipped": sum(1 for a in applied if a.get("action") != "repointed"),
        },
    }


def _repoint_shipment(session: Session, tok: str, product_id: int) -> int:
    lines = session.scalars(
        select(ShipmentEvidenceLine).where(
            ShipmentEvidenceLine.product_id.is_(None),
            ShipmentEvidenceLine.product_resolution_status.in_(tuple(_SHIPMENT_UNRESOLVED)),
        )
    ).all()
    ids: list[int] = []
    for line in lines:
        if _line_token_match(line, tok):
            ids.append(int(line.id))
    if not ids:
        return 0
    session.execute(
        update(ShipmentEvidenceLine)
        .where(ShipmentEvidenceLine.id.in_(ids))
        .values(
            product_id=product_id,
            product_resolution_status="resolved",
            product_resolution_detail="catalogue_gap_bulk_resolve",
        )
    )
    # fact_inbound_shipment: resolution FKs only where still null (latest-job-wins grain unchanged)
    try:
        from app.models.facts import FactInboundShipment

        session.execute(
            update(FactInboundShipment)
            .where(
                FactInboundShipment.product_id.is_(None),
                FactInboundShipment.shipment_evidence_line_id.in_(ids),
            )
            .values(
                product_id=product_id,
                product_resolution_status="resolved",
                product_resolution_detail="catalogue_gap_bulk_resolve",
            )
        )
    except Exception:
        pass
    return len(ids)


def _repoint_dsi_staging(session: Session, tok: str, product_id: int) -> int:
    """Mark candidates resolved + refresh staging resolved_product_id. Does NOT rewrite DSI facts."""
    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    n = 0
    job_ids: set[int] = set()
    for c in cands:
        if _norm_token(getattr(c, "normalized_key", None)) != tok:
            continue
        c.status = "resolved"
        c.suggested_entity_id = int(product_id)
        c.match_reason = "catalogue_gap_bulk_resolve"
        ctx = dict(c.context) if isinstance(c.context, dict) else {}
        ctx["catalogue_gap_bulk_resolve"] = True
        c.context = to_jsonable(ctx)
        session.add(c)
        n += 1
        if c.import_job_id is not None:
            job_ids.add(int(c.import_job_id))
    if job_ids:
        staging = session.scalars(
            select(ImportDistributorSiStagingLine).where(
                ImportDistributorSiStagingLine.import_job_id.in_(tuple(job_ids)),
                ImportDistributorSiStagingLine.resolved_product_id.is_(None),
            )
        ).all()
        for row in staging:
            if _norm_token(row.raw_product_token) == tok:
                row.resolved_product_id = int(product_id)
                session.add(row)
    return n


def _repoint_cpor_claims(session: Session, tok: str, product_id: int) -> int:
    rows = session.scalars(
        select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.product_id.is_(None))
    ).all()
    n = 0
    for r in rows:
        if _norm_token(r.source_model_token) != tok:
            continue
        r.product_id = int(product_id)
        session.add(r)
        n += 1
    return n


def _repoint_cst_staging(session: Session, tok: str, product_id: int) -> int:
    """Resolve CST mapping candidates + patch sell-through staging lines. FLAG≠BLOCK."""
    from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
    from app.services.imports.cst_mapping_candidates import CST_PRODUCT_ENTITY

    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY,
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    n = 0
    job_ids: set[int] = set()
    for c in cands:
        if _norm_token(getattr(c, "normalized_key", None)) != tok:
            continue
        c.status = "resolved"
        c.suggested_entity_id = int(product_id)
        c.match_reason = "catalogue_gap_bulk_resolve"
        ctx = dict(c.context) if isinstance(c.context, dict) else {}
        ctx["catalogue_gap_bulk_resolve"] = True
        ctx["steward_resolved_entity_id"] = int(product_id)
        c.context = to_jsonable(ctx)
        session.add(c)
        n += 1
        if c.import_job_id is not None:
            job_ids.add(int(c.import_job_id))
    if job_ids:
        staging = session.scalars(
            select(ImportCustomerSellthroughStagingLine).where(
                ImportCustomerSellthroughStagingLine.import_job_id.in_(tuple(job_ids)),
                ImportCustomerSellthroughStagingLine.resolved_product_id.is_(None),
            )
        ).all()
        for row in staging:
            if _norm_token(row.raw_product_token) == tok:
                row.resolved_product_id = int(product_id)
                row.resolution_status = "resolved"
                session.add(row)
    return n


def _ensure_product_alias(session: Session, tok: str, product_id: int) -> tuple[bool, bool]:
    """Return (written, skipped_conflict). Never auto-creates dim_product."""
    alias_val = tok[:256]
    key = _product_token_key(alias_val)
    existing = session.scalar(
        select(ProductAlias).where(func.lower(ProductAlias.alias_value) == key)
    )
    if existing is not None:
        if int(existing.product_id) == int(product_id):
            return False, False
        return False, True
    session.add(
        ProductAlias(
            product_id=int(product_id),
            alias_value=alias_val,
            alias_kind="source_import_token",
            confidence="steward_approved",
        )
    )
    return True, False


def scan_open_gaps_for_matches(session: Session, *, limit: int = 500) -> dict[str, Any]:
    """On-demand / post-PM: worklist unresolved tokens that now match PM."""
    tokens: set[str] = set()
    for line in session.scalars(
        select(ShipmentEvidenceLine).where(
            ShipmentEvidenceLine.product_id.is_(None),
            ShipmentEvidenceLine.product_resolution_status.in_(tuple(_SHIPMENT_UNRESOLVED)),
        )
    ).all():
        for field in (
            line.product_resolution_token,
            line.item_code,
            line.ean_code,
            line.upc_code,
            line.sales_model_name,
            line.customer_item,
            line.mpor_item_no,
        ):
            t = _norm_token(field)
            if t:
                tokens.add(t)
                break
    for c in session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status == "needs_review",
        )
    ).all():
        t = _norm_token(getattr(c, "normalized_key", None))
        if t:
            tokens.add(t)
    from app.services.imports.cst_mapping_candidates import CST_PRODUCT_ENTITY

    for c in session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY,
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all():
        t = _norm_token(getattr(c, "normalized_key", None))
        if t:
            tokens.add(t)
    for r in session.scalars(
        select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.product_id.is_(None))
    ).all():
        t = _norm_token(r.source_model_token)
        if t:
            tokens.add(t)

    token_list = sorted(tokens)[:limit]
    preview = preview_gap_resolve(session, token_list)
    matched = [i for i in preview["items"] if i.get("matched")]
    return {
        "scanned_tokens": len(token_list),
        "matched": matched,
        "matched_count": len(matched),
        "truncated": len(tokens) > limit,
    }
