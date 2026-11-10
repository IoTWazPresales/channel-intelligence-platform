"""Turn a slow or unsold line into a draft promotion, a move, or a return.

Viewing the board does not write. An explicit action does. Move and return are
stock actions: they are excluded from support comparisons and are not claims.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupLine
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer
from app.services.cpor.promo_plan_builder import (
    _positive_srp,
    create_case_from_promo_draft,
    load_promotion_line_evidence,
)
from app.services.cpor.promotion_type_vocab import CPOR_PROMOTION_TYPE_SET
from app.services.store_dc.read_model import build_customer_view
from app.services.store_dc.rules import SUGGESTIONS, stock_action_in_notes

OPEN_CASE_STATUSES = ("draft", "proposed", "approved", "active")
PROMOTE_TYPE = "Stock PP (In-Direct)"
CASE_NAMES = {
    "promote": "Aged stock promotion",
    "move": "Move aged stock",
    "return": "Return aged stock",
}
MAX_LISTED_LINES = 200


def current_period_label(today: date | None = None) -> str:
    day = today or date.today()
    quarter = (day.month - 1) // 3 + 1
    return f"{day.year}Q{quarter}"


def _blocks(view: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    account = view.get("account")
    if isinstance(account, dict):
        blocks.append(account)
    blocks.extend(block for block in (view.get("sites") or []) if isinstance(block, dict))
    for section in view.get("dc_sections") or []:
        if not isinstance(section, dict):
            continue
        nested = section.get("sites")
        if isinstance(nested, list):
            blocks.extend(block for block in nested if isinstance(block, dict))
        elif isinstance(section.get("lines"), list):
            blocks.append(section)
    return blocks


def _suggestion_rows(view: dict[str, Any], *, customer_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in _blocks(view):
        site = block.get("site_label")
        for line in block.get("lines") or []:
            if not line.get("suggestions"):
                continue
            rows.append({**line, "site_label": site, "customer_id": int(customer_id)})
    return rows


def list_aged_stock(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None = None,
) -> dict[str, Any]:
    """Slow and unsold lines. This read does not create a case."""
    if customer_id is not None:
        customer_ids = [int(customer_id)]
    else:
        customer_ids = [
            int(row)
            for row in session.scalars(
                select(DimCustomer.id).where(
                    DimCustomer.tenant_id == tenant_id,
                    DimCustomer.merged_into_customer_id.is_(None),
                    DimCustomer.customer_status == "active",
                )
            ).all()
        ]
    lines: list[dict[str, Any]] = []
    for cid in customer_ids:
        try:
            view = build_customer_view(session, tenant_id, cid)
        except LookupError:
            continue
        lines.extend(_suggestion_rows(view, customer_id=cid))
        if len(lines) >= MAX_LISTED_LINES:
            break
    truncated = len(lines) > MAX_LISTED_LINES
    return {"lines": lines[:MAX_LISTED_LINES], "truncated": truncated}


def _srp_for_line(session: Session, *, customer_id: int, product_id: int, tenant_id: str) -> float | None:
    """Shopper price, then lineup shelf price. Sell-in DAP is not a promotion price."""
    evidence = load_promotion_line_evidence(
        session,
        customer_id=customer_id,
        product_id=product_id,
        distributor_id=None,
        tenant_id=tenant_id,
    )
    listing_price = (evidence.get("listing") or {}).get("last_observed_price")
    msrp = session.execute(
        select(CommercialLineupLine.msrp_local)
        .where(CommercialLineupLine.product_id == int(product_id))
        .order_by(CommercialLineupLine.id.desc())
        .limit(1)
    ).scalar()
    return _positive_srp(listing_price, float(msrp) if msrp is not None else None)


def _open_case_id(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_id: int,
    action: str,
) -> int | None:
    rows = session.execute(
        select(CporCase.id, CporCase.notes)
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(
            CporCase.tenant_id == tenant_id,
            CporCase.customer_id == int(customer_id),
            CporCaseLine.product_id == int(product_id),
            CporCase.status.in_(OPEN_CASE_STATUSES),
        )
    ).all()
    for case_id, notes in rows:
        if stock_action_in_notes(notes) == action:
            return int(case_id)
    return None


def _matching_line(
    rows: list[dict[str, Any]],
    *,
    product_id: int,
    site_label: str | None,
) -> dict[str, Any] | None:
    matches = [row for row in rows if int(row["product_id"]) == int(product_id)]
    if site_label is not None:
        wanted = site_label.strip()
        matches = [row for row in matches if (row.get("site_label") or "") == wanted]
    return matches[0] if matches else None


def execute_aged_stock_action(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_id: int,
    action: str,
    actor: str | None,
    site_label: str | None = None,
    period_label: str | None = None,
    generate_case_code,
    record_event,
    recompute_case_line,
    resolve_default_margin,
    suggest_cost_basis,
) -> dict[str, Any]:
    if action not in SUGGESTIONS:
        raise ValueError(f"unknown_stock_action={action}")
    if PROMOTE_TYPE not in CPOR_PROMOTION_TYPE_SET:
        raise ValueError("stock_promotion_type_missing")
    view = build_customer_view(session, tenant_id, int(customer_id))
    line = _matching_line(_suggestion_rows(view, customer_id=int(customer_id)), product_id=product_id, site_label=site_label)
    if line is None:
        raise ValueError("line_not_slow_or_unsold")
    soh = line.get("stock_on_hand")
    if soh is None or float(soh) <= 0:
        raise ValueError("no_stock_to_act_on")
    existing = _open_case_id(
        session,
        tenant_id=tenant_id,
        customer_id=int(customer_id),
        product_id=int(product_id),
        action=action,
    )
    if existing is not None:
        return {
            "created": False,
            "case_id": existing,
            "action": action,
            "reason": "already_open",
            "customer_id": int(customer_id),
            "product_id": int(product_id),
        }
    srp = _srp_for_line(session, customer_id=int(customer_id), product_id=int(product_id), tenant_id=tenant_id)
    if srp is None:
        raise ValueError("no_positive_srp")
    period = period_label or current_period_label()
    logistics = action != "promote"
    created = create_case_from_promo_draft(
        session,
        customer_id=int(customer_id),
        promotion_type=PROMOTE_TYPE,
        tenant_id=tenant_id,
        period_label=period,
        actor=actor,
        lines=[
            {
                "product_id": int(product_id),
                "srp": srp,
                "estimate_qty": float(soh),
                "pod_quarter": period,
                "distributor_id": None,
            }
        ],
        stock_action=action,
        case_origin="stock_action" if logistics else "proposed_by_cip",
        case_name_override=CASE_NAMES[action],
        intelligence_exclude=logistics,
        generate_case_code=generate_case_code,
        record_event=record_event,
        recompute_case_line=recompute_case_line,
        resolve_default_margin=resolve_default_margin,
        suggest_cost_basis=suggest_cost_basis,
    )
    return {
        "created": True,
        "action": action,
        "support_claim": not logistics,
        "case_id": created["case_id"],
        "case_code": created["case_code"],
        "customer_id": int(customer_id),
        "product_id": int(product_id),
        "estimate_qty": float(soh),
        "href": created.get("href"),
    }


def _merged_promote_lines(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_product: dict[int, dict[str, Any]] = {}
    for row in rows:
        product_id = int(row["product_id"])
        soh = row.get("stock_on_hand")
        if soh is None or float(soh) <= 0:
            skipped.append({"customer_id": customer_id, "product_id": product_id, "reason": "no_stock_to_act_on"})
            continue
        if _open_case_id(
            session,
            tenant_id=tenant_id,
            customer_id=customer_id,
            product_id=product_id,
            action="promote",
        ) is not None:
            skipped.append({"customer_id": customer_id, "product_id": product_id, "reason": "already_open"})
            continue
        current = by_product.get(product_id)
        if current is None:
            by_product[product_id] = {"product_id": product_id, "estimate_qty": float(soh)}
        else:
            current["estimate_qty"] = float(current["estimate_qty"]) + float(soh)
    ready: list[dict[str, Any]] = []
    for product_id, spec in by_product.items():
        srp = _srp_for_line(session, customer_id=customer_id, product_id=product_id, tenant_id=tenant_id)
        if srp is None:
            skipped.append({"customer_id": customer_id, "product_id": product_id, "reason": "no_positive_srp"})
            continue
        ready.append(
            {
                "product_id": product_id,
                "srp": srp,
                "estimate_qty": spec["estimate_qty"],
                "distributor_id": None,
            }
        )
    return ready


def auto_propose_from_intelligence(
    session: Session,
    *,
    tenant_id: str,
    actor: str | None,
    customer_id: int | None = None,
    period_label: str | None = None,
    generate_case_code,
    record_event,
    recompute_case_line,
    resolve_default_margin,
    suggest_cost_basis,
) -> dict[str, Any]:
    """Raise one draft promotion per customer from slow or unsold stock."""
    period = period_label or current_period_label()
    listed = list_aged_stock(session, tenant_id=tenant_id, customer_id=customer_id)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in listed["lines"]:
        grouped.setdefault(int(row["customer_id"]), []).append(row)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for cid, rows in grouped.items():
        specs = _merged_promote_lines(session, tenant_id=tenant_id, customer_id=cid, rows=rows, skipped=skipped)
        if not specs:
            continue
        for spec in specs:
            spec["pod_quarter"] = period
        try:
            case = create_case_from_promo_draft(
                session,
                customer_id=cid,
                promotion_type=PROMOTE_TYPE,
                tenant_id=tenant_id,
                period_label=period,
                actor=actor,
                lines=specs,
                stock_action="promote",
                case_origin="proposed_by_cip",
                case_name_override=CASE_NAMES["promote"],
                intelligence_exclude=False,
                generate_case_code=generate_case_code,
                record_event=record_event,
                recompute_case_line=recompute_case_line,
                resolve_default_margin=resolve_default_margin,
                suggest_cost_basis=suggest_cost_basis,
            )
        except ValueError as exc:
            skipped.append({"customer_id": cid, "reason": str(exc), "product_id": None})
            continue
        created.append(
            {
                "customer_id": cid,
                "case_id": case["case_id"],
                "case_code": case["case_code"],
                "line_count": len(specs),
                "href": case.get("href"),
            }
        )
    return {"created": created, "skipped": skipped, "period_label": period, "truncated": listed["truncated"]}
