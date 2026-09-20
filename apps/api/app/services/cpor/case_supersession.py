"""BACKLOG-138 — the one writer for ``cpor_case.superseded_by_case_id``.

Soft-supersede a CPOR case (re-issue / replace) by pointing the loser at its
replacement. Nothing is deleted; ``status`` and ``workflow_status`` are left
alone — the pointer is the signal every reader already filters on
(``serialize``, ``incremental_unit_cost``, ``payment_recon``,
``portfolio_intelligence``, ``support_bias``, ``norms_and_comparable``,
``cpor_activation``, ``settlement_book_read``, ``promo_plan_builder``).

This is **not** the lineup writer. ``commercial_lineup_case.superseded_by_case_id``
is owned by ``commercial_planner/lineup_case_supersession.py`` and must never be
written from here (and vice versa). In-case *line* supersession (D-058) is a
different concept (BACKLOG-137).

Preview → confirm: ``preview_case_supersession`` computes blockers/warnings with no
writes; ``supersede_case`` refuses when blockers exist; ``restore_case_supersession``
clears the pointer. Callers own the transaction (no commit here).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine

EVENT_SUPERSEDED = "superseded"
EVENT_SUPERSEDES = "supersedes"
EVENT_SUPERSESSION_RESTORED = "supersession_restored"

# A settled case is money-final; hiding it from the settlement book via the pointer
# would silently drop paid support from every roll-up. Re-issue must start earlier.
_LOSER_BLOCKED_STATUSES = frozenset({"settled"})
# A dead replacement is not a replacement.
_WINNER_BLOCKED_STATUSES = frozenset({"cancelled", "rejected"})


def _case_summary(session: Session, case: CporCase) -> dict[str, Any]:
    line_count = int(
        session.scalar(select(func.count()).select_from(CporCaseLine).where(CporCaseLine.case_id == case.id))
        or 0
    )
    return {
        "id": int(case.id),
        "case_code": case.case_code,
        "case_name": case.case_name,
        "customer_id": int(case.customer_id),
        "status": case.status,
        "workflow_status": case.workflow_status,
        "window_start": case.window_start.isoformat() if case.window_start else None,
        "window_end": case.window_end.isoformat() if case.window_end else None,
        "line_count": line_count,
        "superseded_by_case_id": int(case.superseded_by_case_id) if case.superseded_by_case_id is not None else None,
    }


def preview_case_supersession(
    session: Session,
    *,
    loser: CporCase,
    winner: CporCase,
) -> dict[str, Any]:
    """Compute what ``supersede_case`` would do. No writes.

    ``blockers`` non-empty → supersede is refused. ``warnings`` are surfaced to the
    operator but do not block. ``already_superseded`` → the confirm is a no-op.
    """
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if int(loser.id) == int(winner.id):
        blockers.append({"code": "same_case", "message": "A case cannot supersede itself."})
    if (loser.tenant_id or "default") != (winner.tenant_id or "default"):
        blockers.append({"code": "tenant_mismatch", "message": "Replacement case belongs to another tenant."})
    if winner.superseded_by_case_id is not None:
        blockers.append(
            {
                "code": "winner_superseded",
                "message": f"Replacement case {winner.case_code} is itself superseded by case #{winner.superseded_by_case_id}.",
            }
        )
    if str(winner.status or "").lower() in _WINNER_BLOCKED_STATUSES:
        blockers.append(
            {"code": "winner_status", "message": f"Replacement case {winner.case_code} is {winner.status}."}
        )
    if str(loser.status or "").lower() in _LOSER_BLOCKED_STATUSES:
        blockers.append(
            {
                "code": "loser_settled",
                "message": f"Case {loser.case_code} is settled — money-final cases cannot be superseded.",
            }
        )
    already = loser.superseded_by_case_id is not None and int(loser.superseded_by_case_id) == int(winner.id)
    if loser.superseded_by_case_id is not None and not already:
        blockers.append(
            {
                "code": "loser_already_superseded",
                "message": (
                    f"Case {loser.case_code} is already superseded by case #{loser.superseded_by_case_id}. "
                    "Restore it before pointing it elsewhere."
                ),
            }
        )

    if int(loser.customer_id) != int(winner.customer_id):
        warnings.append({"code": "customer_mismatch", "message": "Replacement case is for a different customer."})
    if str(loser.promotion_type or "") != str(winner.promotion_type or ""):
        warnings.append(
            {"code": "promotion_type_mismatch", "message": "Replacement case has a different promotion type."}
        )
    if loser.window_end and winner.window_start and winner.window_start > loser.window_end:
        warnings.append(
            {"code": "window_gap", "message": "Replacement window starts after the original window ends."}
        )
    if str(loser.status or "").lower() in {"approved", "active", "ended"}:
        warnings.append(
            {
                "code": "loser_live",
                "message": (
                    f"Case {loser.case_code} is {loser.status}. Superseding removes it from owed / book / "
                    "comparables; its lines and events are kept."
                ),
            }
        )

    return {
        "loser": _case_summary(session, loser),
        "winner": _case_summary(session, winner),
        "already_superseded": already,
        "blockers": blockers,
        "warnings": warnings,
        "effects": [
            "cpor_case.superseded_by_case_id ← replacement id (status and workflow_status unchanged)",
            "Excluded from: settlement book, owed/paid recon, portfolio intelligence, support norms, "
            "comparable cases, incremental unit cost, promo plan drafts, activation matching",
            "Lines, events, claim evidence and payment evidence are kept; nothing is deleted",
            "Reversible via restore",
        ],
    }


def _event(
    session: Session,
    *,
    case_id: int,
    event_type: str,
    actor: str | None,
    payload: dict[str, Any],
) -> None:
    session.add(CporCaseEvent(case_id=int(case_id), event_type=event_type, actor=actor, payload_json=payload))


def supersede_case(
    session: Session,
    *,
    loser: CporCase,
    winner: CporCase,
    actor: str | None,
    reason: str | None = None,
    actor_trail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Point ``loser`` at ``winner``. Raises ``ValueError`` when preview has blockers.

    Idempotent: already pointing at the same winner → no writes, ``already_superseded=True``.
    Records a ``superseded`` event on the loser and a mirror ``supersedes`` event on the winner.
    Does not commit.
    """
    preview = preview_case_supersession(session, loser=loser, winner=winner)
    if preview["blockers"]:
        raise ValueError("; ".join(b["message"] for b in preview["blockers"]))
    if preview["already_superseded"]:
        return {**preview, "written": False}

    loser.superseded_by_case_id = int(winner.id)
    session.add(loser)
    trail = dict(actor_trail or {})
    _event(
        session,
        case_id=int(loser.id),
        event_type=EVENT_SUPERSEDED,
        actor=actor,
        payload={
            "superseded_by_case_id": int(winner.id),
            "superseded_by_case_code": winner.case_code,
            "reason": reason,
            "status_unchanged": loser.status,
            **trail,
        },
    )
    _event(
        session,
        case_id=int(winner.id),
        event_type=EVENT_SUPERSEDES,
        actor=actor,
        payload={"supersedes_case_id": int(loser.id), "supersedes_case_code": loser.case_code, "reason": reason, **trail},
    )
    session.flush()
    return {**preview, "loser": _case_summary(session, loser), "written": True}


def restore_case_supersession(
    session: Session,
    *,
    case: CporCase,
    actor: str | None,
    reason: str | None = None,
    actor_trail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clear the pointer (soft reversal). No-op when not superseded. Does not commit."""
    previous = case.superseded_by_case_id
    if previous is None:
        return {"case": _case_summary(session, case), "restored": False, "previous_superseded_by_case_id": None}
    case.superseded_by_case_id = None
    session.add(case)
    _event(
        session,
        case_id=int(case.id),
        event_type=EVENT_SUPERSESSION_RESTORED,
        actor=actor,
        payload={"previous_superseded_by_case_id": int(previous), "reason": reason, **dict(actor_trail or {})},
    )
    session.flush()
    return {
        "case": _case_summary(session, case),
        "restored": True,
        "previous_superseded_by_case_id": int(previous),
    }
