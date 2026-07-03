"""Steward-driven re-derivation for existing 1H lineup cases (split + uniform half allocation)."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.models.ingestion import ImportJob
from app.services.commercial_planner.lineup_bulk_backfill_apply import persist_preview_session
from app.services.commercial_planner.lineup_bulk_period_inference import (
    infer_period_from_filename,
    resolve_layered_period,
)
from app.services.commercial_planner.lineup_half_year_quantity import (
    HALF_YEAR_ALLOCATION_FLAG,
    PERIOD_SCOPE_1H_SPLIT_FLAG,
    apply_half_year_allocation_to_line_fields,
    half_year_allocation_summary,
    sum_line_quantities,
)
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    display_period_label_from_period_start,
    supersession_group_key_from_period_start,
)
from app.utils.json_safe import to_jsonable

REDERIVATION_PREVIEW_KEY = "lineup_1h_rederivation_preview"


def _norm_customer_token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def case_has_1h_signal(case: CommercialLineupCase) -> bool:
    sig = infer_period_from_filename(case.file_name)
    if sig is not None and sig.is_half:
        return True
    assignments, _ = resolve_layered_period(filename=case.file_name)
    return any(PERIOD_SCOPE_1H_SPLIT_FLAG in (a.flags or []) for a in assignments)


def _line_already_allocated(line: CommercialLineupLine) -> bool:
    codes = list(line.diagnostic_codes or [])
    return HALF_YEAR_ALLOCATION_FLAG in codes


def _majority_customer_id(lines: list[CommercialLineupLine]) -> int | None:
    counts: dict[int, int] = {}
    for ln in lines:
        if ln.customer_id is not None:
            cid = int(ln.customer_id)
            counts[cid] = counts.get(cid, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _planned_for_customer(lines: list[CommercialLineupLine], customer_id: int | None) -> float:
    total = 0.0
    for ln in lines:
        if customer_id is not None and ln.customer_id != customer_id:
            continue
        if ln.quantity_units is not None:
            total += float(ln.quantity_units)
    return total


def _find_existing_q2_collisions(
    db: Session,
    *,
    q2_period_start: date,
    customer_id: int | None,
    customer_token: str | None,
    business_unit: str | None,
    exclude_case_id: int,
) -> list[CommercialLineupCase]:
    bu_key = (business_unit or "unknown").strip().upper()
    candidates = list(
        db.scalars(
            select(CommercialLineupCase).where(
                *active_lineup_case_filters(),
                CommercialLineupCase.id != int(exclude_case_id),
                CommercialLineupCase.inferred_period_start == q2_period_start,
            )
        ).all()
    )
    out: list[CommercialLineupCase] = []
    for c in candidates:
        c_bu = ((c.business_unit or c.product_line) or "unknown").strip().upper()
        if c_bu == bu_key:
            out.append(c)
    return out


def _build_rederivation_proposal(db: Session, case: CommercialLineupCase) -> dict[str, Any] | None:
    if not case_has_1h_signal(case):
        return None
    lines = list(db.scalars(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case.id)).all())
    if not lines:
        return None

    year = case.inferred_period_start.year if case.inferred_period_start else None
    if year is None:
        assignments, _ = resolve_layered_period(filename=case.file_name)
        for a in assignments:
            if a.period_start is not None:
                year = a.period_start.year
                break
    if year is None:
        return None

    q2_start = date(year, 4, 1)
    source_total = sum_line_quantities(lines)
    alloc = half_year_allocation_summary(source_total)
    cust_id = _majority_customer_id(lines)
    cust_token = next((ln.customer_token for ln in lines if ln.customer_token), None)
    bu = case.business_unit or case.product_line

    po_count = db.scalar(
        select(func.count()).select_from(CommercialLineupCasePo).where(CommercialLineupCasePo.case_id == case.id)
    )

    q2_collisions = _find_existing_q2_collisions(
        db,
        q2_period_start=q2_start,
        customer_id=cust_id,
        customer_token=cust_token,
        business_unit=bu,
        exclude_case_id=int(case.id),
    )

    q2_proposal_key = f"rederivation:{case.id}:q2"
    sgk = f"{q2_start.isoformat()}|{bu or 'unknown'}|q2_rederivation"

    customer_planned_before = _planned_for_customer(lines, cust_id) if cust_id is not None else None
    customer_planned_after_q1 = None
    if customer_planned_before is not None and source_total:
        customer_planned_after_q1 = float(alloc["q1_allocated_units"]) * (customer_planned_before / source_total)

    makro_id = db.scalar(select(DimCustomer.id).where(func.lower(DimCustomer.name).like("%makro%")).limit(1))
    makro_planned_before = _planned_for_customer(lines, int(makro_id)) if makro_id else None
    makro_planned_after_q1 = None
    if makro_planned_before is not None:
        makro_planned_after_q1 = half_year_allocation_summary(makro_planned_before)["q1_allocated_units"]

    return {
        "proposal_key": f"rederivation:{case.id}",
        "source_case_id": int(case.id),
        "file_name": case.file_name,
        "period_label_before": case.period_label,
        "business_unit": bu,
        "flags": [PERIOD_SCOPE_1H_SPLIT_FLAG, HALF_YEAR_ALLOCATION_FLAG],
        "allocation_summary": alloc,
        "q1_adjustment": {
            "case_id": int(case.id),
            "planned_units_before": source_total,
            "planned_units_after": alloc["q1_allocated_units"],
            "line_count": len(lines),
            "po_link_count": int(po_count or 0),
            "customer_planned_before": customer_planned_before,
            "customer_planned_after_q1": customer_planned_after_q1,
            "makro_planned_before": makro_planned_before,
            "makro_planned_after_q1": makro_planned_after_q1,
            "already_allocated": all(_line_already_allocated(ln) for ln in lines),
        },
        "q2_twin_proposal": {
            "proposal_key": q2_proposal_key,
            "period_label": display_period_label_from_period_start(q2_start),
            "period_start": q2_start.isoformat(),
            "planned_units": alloc["q2_allocated_units"],
            "supersession_group_key": sgk,
            "line_count": len(lines),
        },
        "q2_existing_collisions": [
            {
                "case_id": int(c.id),
                "file_name": c.file_name,
                "period_label": c.period_label,
                "commercial_status": c.commercial_status,
                "member_key": f"existing:{c.id}",
            }
            for c in q2_collisions
        ],
        "status": "ready",
    }


def build_1h_rederivation_collisions(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collisions: list[dict[str, Any]] = []
    for prop in proposals:
        twin = prop.get("q2_twin_proposal") or {}
        sgk = str(twin.get("supersession_group_key") or "")
        if not sgk:
            continue
        members: list[dict[str, Any]] = []
        for ex in prop.get("q2_existing_collisions") or []:
            members.append(
                {
                    "member_key": ex.get("member_key"),
                    "case_id": ex.get("case_id"),
                    "filename": ex.get("file_name"),
                    "kind": "existing_case",
                }
            )
        members.append(
            {
                "member_key": twin.get("proposal_key"),
                "proposal_key": twin.get("proposal_key"),
                "filename": prop.get("file_name"),
                "kind": "proposed_q2_twin",
                "source_case_id": prop.get("source_case_id"),
            }
        )
        if len(members) < 2:
            continue
        existing = [m for m in members if m.get("kind") == "existing_case"]
        proposed = [m for m in members if m.get("kind") == "proposed_q2_twin"]
        winner_key = existing[-1]["member_key"] if existing else proposed[-1]["member_key"]
        collisions.append(
            {
                "supersession_group_key": sgk,
                "winner_member_key": winner_key,
                "members": members,
            }
        )
    return collisions


async def build_1h_rederivation_preview(db: AsyncSession) -> dict[str, Any]:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as sync_db:
        cases = list(
            sync_db.scalars(
                select(CommercialLineupCase).where(
                    *active_lineup_case_filters(),
                    CommercialLineupCase.file_name.isnot(None),
                )
            ).all()
        )
        proposals: list[dict[str, Any]] = []
        for case in cases:
            prop = _build_rederivation_proposal(sync_db, case)
            if prop:
                proposals.append(prop)

    preview_id = str(uuid.uuid4())
    collisions = build_1h_rederivation_collisions(proposals)
    return {
        "preview_id": preview_id,
        "rederivation_proposals": proposals,
        "supersession_collisions": collisions,
        "totals": {"eligible_cases": len(proposals), "collision_groups": len(collisions)},
    }


async def persist_rederivation_preview_session(db: AsyncSession, preview_payload: dict[str, Any]) -> ImportJob:
    wrapped = {REDERIVATION_PREVIEW_KEY: preview_payload, "preview_id": preview_payload.get("preview_id")}
    return await persist_preview_session(db, wrapped)


def _winner_member_keys(preview: dict[str, Any], confirmations: dict[str, str] | None) -> dict[str, str]:
    winners: dict[str, str] = {}
    confirmations = confirmations or {}
    inner = preview.get(REDERIVATION_PREVIEW_KEY) or preview
    for group in inner.get("supersession_collisions") or []:
        if not isinstance(group, dict):
            continue
        gkey = str(group.get("supersession_group_key") or "")
        if gkey in confirmations:
            winners[gkey] = str(confirmations[gkey])
        else:
            w = group.get("winner_member_key")
            if w:
                winners[gkey] = str(w)
    return winners


def _snapshot_line_sources(line: CommercialLineupLine) -> None:
    raw = dict(line.raw_row_payload or {})
    if line.quantity_units is not None:
        raw["half_year_source_quantity_units"] = float(line.quantity_units)
    if line.msrp_local is not None:
        raw["half_year_source_msrp_local"] = float(line.msrp_local)
    if line.promo_price_evidence_local is not None:
        raw["half_year_source_promo_price_evidence_local"] = float(line.promo_price_evidence_local)
    if line.dap_evidence_local is not None:
        raw["half_year_source_dap_evidence_local"] = float(line.dap_evidence_local)
    if line.calc_dap_cost_currency is not None:
        raw["half_year_source_calc_dap_cost_currency"] = float(line.calc_dap_cost_currency)
    if line.calc_profit_total is not None:
        raw["half_year_source_calc_profit_total"] = float(line.calc_profit_total)
    line.raw_row_payload = raw


def _update_line_allocation(line: CommercialLineupLine, *, half: str) -> None:
    raw = dict(line.raw_row_payload or {})
    allocated = apply_half_year_allocation_to_line_fields(
        quantity_units=float(raw.get("half_year_source_quantity_units", line.quantity_units))
        if (raw.get("half_year_source_quantity_units", line.quantity_units) is not None)
        else None,
        msrp_local=float(raw.get("half_year_source_msrp_local", line.msrp_local))
        if (raw.get("half_year_source_msrp_local", line.msrp_local) is not None)
        else None,
        promo_price_evidence_local=float(
            raw.get("half_year_source_promo_price_evidence_local", line.promo_price_evidence_local)
        )
        if (raw.get("half_year_source_promo_price_evidence_local", line.promo_price_evidence_local) is not None)
        else None,
        dap_evidence_local=float(raw.get("half_year_source_dap_evidence_local", line.dap_evidence_local))
        if (raw.get("half_year_source_dap_evidence_local", line.dap_evidence_local) is not None)
        else None,
        calc_dap_cost_currency=float(
            raw.get("half_year_source_calc_dap_cost_currency", line.calc_dap_cost_currency)
        )
        if (raw.get("half_year_source_calc_dap_cost_currency", line.calc_dap_cost_currency) is not None)
        else None,
        calc_profit_total=float(raw.get("half_year_source_calc_profit_total", line.calc_profit_total))
        if (raw.get("half_year_source_calc_profit_total", line.calc_profit_total) is not None)
        else None,
        half=half,
    )
    for field, value in allocated.items():
        setattr(line, field, value)
    diag = list(line.diagnostic_codes or [])
    if HALF_YEAR_ALLOCATION_FLAG not in diag:
        diag.append(HALF_YEAR_ALLOCATION_FLAG)
    line.diagnostic_codes = diag
    raw = dict(line.raw_row_payload or {})
    if line.quantity_units is not None:
        raw.setdefault("half_year_source_quantity_units", raw.get("quantity_units", line.quantity_units))
    line.raw_row_payload = raw


def _clone_line_for_case(line: CommercialLineupLine, *, case_id: int, half: str) -> CommercialLineupLine:
    raw = deepcopy(line.raw_row_payload) if isinstance(line.raw_row_payload, dict) else {}
    source_qty = raw.get("half_year_source_quantity_units", line.quantity_units)
    source_msrp = raw.get("half_year_source_msrp_local", line.msrp_local)
    source_promo = raw.get("half_year_source_promo_price_evidence_local", line.promo_price_evidence_local)
    source_dap = raw.get("half_year_source_dap_evidence_local", line.dap_evidence_local)
    source_calc_dap = raw.get("half_year_source_calc_dap_cost_currency", line.calc_dap_cost_currency)
    source_calc_profit = raw.get("half_year_source_calc_profit_total", line.calc_profit_total)

    allocated = apply_half_year_allocation_to_line_fields(
        quantity_units=float(source_qty) if source_qty is not None else None,
        msrp_local=float(source_msrp) if source_msrp is not None else None,
        promo_price_evidence_local=float(source_promo) if source_promo is not None else None,
        dap_evidence_local=float(source_dap) if source_dap is not None else None,
        calc_dap_cost_currency=float(source_calc_dap) if source_calc_dap is not None else None,
        calc_profit_total=float(source_calc_profit) if source_calc_profit is not None else None,
        half=half,
    )
    diag = list(line.diagnostic_codes or [])
    if HALF_YEAR_ALLOCATION_FLAG not in diag:
        diag.append(HALF_YEAR_ALLOCATION_FLAG)

    return CommercialLineupLine(
        case_id=case_id,
        source_row_number=line.source_row_number,
        product_id=line.product_id,
        customer_id=line.customer_id,
        distributor_id=line.distributor_id,
        customer_token=line.customer_token,
        sku_raw=line.sku_raw,
        part_number_raw=line.part_number_raw,
        model_raw=line.model_raw,
        base_unit_raw=line.base_unit_raw,
        quantity_units=allocated["quantity_units"],
        msrp_local=allocated["msrp_local"],
        promo_price_evidence_local=allocated["promo_price_evidence_local"],
        dap_evidence_local=allocated["dap_evidence_local"],
        rebate_pct_evidence=line.rebate_pct_evidence,
        distributor_margin_pct_evidence=line.distributor_margin_pct_evidence,
        vat_pct_evidence=line.vat_pct_evidence,
        diagnostic_codes=diag,
        raw_row_payload=raw,
        row_status=line.row_status,
        mapping_confidence=line.mapping_confidence,
        pricing_chain_json=line.pricing_chain_json,
        calc_dap_cost_currency=allocated["calc_dap_cost_currency"],
        calc_profit_total=allocated["calc_profit_total"],
    )


def apply_1h_rederivation_sync(
    session_job_id: int,
    *,
    approved_proposal_keys: list[str] | None = None,
    supersession_confirmations: dict[str, str] | None = None,
) -> dict[str, Any]:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        job = db.get(ImportJob, session_job_id)
        if job is None:
            raise ValueError(f"session job {session_job_id} not found")
        meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        outer = meta.get("bulk_lineup_backfill_preview")
        if isinstance(outer, dict) and REDERIVATION_PREVIEW_KEY in outer:
            preview = outer.get(REDERIVATION_PREVIEW_KEY)
        else:
            preview = meta.get(REDERIVATION_PREVIEW_KEY)
        if not isinstance(preview, dict):
            raise ValueError("missing rederivation preview payload")

        approved = set(approved_proposal_keys or [])
        if not approved_proposal_keys:
            approved = {str(p.get("proposal_key")) for p in preview.get("rederivation_proposals") or []}

        collision_winners = _winner_member_keys(preview, supersession_confirmations)
        results: list[dict[str, Any]] = []

        for prop in preview.get("rederivation_proposals") or []:
            pk = str(prop.get("proposal_key") or "")
            if pk not in approved:
                continue
            case_id = int(prop["source_case_id"])
            case = db.get(CommercialLineupCase, case_id)
            if case is None:
                results.append({"proposal_key": pk, "outcome": "error", "error": "case not found"})
                continue

            lines = list(db.scalars(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)).all())
            before_total = sum_line_quantities(lines)

            for ln in lines:
                _snapshot_line_sources(ln)
            for ln in lines:
                if not _line_already_allocated(ln):
                    _update_line_allocation(ln, half="q1")

            after_total = sum_line_quantities(lines)
            po_count = db.scalar(
                select(func.count()).select_from(CommercialLineupCasePo).where(CommercialLineupCasePo.case_id == case_id)
            )

            twin = prop.get("q2_twin_proposal") or {}
            sgk = str(twin.get("supersession_group_key") or "")
            winner_member = collision_winners.get(sgk, "")
            q2_case_id: int | None = None
            q2_outcome = "skipped_collision_existing_winner"

            if winner_member.startswith("existing:"):
                q2_case_id = int(winner_member.split(":", 1)[1])
            elif winner_member == str(twin.get("proposal_key")):
                q2_start = date.fromisoformat(str(twin["period_start"])[:10])
                q2_case = CommercialLineupCase(
                    commercial_plan_id=case.commercial_plan_id,
                    file_name=case.file_name,
                    period_label=twin.get("period_label"),
                    inferred_period_start=q2_start,
                    business_unit=case.business_unit,
                    product_line=case.product_line,
                    country_code=case.country_code,
                    currency_code=case.currency_code,
                    commercial_status="draft_imported",
                    import_intent=case.import_intent,
                    source_context=case.source_context,
                    notes=f"1H re-derivation Q2 twin from case #{case_id}",
                )
                db.add(q2_case)
                db.flush()
                for ln in lines:
                    db.add(_clone_line_for_case(ln, case_id=int(q2_case.id), half="q2"))
                q2_case_id = int(q2_case.id)
                q2_outcome = "created_q2_twin"

            db.commit()
            results.append(
                {
                    "proposal_key": pk,
                    "outcome": "applied",
                    "source_case_id": case_id,
                    "planned_before": before_total,
                    "planned_after_q1": after_total,
                    "po_link_count": int(po_count or 0),
                    "q2_case_id": q2_case_id,
                    "q2_outcome": q2_outcome,
                    "collision_winner": winner_member or None,
                }
            )

        meta = dict(meta)
        meta["lineup_1h_rederivation_apply"] = {"results": results}
        job.staged_metadata = to_jsonable(meta)
        db.commit()
        return {"session_import_job_id": session_job_id, "results": results}
