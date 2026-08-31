"""Settlement rollup + consolidation + CST divergence flags (CPOR U5)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine, CporClaimEvidenceLine
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.cpor.recompute import recompute_case_line
from app.services.cpor.settle_readiness import build_settle_readiness, count_open_assumptions_from_line_flags
from app.services.cpor.waterfall import compute_ttl_result


def _claim_in_window(case: CporCase, sale_date: date, raw: dict | None) -> bool:
    flags = (raw or {}).get("_cpor_flags") if isinstance(raw, dict) else None
    if isinstance(flags, dict) and flags.get("include_out_of_window_override"):
        return True
    if case.window_start and sale_date < case.window_start:
        return False
    if case.window_end and sale_date > case.window_end:
        return False
    return True


def rollup_result_qty_from_claims(
    session: Session,
    case_id: int,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Sum in-window claim units by product_id onto cpor_case_line.result_qty, then recompute."""
    case = session.get(CporCase, case_id)
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    claims = list(
        session.scalars(
            select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.case_id == case_id)
        ).all()
    )

    by_product: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    unresolved_units = Decimal("0")
    for c in claims:
        raw = c.raw_source_row if isinstance(c.raw_source_row, dict) else {}
        if not _claim_in_window(case, c.sale_date, raw):
            continue
        if c.product_id is None:
            unresolved_units += Decimal(str(c.units or 0))
            continue
        by_product[int(c.product_id)] += Decimal(str(c.units or 0))

    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case_id)).all()
    )
    updated = 0
    for line in lines:
        pid = int(line.product_id) if line.product_id is not None else None
        if pid is None:
            continue
        if claims:
            line.result_qty = float(by_product.get(pid, Decimal("0")))
            recompute_case_line(session, line, case=case, actor=actor, write_event=False)
            updated += 1

    session.flush()
    return {
        "case_id": case_id,
        "lines_updated": updated,
        "products_with_claims": len(by_product),
        "unresolved_claim_units": float(unresolved_units),
        "claim_rows": len(claims),
    }


def build_settlement_consolidation(session: Session, case_id: int) -> dict[str, Any]:
    """Per-line estimate vs result + flags. FLAG != BLOCK."""
    case = session.get(CporCase, case_id)
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case_id)).all()
    )
    claims = list(
        session.scalars(
            select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.case_id == case_id)
        ).all()
    )

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

    cst_flags = compute_cst_divergence_flags(session, case)

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

        items.append(
            {
                "line_id": line.id,
                "product_id": pid,
                "estimate_qty": estimate,
                "result_qty": result,
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
    }


def compute_cst_divergence_flags(session: Session, case: CporCase) -> dict[str, Any]:
    """Compare in-window claim units vs CST units for case customer. FLAG only."""
    if case.customer_id is None or case.window_start is None or case.window_end is None:
        return {"available": False, "reason": "missing_customer_or_window", "by_product": {}}

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
        return {"available": False, "reason": "no_cst_or_claim_rows", "by_product": {}}

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
