"""CPOR server-side recompute path (spec §3 — never trust client math).

Writes dealer_price / support_unit / ttl_support / support_usd / ttl_support_usd
(and ttl_result / ttl_result_usd when result_qty present) onto cpor_case_line.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine
from app.services.cpor.config import STORAGE_QUANTIZE
from app.services.cpor.waterfall import compute_line_waterfall, quantize_money


def _q(value) -> float | None:
    if value is None:
        return None
    return float(quantize_money(value, STORAGE_QUANTIZE))


def recompute_case_line(
    session: Session,
    line: CporCaseLine,
    *,
    case: CporCase | None = None,
    actor: str | None = None,
    write_event: bool = False,
) -> dict[str, Any]:
    """Recompute one line from stored inputs. Returns values + flags (FLAG ≠ BLOCK)."""
    case = case or session.get(CporCase, line.case_id)
    if case is None:
        raise ValueError(f"cpor_case id={line.case_id} not found for line id={line.id}")

    result = compute_line_waterfall(
        srp=line.srp,
        vat_rate=line.vat_rate,
        dealer_margin_pct=line.dealer_margin_pct,
        cost_basis=line.cost_basis,
        estimate_qty=line.estimate_qty,
        result_qty=line.result_qty,
        case_roe=case.roe_snapshot,
        channel=case.channel or "reseller",
    )

    changed: dict[str, Any] = {}
    line.dealer_price = _q(result["dealer_price"])
    changed["dealer_price"] = line.dealer_price

    if result["support_unit"] is None:
        line.support_unit = None
        line.ttl_support = None
        line.support_usd = None
        line.ttl_result = None
        line.ttl_support_usd = None
        line.ttl_result_usd = None
    else:
        line.support_unit = _q(result["support_unit"])
        line.ttl_support = _q(result["ttl_support"])
        line.support_usd = _q(result["support_usd"])
        line.ttl_result = _q(result["ttl_result"]) if result["ttl_result"] is not None else None
        line.ttl_support_usd = (
            _q(result["ttl_support_usd"]) if result.get("ttl_support_usd") is not None else None
        )
        line.ttl_result_usd = (
            _q(result["ttl_result_usd"]) if result.get("ttl_result_usd") is not None else None
        )
        changed.update(
            {
                "support_unit": line.support_unit,
                "ttl_support": line.ttl_support,
                "support_usd": line.support_usd,
                "ttl_result": line.ttl_result,
                "ttl_support_usd": line.ttl_support_usd,
                "ttl_result_usd": line.ttl_result_usd,
            }
        )

    session.add(line)

    if write_event:
        session.add(
            CporCaseEvent(
                case_id=case.id,
                event_type="recomputed",
                actor=actor,
                payload_json={"line_id": line.id, "changed": changed, "flags": result["flags"]},
            )
        )

    return {
        "line_id": line.id,
        "case_id": case.id,
        "values": {
            "dealer_price": line.dealer_price,
            "support_unit": line.support_unit,
            "ttl_support": line.ttl_support,
            "support_usd": line.support_usd,
            "ttl_result": line.ttl_result,
            "ttl_support_usd": line.ttl_support_usd,
            "ttl_result_usd": line.ttl_result_usd,
        },
        "full_precision": {
            "dealer_price": str(result["dealer_price"]),
            "support_unit": str(result["support_unit"]) if result["support_unit"] is not None else None,
            "ttl_support": str(result["ttl_support"]) if result["ttl_support"] is not None else None,
            "ttl_result": str(result["ttl_result"]) if result["ttl_result"] is not None else None,
            "support_usd": str(result["support_usd"]) if result["support_usd"] is not None else None,
            "ttl_support_usd": (
                str(result["ttl_support_usd"]) if result.get("ttl_support_usd") is not None else None
            ),
            "ttl_result_usd": (
                str(result["ttl_result_usd"]) if result.get("ttl_result_usd") is not None else None
            ),
        },
        "flags": list(result["flags"]),
    }


def recompute_case(
    session: Session,
    case: CporCase,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Recompute all lines on a case; one recomputed event for the whole call."""
    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
    )
    reports: list[dict[str, Any]] = []
    all_flags: list[str] = []
    for line in lines:
        rep = recompute_case_line(session, line, case=case, write_event=False)
        reports.append(rep)
        all_flags.extend(rep["flags"])

    session.add(
        CporCaseEvent(
            case_id=case.id,
            event_type="recomputed",
            actor=actor,
            payload_json={
                "line_count": len(reports),
                "line_ids": [r["line_id"] for r in reports],
                "flags": sorted(set(all_flags)),
            },
        )
    )
    return {"case_id": case.id, "lines": reports, "flags": sorted(set(all_flags))}
