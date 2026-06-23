"""Shipment resolution-plan apply — effective plan once, then canonical bulk writers."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    enrich_shipment_customer_token_candidates,
    enrich_shipment_distributor_candidates,
)
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    _apply_create_provisional_shipment_customer_without_commit,
    _apply_create_provisional_shipment_distributor_without_commit,
    _apply_map_shipment_customer_without_commit,
    _apply_map_shipment_distributor_without_commit,
    _display_name_from_context_or_sample,
    _first_sample_raw,
    execute_bulk_map_shipment_customers,
)
from app.services.imports.shipment_resolution_plan import build_shipment_resolution_plan_effective_sync

logger = logging.getLogger(__name__)


def _empty_combined(job_id: int) -> dict[str, Any]:
    return {
        "import_job_id": job_id,
        "applied": 0,
        "failed": 0,
        "skipped_hold": 0,
        "skipped_not_ready": 0,
        "results": [],
    }


def run_shipment_resolution_plan_apply_orchestrator(
    session: Session,
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    overrides: list[dict[str, Any]] = [
        dict(o) for o in (payload.get("overrides") or []) if isinstance(o, dict)
    ]
    total = len(candidate_ids)
    combined = _empty_combined(job_id)
    processed = 0

    def _advance(count: int = 1) -> None:
        nonlocal processed
        processed = min(total, processed + count)
        if on_progress is not None:
            on_progress(processed, total)

    plan = build_shipment_resolution_plan_effective_sync(
        session,
        job_id,
        candidate_ids=candidate_ids,
        overrides=overrides,
    )
    rows_by_cid = {int(r["candidate_id"]): r for r in plan.get("rows") or [] if "candidate_id" in r}

    map_customer_groups: dict[int, list[int]] = defaultdict(list)
    map_distributor_groups: dict[int, list[int]] = defaultdict(list)
    provisional_customer_cids: list[int] = []
    provisional_distributor_cids: list[int] = []

    for cid in candidate_ids:
        row = rows_by_cid.get(int(cid))
        if row is None:
            combined["failed"] += 1
            combined["results"].append(
                {"candidate_id": int(cid), "status": "failed", "detail": "Candidate not found in effective plan"}
            )
            _advance()
            continue
        if row.get("hold_for_manual_review"):
            combined["skipped_hold"] += 1
            combined["results"].append(
                {"candidate_id": int(cid), "status": "skipped_hold", "detail": "hold_for_manual_review"}
            )
            _advance()
            continue
        if not row.get("ready"):
            combined["skipped_not_ready"] += 1
            blockers = row.get("resolution_blockers")
            detail = ",".join(blockers) if isinstance(blockers, list) and blockers else "not_ready"
            combined["results"].append(
                {"candidate_id": int(cid), "status": "skipped_not_ready", "detail": detail}
            )
            _advance()
            continue

        action = str(row.get("suggested_action") or "")
        tid = row.get("suggested_target_id")
        if action == "map_customer" and tid is not None:
            map_customer_groups[int(tid)].append(int(cid))
        elif action == "map_distributor" and tid is not None:
            map_distributor_groups[int(tid)].append(int(cid))
        elif action == "create_provisional_customer":
            provisional_customer_cids.append(int(cid))
        elif action == "create_provisional_distributor":
            provisional_distributor_cids.append(int(cid))
        else:
            combined["failed"] += 1
            combined["results"].append(
                {"candidate_id": int(cid), "status": "failed", "detail": f"unsupported_action:{action or 'empty'}"}
            )
            _advance()

    for customer_id, cids in map_customer_groups.items():
        try:
            bulk_out = execute_bulk_map_shipment_customers(
                session,
                customer_id=int(customer_id),
                candidate_ids=cids,
            )
            for r in bulk_out.get("results") or []:
                cid = int(r["candidate_id"])
                if r.get("ok"):
                    combined["applied"] += 1
                    combined["results"].append({"candidate_id": cid, "status": "applied", "result": r.get("result")})
                else:
                    combined["failed"] += 1
                    combined["results"].append(
                        {"candidate_id": cid, "status": "failed", "detail": r.get("detail") or "bulk map failed"}
                    )
                _advance()
        except Exception as exc:  # noqa: BLE001
            logger.exception("shipment plan apply bulk map customer failed customer_id=%s", customer_id)
            for cid in cids:
                combined["failed"] += 1
                combined["results"].append({"candidate_id": cid, "status": "failed", "detail": str(exc)[:400]})
                _advance()

    for distributor_id, cids in map_distributor_groups.items():
        for cid in cids:
            cand = session.get(ImportEntityMappingCandidate, cid)
            if cand is None:
                combined["failed"] += 1
                combined["results"].append({"candidate_id": cid, "status": "failed", "detail": "candidate_not_found"})
                _advance()
                continue
            try:
                _apply_map_shipment_distributor_without_commit(
                    session, cand, distributor_id=int(distributor_id), raw_token=None
                )
                combined["applied"] += 1
                combined["results"].append({"candidate_id": cid, "status": "applied"})
            except ShipmentStewardOpError as exc:
                combined["failed"] += 1
                combined["results"].append({"candidate_id": cid, "status": "failed", "detail": str(exc.detail)})
            _advance()

    for cid in provisional_customer_cids:
        cand = session.get(ImportEntityMappingCandidate, cid)
        if cand is None:
            combined["failed"] += 1
            combined["results"].append({"candidate_id": cid, "status": "failed", "detail": "candidate_not_found"})
            _advance()
            continue
        try:
            raw = _first_sample_raw(cand)
            dn = _display_name_from_context_or_sample(cand, None, raw)
            _apply_create_provisional_shipment_customer_without_commit(
                session,
                cand,
                display_name=dn.strip() or None,
                region_id=None,
                channel_id=None,
                preferred_distributor_id=None,
                partner_tier="unmanaged",
                notes_summary=None,
                bypass_partner_text_guards=True,
            )
            combined["applied"] += 1
            combined["results"].append({"candidate_id": cid, "status": "applied"})
        except ShipmentStewardOpError as exc:
            combined["failed"] += 1
            combined["results"].append({"candidate_id": cid, "status": "failed", "detail": str(exc.detail)})
        _advance()

    for cid in provisional_distributor_cids:
        cand = session.get(ImportEntityMappingCandidate, cid)
        if cand is None:
            combined["failed"] += 1
            combined["results"].append({"candidate_id": cid, "status": "failed", "detail": "candidate_not_found"})
            _advance()
            continue
        try:
            raw = _first_sample_raw(cand)
            dn = _display_name_from_context_or_sample(cand, None, raw)
            _apply_create_provisional_shipment_distributor_without_commit(
                session,
                cand,
                display_name=dn.strip() or None,
                distributor_code=None,
                confirm_for_suspicious_token=False,
                bypass_suspicious_token_gate=True,
            )
            combined["applied"] += 1
            combined["results"].append({"candidate_id": cid, "status": "applied"})
        except ShipmentStewardOpError as exc:
            combined["failed"] += 1
            combined["results"].append({"candidate_id": cid, "status": "failed", "detail": str(exc.detail)})
        _advance()

    if combined["applied"] > 0:
        sid: int | None = None
        any_customer = False
        any_distributor = False
        for r in reversed(combined["results"]):
            if r.get("status") != "applied":
                continue
            c = session.get(ImportEntityMappingCandidate, int(r["candidate_id"]))
            if c is None:
                continue
            if sid is None and c.source_definition_id is not None:
                sid = int(c.source_definition_id)
            if c.entity_type == SHIPMENT_CUSTOMER_ENTITY:
                any_customer = True
            elif c.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY:
                any_distributor = True
        if any_customer:
            enrich_shipment_customer_token_candidates(session, import_job_id=job_id, source_definition_id=sid)
            session.commit()
        if any_distributor:
            enrich_shipment_distributor_candidates(session, import_job_id=job_id, source_definition_id=sid)
            session.commit()
    else:
        session.commit()

    combined["processed"] = processed
    combined["partial_success"] = bool(processed < total and combined["applied"] > 0)
    return combined


def run_shipment_resolution_plan_apply_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as session:
        return run_shipment_resolution_plan_apply_orchestrator(
            session, job_id, payload, on_progress=on_progress
        )
