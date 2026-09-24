"""Settlement rollup + consolidation + CST divergence flags (CPOR U5)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine, CporClaimEvidenceLine
from app.models.dimensions import DimDistributor, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.cpor.line_window import (
    FLAG_WINDOW_WEEK_STRADDLE,
    effective_line_window,
    line_window_info,
)
from app.services.cpor.recompute import recompute_case_line
from app.services.cpor.settle_readiness import build_settle_readiness, count_open_assumptions_from_line_flags
from app.services.cpor.settlement_desk import (
    CORROBORATION_REASON,
    cip_amount_product_grain,
    classify_corroboration,
    customer_amount_line_grain,
    line_amount,
)
from app.services.cpor.waterfall import compute_ttl_result


def _has_window_override(raw: dict | None) -> bool:
    flags = (raw or {}).get("_cpor_flags") if isinstance(raw, dict) else None
    return isinstance(flags, dict) and bool(flags.get("include_out_of_window_override"))


def _claim_in_window(
    case: CporCase,
    sale_date: date,
    raw: dict | None,
    line: CporCaseLine | None = None,
) -> bool:
    """In-window test on the LINE window when a line is given (BACKLOG-137), else the case window.

    Claims are dated (daily); a claim either falls in a window or not, never pro-rated.
    """
    if _has_window_override(raw):
        return True
    if line is not None:
        ws, we = effective_line_window(line, case)
    else:
        ws, we = case.window_start, case.window_end
    if ws and sale_date < ws:
        return False
    if we and sale_date > we:
        return False
    return True


def rollup_result_qty_from_claims(
    session: Session,
    case_id: int,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Sum claim units in each LINE's window onto cpor_case_line.result_qty, then recompute.

    Each line counts claims for its product dated inside its own window (case window
    when the line has none). A line whose window cuts a Mon-Sun week mid-week is
    flagged ``window_week_straddle``; nothing is pro-rated. An out-of-window override
    claim is counted where the product has a single window; with several windows it
    cannot be placed and is reported (``override_claim_units_unplaced``), not guessed.
    """
    case = session.get(CporCase, case_id)
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    claims = list(
        session.scalars(
            select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.case_id == case_id)
        ).all()
    )
    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case_id)).all()
    )

    windows_by_pid: dict[int, set[tuple[date | None, date | None]]] = defaultdict(set)
    for line in lines:
        if line.product_id is not None:
            windows_by_pid[int(line.product_id)].add(effective_line_window(line, case))

    unresolved_units = Decimal("0")
    products_with_claims: set[int] = set()
    for c in claims:
        raw = c.raw_source_row if isinstance(c.raw_source_row, dict) else {}
        if not _claim_in_window(case, c.sale_date, raw):
            continue
        if c.product_id is None:
            unresolved_units += Decimal(str(c.units or 0))
            continue
        products_with_claims.add(int(c.product_id))

    updated = 0
    unplaced_override_units = Decimal("0")
    unplaced_seen: set[int] = set()
    window_flags: list[dict[str, Any]] = []
    for line in lines:
        pid = int(line.product_id) if line.product_id is not None else None
        if pid is None:
            continue
        info = line_window_info(line, case)
        if info["straddle_weeks"]:
            window_flags.append(
                {
                    "line_id": line.id,
                    "flag": FLAG_WINDOW_WEEK_STRADDLE,
                    "window_start": info["window_start"],
                    "window_end": info["window_end"],
                    "straddle_weeks": info["straddle_weeks"],
                }
            )
        if not claims:
            continue
        single_window = len(windows_by_pid.get(pid, set())) <= 1
        qty = Decimal("0")
        for c in claims:
            if c.product_id is None or int(c.product_id) != pid:
                continue
            raw = c.raw_source_row if isinstance(c.raw_source_row, dict) else {}
            if _claim_in_window(case, c.sale_date, None, line):
                qty += Decimal(str(c.units or 0))
            elif _has_window_override(raw):
                if single_window:
                    qty += Decimal(str(c.units or 0))
                elif id(c) not in unplaced_seen:
                    unplaced_seen.add(id(c))
                    unplaced_override_units += Decimal(str(c.units or 0))
        line.result_qty = float(qty)
        recompute_case_line(session, line, case=case, actor=actor, write_event=False)
        updated += 1

    session.flush()
    return {
        "case_id": case_id,
        "lines_updated": updated,
        "products_with_claims": len(products_with_claims),
        "unresolved_claim_units": float(unresolved_units),
        "claim_rows": len(claims),
        "window_week_straddle_lines": len(window_flags),
        "window_flags": window_flags,
        "override_claim_units_unplaced": float(unplaced_override_units),
    }


def _cst_and_claim_units(session: Session, case: CporCase) -> dict[str, Any]:
    """Product-grain CST vs in-window claims. CST is not allocated across duplicate case lines."""
    claims = list(
        session.scalars(
            select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.case_id == case.id)
        ).all()
    )
    claim_by_pid: dict[int, float] = defaultdict(float)
    for c in claims:
        raw = c.raw_source_row if isinstance(c.raw_source_row, dict) else {}
        if not _claim_in_window(case, c.sale_date, raw):
            continue
        if c.product_id is None:
            continue
        claim_by_pid[int(c.product_id)] += float(c.units or 0)

    if case.customer_id is None or case.window_start is None or case.window_end is None:
        return {
            "available": False,
            "reason": "missing_customer_or_window",
            "claim_by_pid": claim_by_pid,
            "cst_by_pid": {},
            "claims": claims,
        }

    period_floor = case.window_start - timedelta(days=31)
    cst_rows = session.execute(
        select(
            FactCustomerSellthrough.product_id,
            func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0),
        )
        .where(
            FactCustomerSellthrough.customer_id == int(case.customer_id),
            FactCustomerSellthrough.period_start_date <= case.window_end,
            FactCustomerSellthrough.period_start_date >= period_floor,
        )
        .group_by(FactCustomerSellthrough.product_id)
    ).all()
    cst_by_pid = {int(r[0]): float(r[1] or 0) for r in cst_rows if r[0] is not None}
    if not cst_by_pid and not claim_by_pid:
        return {
            "available": False,
            "reason": "no_cst_or_claim_rows",
            "claim_by_pid": claim_by_pid,
            "cst_by_pid": cst_by_pid,
            "claims": claims,
        }
    return {
        "available": True,
        "reason": None,
        "claim_by_pid": claim_by_pid,
        "cst_by_pid": cst_by_pid,
        "claims": claims,
    }


def build_settlement_consolidation(session: Session, case_id: int) -> dict[str, Any]:
    """Per-line estimate vs result + flags. FLAG != BLOCK.

    Desk fields (cip_qty / customer_qty) are read-only projections:
    cip_qty = CST units at product grain; customer_qty = result_qty from claim rollup.
    """
    case = session.get(CporCase, case_id)
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case_id)).all()
    )
    units = _cst_and_claim_units(session, case)
    claims = list(units["claims"])
    cst_flags = compute_cst_divergence_flags(session, case, units=units)

    unresolved_tokens: dict[str, float] = defaultdict(float)
    oow_rows = 0
    for c in claims:
        raw = c.raw_source_row if isinstance(c.raw_source_row, dict) else {}
        flags = raw.get("_cpor_flags") if isinstance(raw, dict) else {}
        if isinstance(flags, dict) and flags.get("out_of_window"):
            oow_rows += 1
        if c.product_id is None:
            tok = (c.source_model_token or "").strip() or "(blank)"
            unresolved_tokens[tok] += float(c.units or 0)

    product_ids = [int(line.product_id) for line in lines if line.product_id is not None]
    products: dict[int, DimProduct] = {}
    if product_ids:
        products = {
            int(p.id): p
            for p in session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids))).all()
        }
    dist_ids = [int(line.distributor_id) for line in lines if line.distributor_id is not None]
    distributors: dict[int, DimDistributor] = {}
    if dist_ids:
        distributors = {
            int(d.id): d
            for d in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(dist_ids))).all()
        }

    has_customer_report = len(claims) > 0
    cst_by_pid: dict[int, float] = units["cst_by_pid"]

    items: list[dict[str, Any]] = []
    for line in lines:
        estimate = float(line.estimate_qty or 0)
        result = float(line.result_qty) if line.result_qty is not None else None
        support_unit = float(line.support_unit) if line.support_unit is not None else None
        line_flags: list[str] = []
        if result is not None and estimate > 0 and result > estimate:
            line_flags.append("over_estimate")
        if result is not None and support_unit is not None and line.ttl_result is not None:
            expected = compute_ttl_result(support_unit, result)
            if expected is not None and abs(float(expected) - float(line.ttl_result)) > 0.02:
                line_flags.append("ttl_result_mismatch")

        pid = int(line.product_id) if line.product_id is not None else None
        if pid is not None and pid in cst_flags.get("by_product", {}):
            line_flags.append("cst_divergence")
        window = line_window_info(line, case)
        if window["straddle_weeks"]:
            line_flags.append(FLAG_WINDOW_WEEK_STRADDLE)

        product = products.get(pid) if pid is not None else None
        dist_id = int(line.distributor_id) if line.distributor_id is not None else None
        distributor = distributors.get(dist_id) if dist_id is not None else None
        cip_qty = cst_by_pid.get(pid) if pid is not None and pid in cst_by_pid else None
        customer_qty = result if has_customer_report else None
        corr = classify_corroboration(
            cip_qty=cip_qty,
            customer_qty=customer_qty,
            has_customer_report=has_customer_report,
        )

        items.append(
            {
                "line_id": line.id,
                "product_id": pid,
                "product_sku": product.sku if product is not None else None,
                "product_name": product.name if product is not None else None,
                "product_sales_model_name": (
                    product.sales_model_name if product is not None else None
                ),
                "distributor_id": dist_id,
                "distributor_name": distributor.name if distributor is not None else None,
                "window_start": window["window_start"],
                "window_end": window["window_end"],
                "window_week_aligned": window["week_aligned"],
                "straddle_weeks": window["straddle_weeks"],
                "estimate_qty": estimate,
                "result_qty": result,
                "cip_qty": cip_qty,
                "cip_qty_grain": "product",
                "customer_qty": customer_qty,
                "corroboration": corr,
                "corroboration_reason": CORROBORATION_REASON[corr],
                "include_in_credit": corr == "match",
                "support_unit": support_unit,
                "ttl_support": float(line.ttl_support) if line.ttl_support is not None else None,
                "ttl_result": float(line.ttl_result) if line.ttl_result is not None else None,
                "ttl_support_usd": float(line.ttl_support_usd)
                if line.ttl_support_usd is not None
                else None,
                "ttl_result_usd": float(line.ttl_result_usd)
                if line.ttl_result_usd is not None
                else None,
                "flags": line_flags,
            }
        )

    open_assumptions = 0
    for line in lines:
        line_flags: list[str] = []
        if line.distributor_id is None:
            line_flags.append("no_distributor")
        if line.cost_basis is None:
            line_flags.append("no_cost_basis")
        ev = line.cost_evidence_json or {}
        for f in ev.get("flags") or []:
            if f not in line_flags:
                line_flags.append(str(f))
        if count_open_assumptions_from_line_flags(line_flags) > 0:
            open_assumptions += 1

    cip_amount = cip_amount_product_grain(items)
    customer_amount = customer_amount_line_grain(items)
    matched = [row for row in items if row["corroboration"] == "match"]
    open_lines = [row for row in items if row["corroboration"] != "match"]
    credit_amount = 0.0
    for row in matched:
        amt = line_amount(row.get("customer_qty"), row.get("support_unit"))
        if amt is not None:
            credit_amount += amt
    agreed_amount = customer_amount if case.status == "settled" else None

    return {
        "case_id": case_id,
        "status": case.status,
        "window_start": case.window_start.isoformat() if case.window_start else None,
        "window_end": case.window_end.isoformat() if case.window_end else None,
        "claim_row_count": len(claims),
        "out_of_window_claim_rows": oow_rows,
        "unresolved_products": [
            {"token": k, "units": v} for k, v in sorted(unresolved_tokens.items())
        ],
        "cst_reconciliation": cst_flags,
        "settle_readiness": build_settle_readiness(
            case,
            claim_row_count=len(claims),
            open_assumption_count=open_assumptions,
        ),
        "lines": items,
        "can_settle": case.status == "ended",
        "desk": {
            "cip_amount": cip_amount,
            "customer_amount": customer_amount,
            "agreed_amount": agreed_amount,
            "paid_amount": None,
            "paid_in_schema": False,
            "hq_credit_amount": credit_amount if matched else None,
            "hq_credit_line_count": len(matched),
            "matched_count": len(matched),
            "open_count": len(open_lines),
            "cip_qty_grain": "product",
            "agreed_actor": case.decided_by if case.status == "settled" else None,
        },
    }


def compute_cst_divergence_flags(
    session: Session,
    case: CporCase,
    *,
    units: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare in-window claim units vs CST units for case customer. FLAG only."""
    packed = units or _cst_and_claim_units(session, case)
    if not packed.get("available"):
        return {
            "available": False,
            "reason": packed.get("reason") or "missing_customer_or_window",
            "by_product": {},
        }

    claim_by_pid: dict[int, float] = packed["claim_by_pid"]
    cst_by_pid: dict[int, float] = packed["cst_by_pid"]

    by_product: dict[int, dict[str, Any]] = {}
    for pid in set(claim_by_pid) | set(cst_by_pid):
        claimed = claim_by_pid.get(pid, 0.0)
        cst = cst_by_pid.get(pid, 0.0)
        if cst <= 0 and claimed <= 0:
            continue
        flagged = False
        if cst > 0:
            flagged = abs(claimed - cst) / cst > 0.10
        elif claimed > 0:
            flagged = True
        if flagged:
            by_product[pid] = {
                "claimed_units": claimed,
                "cst_units": cst,
                "flagged": True,
            }

    return {
        "available": True,
        "products_compared": len(set(claim_by_pid) | set(cst_by_pid)),
        "divergence_count": len(by_product),
        "by_product": by_product,
    }
