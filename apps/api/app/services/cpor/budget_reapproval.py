"""CPOR over-money-ceiling reapproval (Q-001 / BACKLOG-095).

When the tenant binding axis is money and spend exceeds the configured ceiling,
cases must be explicitly reapproved (confirm_over_budget_reapproval) before
approve/export can proceed under HARD_ENFORCE_BUDGET.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.services import commercial_tenant_profile as tenant_profile

# Statuses whose planned support counts toward the money ceiling.
_COMMITTED_STATUSES = frozenset(
    {"proposed", "approved", "active", "ended", "settled"}
)


def case_support_usd(session: Session, case_id: int) -> float:
    """Sum planned support USD for a case's lines."""
    rows = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == int(case_id))).all()
    total = 0.0
    for line in rows:
        if line.ttl_support_usd is not None:
            total += float(line.ttl_support_usd)
        elif line.support_usd is not None and line.estimate_qty is not None:
            total += float(line.support_usd) * float(line.estimate_qty)
    return total


def portfolio_committed_usd(session: Session, *, include_case_id: int | None = None) -> float:
    """Sum support USD across cases in committed lifecycle statuses."""
    cases = session.scalars(
        select(CporCase).where(CporCase.status.in_(sorted(_COMMITTED_STATUSES)))
    ).all()
    total = 0.0
    seen = set()
    for case in cases:
        seen.add(int(case.id))
        total += case_support_usd(session, int(case.id))
    if include_case_id is not None and int(include_case_id) not in seen:
        total += case_support_usd(session, int(include_case_id))
    return total


def money_ceiling_usd() -> float | None:
    raw = getattr(tenant_profile, "MONEY_CEILING_USD", None)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def evaluate_money_position(
    session: Session,
    *,
    case_id: int,
    include_this_case: bool = True,
) -> dict[str, Any]:
    """Explain money-ceiling position for a case (portfolio drawn vs tenant ceiling)."""
    ceiling = money_ceiling_usd()
    drawn = portfolio_committed_usd(
        session,
        include_case_id=int(case_id) if include_this_case else None,
    )
    case_usd = case_support_usd(session, int(case_id))
    over = bool(ceiling is not None and drawn > ceiling)
    case = session.get(CporCase, int(case_id))
    flagged = bool(case.needs_reapproval) if case is not None else False
    return {
        "binding_axis": tenant_profile.CONSTRAINT_AXIS,
        "over_budget_action": tenant_profile.OVER_BUDGET_ACTION,
        "hard_enforce": bool(tenant_profile.HARD_ENFORCE_BUDGET),
        "money_ceiling_usd": ceiling,
        "portfolio_committed_usd": round(drawn, 4),
        "case_support_usd": round(case_usd, 4),
        "money_over": over,
        "needs_reapproval": flagged,
        "status": (
            "over"
            if over
            else ("needs_reapproval" if flagged else ("ok" if ceiling else "no_ceiling_configured"))
        ),
    }


def should_require_reapproval(position: dict[str, Any]) -> bool:
    if tenant_profile.CONSTRAINT_AXIS not in ("money", "dual"):
        return False
    if tenant_profile.OVER_BUDGET_ACTION != "require_reapproval":
        return False
    return bool(position.get("money_over") or position.get("needs_reapproval"))


def apply_reapproval_flag(session: Session, case: CporCase, *, money_over: bool) -> bool:
    """Set needs_reapproval when money is over; return whether flag is now True."""
    if money_over and tenant_profile.CONSTRAINT_AXIS in ("money", "dual"):
        case.needs_reapproval = True
    return bool(case.needs_reapproval)


def gate_detail(position: dict[str, Any], *, action: str) -> dict[str, Any]:
    return {
        "message": (
            f"Money ceiling exceeded — case requires over-budget reapproval before {action}. "
            "Pass confirm_over_budget_reapproval=true to approve, or reduce support / raise ceiling."
            if action == "approve"
            else "Money ceiling / needs_reapproval — export blocked until case is reapproved."
        ),
        "remediation": "confirm_over_budget_reapproval",
        "budget": position,
    }
