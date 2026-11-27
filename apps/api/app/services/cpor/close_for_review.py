"""Close an open customer promotion for review when its window has ended (Warren, 2026-11-27).

Actual sales are the customer's uploaded sell-through (``fact_customer_sellthrough``) for that
customer. Sale-date rule: a row counts when its ``period_start_date`` is inside the promotion
window; the whole row counts; chain-grain and store-grain rows are summed; month-to-date rows
count and are flagged. There is no lookback before the window. The target is the forecast units on
the case lines (``estimate_qty``) for that same window.

A case closes to ``ended``, the existing status that means closed for review, only when that
customer's uploaded sales cover the window end. Until then it stays ``active`` and a held event
says why. The comparison saved on the ``transition_end`` event is the reconciliation.

It does not write ``result_qty``: that stays settlement-written from the customer's claim file.
It notifies no one and sends nothing to the customer.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.channel_intelligence.cst_read_model import _period_end
from app.services.commercial_tenant_profile import reporting_today
from app.services.cpor.lifecycle import STOCK_ACTION_ORIGIN, can_transition, workflow_status_for
from app.services.cpor.line_window import effective_line_window, straddle_weeks
from app.services.cpor.pivot import is_voided_line
from app.services.cpor.promotion_type_vocab import CUSTOMER_SELL_THROUGH, promotion_family

logger = logging.getLogger(__name__)

CLOSE_FOR_REVIEW_ACTOR = "system:close_for_review"
CLOSE_FOR_REVIEW_TRIGGER = "window_ended"
HELD_EVENT_TYPE = "close_for_review_held"

FLAG_NO_SALES_LOADED = "no_sales_loaded"
FLAG_SALES_NOT_THROUGH_WINDOW_END = "sales_not_loaded_through_window_end"
FLAG_MTD_ESTIMATE = "includes_mtd_estimate"
FLAG_WINDOW_WEEK_STRADDLE = "window_week_straddle"

# Warren, 27 Nov: a person may end a promotion before sales cover the window.
# The gap stays on the existing transition event so settlement can still see it.
SALES_WINDOW_GAP_FLAGS = (FLAG_NO_SALES_LOADED, FLAG_SALES_NOT_THROUGH_WINDOW_END)
SALES_WINDOW_GAP_LABEL = {
    FLAG_NO_SALES_LOADED: "no sales loaded",
    FLAG_SALES_NOT_THROUGH_WINDOW_END: "sales do not cover the window end",
}

OUTCOME_CLOSED = "closed"
OUTCOME_HELD = "held"


class SaleRow(NamedTuple):
    product_id: int
    sale_date: date
    units: float
    is_mtd_estimate: bool


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def sales_covered_through(latest_start_by_period_type: dict[str, date]) -> date | None:
    """Last day covered by the customer's uploaded sales: the latest period end over all rows."""
    ends = [_period_end(start, ptype) for ptype, start in latest_start_by_period_type.items()]
    return max(ends) if ends else None


def sales_cover_window(case: CporCase, covered_through: date | None) -> bool:
    return (
        covered_through is not None
        and case.window_end is not None
        and (covered_through >= case.window_end)
    )


def held_reason(covered_through: date | None) -> str:
    return FLAG_NO_SALES_LOADED if covered_through is None else FLAG_SALES_NOT_THROUGH_WINDOW_END


def sales_window_gap(reconciliation: dict | None) -> str | None:
    """The coverage-gap flag on a reconciliation, when sales do not cover the window."""
    flags = (reconciliation or {}).get("flags") or []
    for flag in SALES_WINDOW_GAP_FLAGS:
        if flag in flags:
            return flag
    return None


def gap_record_from_event(actor: str | None, payload: dict | None) -> dict | None:
    """What settlement reads from the existing ``transition_end`` event. No new column."""
    if not isinstance(payload, dict):
        return None
    explicit = payload.get("sales_window_gap")
    flag = explicit if isinstance(explicit, str) and explicit else sales_window_gap(payload.get("reconciliation"))
    if not flag:
        return None
    raw_reason = payload.get("reason") if isinstance(payload.get("reason"), str) else payload.get("comment")
    reason = raw_reason.strip() if isinstance(raw_reason, str) and raw_reason.strip() else None
    stamped = actor.strip() if isinstance(actor, str) and actor.strip() else None
    payload_actor = payload.get("actor")
    if stamped is None and isinstance(payload_actor, str) and payload_actor.strip():
        stamped = payload_actor.strip()
    return {
        "flag": flag,
        "label": SALES_WINDOW_GAP_LABEL.get(flag, flag),
        "reason": reason,
        "actor": stamped,
    }


def reconcile_window(
    case: CporCase,
    lines: Iterable[CporCaseLine],
    sales: Iterable[SaleRow],
    *,
    covered_through: date | None,
) -> dict[str, Any]:
    """Actual units in each window against the forecast target for that window.

    Lines sharing a product and a window are one group, so one sale is never counted twice. A sale
    counts for a group when its date is inside the group's window (both ends included). Nothing is
    pro-rated.
    """
    groups: dict[tuple[int, date, date], list[CporCaseLine]] = defaultdict(list)
    for line in lines:
        if line.product_id is None or is_voided_line(line):
            continue
        ws, we = effective_line_window(line, case)
        if ws is None or we is None:
            continue
        groups[(int(line.product_id), ws, we)].append(line)

    sales_by_pid: dict[int, list[SaleRow]] = defaultdict(list)
    for s in sales:
        sales_by_pid[int(s.product_id)].append(s)

    out_lines: list[dict[str, Any]] = []
    total_target = 0.0
    total_actual = 0.0
    any_mtd = False
    for (pid, ws, we), members in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        target = sum(_f(ln.estimate_qty) for ln in members)
        in_window = [s for s in sales_by_pid.get(pid, []) if ws <= s.sale_date <= we]
        actual = sum(_f(s.units) for s in in_window)
        flags: list[str] = []
        if any(s.is_mtd_estimate for s in in_window):
            flags.append(FLAG_MTD_ESTIMATE)
            any_mtd = True
        if straddle_weeks(ws, we):
            flags.append(FLAG_WINDOW_WEEK_STRADDLE)
        total_target += target
        total_actual += actual
        out_lines.append(
            {
                "product_id": pid,
                "line_ids": sorted(int(ln.id) for ln in members if ln.id is not None),
                "window_start": ws.isoformat(),
                "window_end": we.isoformat(),
                "target_units": target,
                "actual_units": actual,
                "delivery_pct": (actual / target) if target > 0 else None,
                "flags": flags,
            }
        )

    flags: list[str] = []
    if covered_through is None:
        flags.append(FLAG_NO_SALES_LOADED)
    elif not sales_cover_window(case, covered_through):
        flags.append(FLAG_SALES_NOT_THROUGH_WINDOW_END)
    if any_mtd:
        flags.append(FLAG_MTD_ESTIMATE)
    return {
        "basis": "customer_sell_through_sale_date_in_window",
        "target_basis": "estimate_qty",
        "window_start": case.window_start.isoformat() if case.window_start else None,
        "window_end": case.window_end.isoformat() if case.window_end else None,
        "sales_covered_through": covered_through.isoformat() if covered_through else None,
        "target_units": total_target,
        "actual_units": total_actual,
        "delivery_pct": (total_actual / total_target) if total_target > 0 else None,
        "lines": out_lines,
        "flags": flags,
    }


def _customer_covered_through(session: Session, case: CporCase) -> date | None:
    rows = session.execute(
        select(
            FactCustomerSellthrough.period_type,
            func.max(FactCustomerSellthrough.period_start_date),
        )
        .where(
            FactCustomerSellthrough.tenant_id == (case.tenant_id or "default"),
            FactCustomerSellthrough.customer_id == int(case.customer_id),
        )
        .group_by(FactCustomerSellthrough.period_type)
    ).all()
    return sales_covered_through({str(r[0] or ""): r[1] for r in rows if r[1] is not None})


def reconcile_case_window(session: Session, case: CporCase) -> dict[str, Any]:
    """Read the case lines and the customer's sell-through inside the case window; reconcile."""
    lines = list(session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all())
    product_ids = sorted({int(ln.product_id) for ln in lines if ln.product_id is not None})
    sales: list[SaleRow] = []
    if product_ids and case.window_start is not None and case.window_end is not None:
        rows = session.execute(
            select(
                FactCustomerSellthrough.product_id,
                FactCustomerSellthrough.period_start_date,
                FactCustomerSellthrough.units_sold,
                FactCustomerSellthrough.is_mtd_estimate,
            ).where(
                FactCustomerSellthrough.tenant_id == (case.tenant_id or "default"),
                FactCustomerSellthrough.customer_id == int(case.customer_id),
                FactCustomerSellthrough.product_id.in_(product_ids),
                FactCustomerSellthrough.period_start_date >= case.window_start,
                FactCustomerSellthrough.period_start_date <= case.window_end,
            )
        ).all()
        sales = [SaleRow(int(r[0]), r[1], _f(r[2]), bool(r[3])) for r in rows]
    covered = _customer_covered_through(session, case)
    return reconcile_window(case, lines, sales, covered_through=covered)


def due_for_review(case: CporCase, today: date) -> bool:
    """Active, current, customer sell-through, not a stock action, window ended before today.

    Approved cases that never went active are not due: they never ran.
    """
    return (
        case.status == "active"
        and case.superseded_by_case_id is None
        and (case.origin or "") != STOCK_ACTION_ORIGIN
        and promotion_family(case.promotion_type) == CUSTOMER_SELL_THROUGH
        and case.window_end is not None
        and case.window_end < today
        and can_transition(case.status, "end")
    )


def end_event_payload(
    case: CporCase, *, from_status: str, reconciliation: dict[str, Any], trigger: str
) -> dict:
    """The ``transition_end`` payload of the automatic close."""
    return {
        "from": from_status,
        "to": "ended",
        "action": "end",
        "trigger": trigger,
        "export_version": case.export_version,
        "reconciliation": reconciliation,
    }


def _last_held_covered_through(session: Session, case_id: int) -> tuple[bool, str | None]:
    """Whether a held event exists, and the sales coverage it recorded."""
    payload = session.scalar(
        select(CporCaseEvent.payload_json)
        .where(CporCaseEvent.case_id == case_id, CporCaseEvent.event_type == HELD_EVENT_TYPE)
        .order_by(CporCaseEvent.id.desc())
        .limit(1)
    )
    if payload is None:
        return False, None
    return True, (payload or {}).get("sales_covered_through")


def close_case_for_review(
    session: Session,
    case: CporCase,
    *,
    today: date,
    actor: str = CLOSE_FOR_REVIEW_ACTOR,
) -> dict[str, Any] | None:
    """Reconcile one due case; close it to ``ended`` only when its sales cover the window.

    Returns ``{"outcome": "closed" | "held", ...}``, or None when the case is not due. A held case
    stays ``active``; its held event is written again only when the sales coverage has moved, so
    a daily run does not add one every day. Idempotent: a case that is no longer active is not due.
    """
    if not due_for_review(case, today):
        return None
    reconciliation = reconcile_case_window(session, case)
    covered = reconciliation["sales_covered_through"]
    covered_date = date.fromisoformat(covered) if covered else None
    if not sales_cover_window(case, covered_date):
        reason = held_reason(covered_date)
        held_before, held_covered = _last_held_covered_through(session, case.id)
        recorded = not (held_before and held_covered == covered)
        if recorded:
            session.add(
                CporCaseEvent(
                    case_id=case.id,
                    event_type=HELD_EVENT_TYPE,
                    actor=actor,
                    payload_json={
                        "reason": reason,
                        "window_end": reconciliation["window_end"],
                        "sales_covered_through": covered,
                        "reconciliation": reconciliation,
                    },
                )
            )
        return {
            "outcome": OUTCOME_HELD,
            "reason": reason,
            "event_recorded": recorded,
            "reconciliation": reconciliation,
        }

    from_status = case.status
    case.status = "ended"
    case.workflow_status = workflow_status_for(case.status)
    session.add(case)
    payload = end_event_payload(
        case,
        from_status=from_status,
        reconciliation=reconciliation,
        trigger=CLOSE_FOR_REVIEW_TRIGGER,
    )
    session.add(
        CporCaseEvent(
            case_id=case.id, event_type="transition_end", actor=actor, payload_json=payload
        )
    )
    return {"outcome": OUTCOME_CLOSED, "event": payload, "reconciliation": reconciliation}


def close_due_cases(session: Session, *, today: date | None = None) -> dict[str, Any]:
    """Close every due case whose sales cover its window; hold the rest. One commit per case.

    ``today`` is each case tenant's reporting date unless a date is passed. The family is checked
    per case by ``due_for_review``, which matches stored type names normalised.
    """
    # Coarse SQL bound: no zone's date is more than one day ahead of the server's UTC date. The
    # exact per-tenant check is ``due_for_review``.
    bound = today if today is not None else date.today() + timedelta(days=1)
    ids = list(
        session.scalars(
            select(CporCase.id)
            .where(
                CporCase.status == "active",
                CporCase.superseded_by_case_id.is_(None),
                CporCase.window_end < bound,
            )
            .order_by(CporCase.id.asc())
        ).all()
    )
    closed: list[int] = []
    held: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for case_id in ids:
        try:
            case = session.get(CporCase, case_id)
            if case is None:
                continue
            case_today = (
                today if today is not None else reporting_today(case.tenant_id or "default")
            )
            result = close_case_for_review(session, case, today=case_today)
            if result is None:
                continue
            session.commit()
            if result["outcome"] == OUTCOME_CLOSED:
                closed.append(int(case_id))
            else:
                held.append(
                    {
                        "case_id": int(case_id),
                        "reason": result["reason"],
                        "sales_covered_through": result["reconciliation"]["sales_covered_through"],
                    }
                )
        except Exception as exc:  # noqa: BLE001 — one case must not stop the batch
            session.rollback()
            logger.exception("cpor close for review failed for case %s", case_id)
            failed.append({"case_id": int(case_id), "error": type(exc).__name__})
    return {"candidates": len(ids), "closed": closed, "held": held, "failed": failed}
