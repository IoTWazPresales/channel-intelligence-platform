"""Steward-driven re-derivation for existing 1H lineup cases (month-derived or uniform_half split)."""

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
from app.models.facts import FactInboundShipment
from app.models.ingestion import ImportJob
from app.services.commercial_planner.lineup_bulk_backfill_apply import persist_preview_session
from app.services.commercial_planner.lineup_bulk_period_inference import (
    infer_period_from_filename,
    resolve_layered_period,
)
from app.services.commercial_planner.lineup_fiscal_calendar import (
    get_lineup_fiscal_calendar_config,
    half_year_period_starts,
)
from app.services.commercial_planner.lineup_half_year_quantity import (
    HALF_YEAR_ALLOCATION_FLAG,
    PERIOD_SCOPE_1H_SPLIT_FLAG,
    sum_line_quantities,
)
from app.services.commercial_planner.lineup_month_derived_allocation import (
    MONTH_DERIVED_ALLOCATION_FLAG,
    QTY_MONTH_DISAGREEMENT_FLAG,
    case_allocation_summary_from_lines,
    compute_line_half_year_allocation,
    line_preview_dict,
    lines_indicate_1h_month_phasing_for_config,
)
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    display_period_label_from_period_start,
)
from app.utils.json_safe import to_jsonable

REDERIVATION_PREVIEW_KEY = "lineup_1h_rederivation_preview"

HALF_YEAR_SIGNAL_FILENAME = "filename_1h"
HALF_YEAR_SIGNAL_MONTH_COLUMNS = "stored_month_columns"
HALF_YEAR_SIGNAL_WORKBOOK_SIBLING = "workbook_sibling_1h"


def _norm_customer_token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def _workbook_file_key(file_name: str | None) -> str:
    return (file_name or "").strip().lower()


def _month_numbers_from_lines(lines: list[CommercialLineupLine]) -> set[int]:
    from app.services.commercial_planner.lineup_month_column_detector import detect_month_columns
    from app.services.commercial_planner.lineup_month_derived_allocation import _qty_from_uploaded

    months: set[int] = set()
    for ln in lines:
        raw = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
        uploaded = raw.get("uploaded")
        if isinstance(uploaded, dict):
            qty_cell = _qty_from_uploaded(uploaded)
            det = detect_month_columns(uploaded, column_order=list(uploaded.keys()), qty_cell_hint=qty_cell)
            months |= set(det.month_values.keys())
    return months


def lines_indicate_1h_month_phasing(lines: list[CommercialLineupLine]) -> bool:
    """True when stored parse evidence has month columns spanning both 1H fiscal quarters."""
    return lines_indicate_1h_month_phasing_for_config(lines, get_lineup_fiscal_calendar_config())


def case_has_1h_filename_signal(case: CommercialLineupCase) -> bool:
    sig = infer_period_from_filename(case.file_name)
    if sig is not None and sig.is_half:
        return True
    assignments, _ = resolve_layered_period(filename=case.file_name)
    return any(PERIOD_SCOPE_1H_SPLIT_FLAG in (a.flags or []) for a in assignments)


def case_has_1h_signal(case: CommercialLineupCase) -> bool:
    """Filename-only check — prefer ``resolve_half_year_signal`` when lines are available."""
    return case_has_1h_filename_signal(case)


def resolve_half_year_signal(
    case: CommercialLineupCase,
    lines: list[CommercialLineupLine],
    *,
    workbook_keys_with_direct_1h: set[str],
) -> tuple[bool, str | None]:
    """Detect 1H eligibility from filename, stored month columns, or sibling sheet in same workbook."""
    if case_has_1h_filename_signal(case):
        return True, HALF_YEAR_SIGNAL_FILENAME
    if lines_indicate_1h_month_phasing(lines):
        return True, HALF_YEAR_SIGNAL_MONTH_COLUMNS
    fk = _workbook_file_key(case.file_name)
    if fk and fk in workbook_keys_with_direct_1h:
        return True, HALF_YEAR_SIGNAL_WORKBOOK_SIBLING
    return False, None


def _line_allocation_tier(line: CommercialLineupLine) -> str | None:
    codes = list(line.diagnostic_codes or [])
    if MONTH_DERIVED_ALLOCATION_FLAG in codes:
        return "month_derived"
    if HALF_YEAR_ALLOCATION_FLAG in codes:
        return "uniform_half"
    return None


def _line_needs_month_rederivation(line: CommercialLineupLine) -> bool:
    """Pending when months qualify but line still carries uniform_half only."""
    from app.services.commercial_planner.lineup_month_column_detector import detect_month_columns
    from app.services.commercial_planner.lineup_month_derived_allocation import _qty_from_uploaded

    raw = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else {}
    uploaded = raw.get("uploaded")
    if not isinstance(uploaded, dict):
        return _line_allocation_tier(line) is None
    qty_cell = _qty_from_uploaded(uploaded)
    det = detect_month_columns(uploaded, column_order=list(uploaded.keys()), qty_cell_hint=qty_cell)
    if not det.has_qualifying_block:
        return _line_allocation_tier(line) is None
    return _line_allocation_tier(line) != "month_derived"


def _line_already_allocated(line: CommercialLineupLine) -> bool:
    return not _line_needs_month_rederivation(line)


def _shipment_q1_hint(db: Session, *, product_id: int | None, customer_id: int | None, q1_start: date, q2_start: date) -> float | None:
    if product_id is None:
        return None
    stmt = select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
        FactInboundShipment.product_id == int(product_id),
        FactInboundShipment.ship_confirm_date >= q1_start,
        FactInboundShipment.ship_confirm_date < q2_start,
    )
    if customer_id is not None:
        stmt = stmt.where(FactInboundShipment.customer_id == int(customer_id))
    val = db.scalar(stmt)
    return float(val) if val is not None else None


def _compute_case_line_allocations(
    db: Session,
    lines: list[CommercialLineupLine],
    *,
    q1_start: date,
    q2_start: date,
) -> tuple[list[Any], list[Any], list[dict[str, Any]]]:
    fiscal_config = get_lineup_fiscal_calendar_config()
    q1_allocs: list[Any] = []
    q2_allocs: list[Any] = []
    previews: list[dict[str, Any]] = []
    for ln in lines:
        ship_hint = _shipment_q1_hint(
            db, product_id=ln.product_id, customer_id=ln.customer_id, q1_start=q1_start, q2_start=q2_start
        )
        a1 = compute_line_half_year_allocation(ln, half="q1", fiscal_config=fiscal_config, shipment_q1_hint=ship_hint)
        a2 = compute_line_half_year_allocation(ln, half="q2", fiscal_config=fiscal_config, shipment_q1_hint=ship_hint)
        q1_allocs.append(a1)
        q2_allocs.append(a2)
        previews.append(line_preview_dict(a1, a2, ln))
    return q1_allocs, q2_allocs, previews


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


def _build_rederivation_proposal(
    db: Session,
    case: CommercialLineupCase,
    *,
    lines: list[CommercialLineupLine],
    signal_source: str,
) -> dict[str, Any] | None:
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

    fiscal_config = get_lineup_fiscal_calendar_config()
    q1_start, q2_start = half_year_period_starts(year, fiscal_config)
    before_total = sum_line_quantities(lines)
    q1_allocs, q2_allocs, line_previews = _compute_case_line_allocations(
        db, lines, q1_start=q1_start, q2_start=q2_start
    )
    alloc = case_allocation_summary_from_lines(q1_allocs, q2_allocs)
    source_total = float(alloc["source_total_units"])
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
        customer_planned_after_q1 = float(alloc["q1_allocated_units"]) * (customer_planned_before / before_total) if before_total else None

    makro_id = db.scalar(select(DimCustomer.id).where(func.lower(DimCustomer.name).like("%makro%")).limit(1))
    makro_planned_before = _planned_for_customer(lines, int(makro_id)) if makro_id else None
    makro_planned_after_q1 = None
    if makro_planned_before is not None and before_total:
        makro_planned_after_q1 = float(alloc["q1_allocated_units"]) * (makro_planned_before / before_total)

    disagreement_count = sum(1 for p in line_previews if p.get("qty_month_disagreement"))

    return {
        "proposal_key": f"rederivation:{case.id}",
        "source_case_id": int(case.id),
        "file_name": case.file_name,
        "period_label_before": case.period_label,
        "business_unit": bu,
        "half_year_signal_source": signal_source,
        "flags": [PERIOD_SCOPE_1H_SPLIT_FLAG, str(alloc.get("allocation_flag") or HALF_YEAR_ALLOCATION_FLAG)],
        "allocation_summary": alloc,
        "line_allocations": line_previews,
        "qty_month_disagreement_count": disagreement_count,
        "q1_adjustment": {
            "case_id": int(case.id),
            "planned_units_before": before_total,
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
                "business_unit": c.business_unit or c.product_line,
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
        bu = prop.get("business_unit")
        for ex in prop.get("q2_existing_collisions") or []:
            members.append(
                {
                    "member_key": ex.get("member_key"),
                    "case_id": ex.get("case_id"),
                    "filename": ex.get("file_name"),
                    "kind": "existing_case",
                    "business_unit": ex.get("business_unit") or bu,
                }
            )
        members.append(
            {
                "member_key": twin.get("proposal_key"),
                "proposal_key": twin.get("proposal_key"),
                "filename": prop.get("file_name"),
                "kind": "proposed_q2_twin",
                "source_case_id": prop.get("source_case_id"),
                "business_unit": bu,
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
        case_lines: list[tuple[CommercialLineupCase, list[CommercialLineupLine]]] = []
        for case in cases:
            lines = list(
                sync_db.scalars(
                    select(CommercialLineupLine).where(CommercialLineupLine.case_id == case.id)
                ).all()
            )
            case_lines.append((case, lines))

        workbook_keys_with_direct_1h: set[str] = set()
        for case, lines in case_lines:
            if case_has_1h_filename_signal(case) or lines_indicate_1h_month_phasing(lines):
                fk = _workbook_file_key(case.file_name)
                if fk:
                    workbook_keys_with_direct_1h.add(fk)

        proposals: list[dict[str, Any]] = []
        for case, lines in case_lines:
            eligible, signal_source = resolve_half_year_signal(
                case,
                lines,
                workbook_keys_with_direct_1h=workbook_keys_with_direct_1h,
            )
            if not eligible or signal_source is None:
                continue
            prop = _build_rederivation_proposal(
                sync_db, case, lines=lines, signal_source=signal_source
            )
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


def _snapshot_line_sources(line: CommercialLineupLine, *, allocation: Any | None = None) -> None:
    raw = dict(line.raw_row_payload or {})
    if allocation is not None and allocation.tier == "month_derived":
        raw["half_year_source_quantity_units"] = float(allocation.month_total_units)
    elif line.quantity_units is not None and "half_year_source_quantity_units" not in raw:
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


def _apply_allocation_to_line(line: CommercialLineupLine, allocation: Any) -> None:
    line.quantity_units = allocation.quantity_units
    for field, value in allocation.monetary.items():
        if hasattr(line, field):
            setattr(line, field, value)
    line.diagnostic_codes = list(allocation.diagnostic_codes)
    raw = dict(line.raw_row_payload or {})
    if allocation.tier == "month_derived":
        raw["half_year_source_quantity_units"] = float(allocation.month_total_units)
    if allocation.qty_month_disagreement:
        raw["lineup_qty_month_disagreement"] = allocation.qty_month_disagreement
    elif "lineup_qty_month_disagreement" in raw:
        del raw["lineup_qty_month_disagreement"]
    line.raw_row_payload = raw


def _update_line_allocation(
    line: CommercialLineupLine,
    *,
    half: str,
    db: Session,
    q1_start: date,
    q2_start: date,
) -> None:
    _snapshot_line_sources(line)
    ship_hint = _shipment_q1_hint(
        db, product_id=line.product_id, customer_id=line.customer_id, q1_start=q1_start, q2_start=q2_start
    )
    allocation = compute_line_half_year_allocation(
        line, half=half, shipment_q1_hint=ship_hint  # type: ignore[arg-type]
    )
    _apply_allocation_to_line(line, allocation)


def _clone_line_for_case(
    line: CommercialLineupLine,
    *,
    case_id: int,
    half: str,
    db: Session,
    q1_start: date,
    q2_start: date,
) -> CommercialLineupLine:
    ship_hint = _shipment_q1_hint(
        db, product_id=line.product_id, customer_id=line.customer_id, q1_start=q1_start, q2_start=q2_start
    )
    allocation = compute_line_half_year_allocation(
        line, half=half, shipment_q1_hint=ship_hint  # type: ignore[arg-type]
    )
    raw = deepcopy(line.raw_row_payload) if isinstance(line.raw_row_payload, dict) else {}
    if allocation.tier == "month_derived":
        raw["half_year_source_quantity_units"] = float(allocation.month_total_units)
    if allocation.qty_month_disagreement:
        raw["lineup_qty_month_disagreement"] = allocation.qty_month_disagreement

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
        quantity_units=allocation.quantity_units,
        msrp_local=allocation.monetary.get("msrp_local"),
        promo_price_evidence_local=allocation.monetary.get("promo_price_evidence_local"),
        dap_evidence_local=allocation.monetary.get("dap_evidence_local"),
        rebate_pct_evidence=line.rebate_pct_evidence,
        distributor_margin_pct_evidence=line.distributor_margin_pct_evidence,
        vat_pct_evidence=line.vat_pct_evidence,
        diagnostic_codes=list(allocation.diagnostic_codes),
        raw_row_payload=raw,
        row_status=line.row_status,
        mapping_confidence=line.mapping_confidence,
        pricing_chain_json=line.pricing_chain_json,
        calc_dap_cost_currency=allocation.monetary.get("calc_dap_cost_currency"),
        calc_profit_total=allocation.monetary.get("calc_profit_total"),
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

            year = case.inferred_period_start.year if case.inferred_period_start else None
            if year is None:
                assignments, _ = resolve_layered_period(filename=case.file_name)
                for a in assignments:
                    if a.period_start is not None:
                        year = a.period_start.year
                        break
            fiscal_config = get_lineup_fiscal_calendar_config()
            q1_start, q2_start = half_year_period_starts(year or date.today().year, fiscal_config)

            for ln in lines:
                _update_line_allocation(ln, half="q1", db=db, q1_start=q1_start, q2_start=q2_start)

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
                    db.add(_clone_line_for_case(ln, case_id=int(q2_case.id), half="q2", db=db, q1_start=q1_start, q2_start=q2_start))
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
