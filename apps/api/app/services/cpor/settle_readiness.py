"""Settle readiness facts derived from existing CPOR columns (NS-1a — no schema)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine, CporClaimEvidenceLine

FX_MODES = frozenset({"booked", "floating"})

# Line flags that represent open assumptions on the case surface (existing `_line_flags` output).
ASSUMPTION_LINE_FLAGS: frozenset[str] = frozenset(
    {
        "no_cost_basis",
        "no_cost_evidence",
        "assumed_currency",
        "manual_deviation_from_evidence",
        "inter_tier_deviation",
        "cost_basis_drift",
        "no_distributor",
    }
)


def fx_declared(case: CporCase) -> bool:
    return case.roe_snapshot is not None and float(case.roe_snapshot) > 0


def case_missing_roe(case: CporCase) -> bool:
    """Inverse of fx_declared — null, zero, or negative ROE is undeclared FX."""
    return not fx_declared(case)


def count_open_assumptions_from_line_flags(flags: list[str]) -> int:
    return sum(1 for f in flags if f in ASSUMPTION_LINE_FLAGS)


def fx_mode_valid(case: CporCase) -> bool:
    mode = getattr(case, "fx_mode", None)
    return mode in FX_MODES


def settle_fx_blocked(case: CporCase) -> bool:
    """True when settle must be refused for FX reasons (NS-1b)."""
    return case_missing_roe(case) or not fx_mode_valid(case)


def build_fx_basis_line(case: CporCase) -> str | None:
    if settle_fx_blocked(case):
        return None
    roe = float(case.roe_snapshot)  # type: ignore[arg-type]
    mode = str(case.fx_mode)
    return f"FX basis: {mode} · ROE ZAR {roe:.2f}/USD"


def build_settle_readiness(
    case: CporCase,
    *,
    claim_row_count: int,
    open_assumption_count: int,
) -> dict[str, Any]:
    declared = fx_declared(case)
    roe = float(case.roe_snapshot) if declared else None
    mode_ok = fx_mode_valid(case)
    return {
        "fx_declared": declared,
        "roe_snapshot": roe,
        "fx_mode": getattr(case, "fx_mode", None),
        "fx_mode_declared": mode_ok,
        "fx_settle_allowed": declared and mode_ok,
        "fx_basis_line": build_fx_basis_line(case),
        "open_assumption_count": int(open_assumption_count),
        "claim_evidence_count": int(claim_row_count),
    }


def load_claim_counts_by_case_id(session: Session, case_ids: list[int]) -> dict[int, int]:
    if not case_ids:
        return {}
    rows = session.execute(
        select(CporClaimEvidenceLine.case_id, func.count())
        .where(CporClaimEvidenceLine.case_id.in_(case_ids))
        .group_by(CporClaimEvidenceLine.case_id)
    ).all()
    return {int(case_id): int(cnt) for case_id, cnt in rows}


def load_open_assumption_counts_by_case_id(session: Session, case_ids: list[int]) -> dict[int, int]:
    """Count case lines carrying at least one assumption flag."""
    if not case_ids:
        return {}
    lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id.in_(case_ids))).all()
    by_case: dict[int, int] = {cid: 0 for cid in case_ids}
    for line in lines:
        flags: list[str] = []
        if line.distributor_id is None:
            flags.append("no_distributor")
        if line.cost_basis is None:
            flags.append("no_cost_basis")
        ev = line.cost_evidence_json or {}
        for f in ev.get("flags") or []:
            if f not in flags:
                flags.append(str(f))
        if count_open_assumptions_from_line_flags(flags) > 0:
            by_case[int(line.case_id)] = by_case.get(int(line.case_id), 0) + 1
    return by_case


def load_settle_readiness_by_case_id(session: Session, cases: list[CporCase]) -> dict[int, dict[str, Any]]:
    case_ids = [int(c.id) for c in cases]
    claim_by = load_claim_counts_by_case_id(session, case_ids)
    assumption_by = load_open_assumption_counts_by_case_id(session, case_ids)
    return {
        int(case.id): build_settle_readiness(
            case,
            claim_row_count=claim_by.get(int(case.id), 0),
            open_assumption_count=assumption_by.get(int(case.id), 0),
        )
        for case in cases
    }
