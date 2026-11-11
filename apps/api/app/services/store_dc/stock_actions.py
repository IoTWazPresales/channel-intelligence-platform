"""Turn a slow or unsold line into a draft promotion, a move, or a return.

Viewing the board does not write. An explicit action does. Move and return are
stock actions: they are excluded from support comparisons and are not claims.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer
from app.services.cpor.promo_plan_builder import (
    _positive_srp,
    create_case_from_promo_draft,
    load_promotion_line_evidence,
)
from app.services.cpor.promotion_type_vocab import CPOR_PROMOTION_TYPE_SET
from app.services.store_dc.read_model import build_customer_view
from app.services.store_dc.rules import SUGGESTIONS, stock_action_covers_site, stock_action_in_notes

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


def _blank_site(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _block_customer(block: dict[str, Any]) -> int | None:
    raw = block.get("customer_id")
    return None if raw is None else int(raw)


def _owns_block(block: dict[str, Any], customer_id: int) -> bool:
    owner = _block_customer(block)
    return owner is None or owner == int(customer_id)


def _scope_key(block: dict[str, Any], customer_id: int) -> tuple[int, str | None]:
    owner = _block_customer(block)
    return (int(customer_id) if owner is None else owner, _blank_site(block.get("site_label")))


def _blocks(view: dict[str, Any], *, customer_id: int) -> list[dict[str, Any]]:
    """Account, this customer's stores, and this customer's confirmed DC.

    A confirmed DC publishes ``stores`` and ``need_from_distributor``. Stores
    already listed for this customer are not counted again. Another customer's
    hub is not this customer's stock. A section shaped as ``sites`` or ``lines``
    is not a DC payload.
    """
    blocks: list[dict[str, Any]] = []
    account = view.get("account")
    if isinstance(account, dict):
        blocks.append(account)
    blocks.extend(block for block in (view.get("sites") or []) if isinstance(block, dict))
    seen = {_scope_key(block, customer_id) for block in blocks}
    for section in view.get("dc_sections") or []:
        if not isinstance(section, dict):
            continue
        for store in section.get("stores") or []:
            if not isinstance(store, dict) or not _owns_block(store, customer_id):
                continue
            key = _scope_key(store, customer_id)
            if key in seen:
                continue
            seen.add(key)
            blocks.append(store)
        owner = section.get("customer_id")
        if owner is None or int(owner) != int(customer_id):
            continue
        needs = [item for item in (section.get("need_from_distributor") or []) if isinstance(item, dict)]
        if not needs:
            continue
        label = section.get("site_label")
        key = (int(customer_id), _blank_site(label))
        if key in seen:
            continue
        seen.add(key)
        blocks.append({"site_label": label, "customer_id": int(customer_id), "lines": needs})
    return blocks


def _suggestion_rows(view: dict[str, Any], *, customer_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, str | None]] = set()
    for block in _blocks(view, customer_id=customer_id):
        site = _blank_site(block.get("site_label"))
        for line in block.get("lines") or []:
            if not isinstance(line, dict) or not line.get("suggestions"):
                continue
            product_id = line.get("product_id")
            if product_id is None:
                continue
            key = (int(product_id), site)
            if key in seen:
                continue
            seen.add(key)
            rows.append({**line, "site_label": site, "customer_id": int(customer_id)})
    return rows


def _customer_ids(session: Session, *, tenant_id: str, customer_id: int | None) -> list[int]:
    if customer_id is not None:
        return [int(customer_id)]
    return [
        int(row)
        for row in session.scalars(
            select(DimCustomer.id).where(
                DimCustomer.tenant_id == tenant_id,
                DimCustomer.merged_into_customer_id.is_(None),
                DimCustomer.customer_status == "active",
            )
        ).all()
    ]


def _collect_aged_stock(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None = None,
    limit: int | None = MAX_LISTED_LINES,
) -> tuple[list[dict[str, Any]], bool]:
    """Slow and unsold lines. ``limit`` None reads every customer; the display uses the cap."""
    customer_ids = _customer_ids(session, tenant_id=tenant_id, customer_id=customer_id)
    lines: list[dict[str, Any]] = []
    truncated = False
    for index, cid in enumerate(customer_ids):
        try:
            view = build_customer_view(session, tenant_id, cid)
        except LookupError:
            continue
        rows = _suggestion_rows(view, customer_id=cid)
        if limit is None:
            lines.extend(rows)
            continue
        room = limit - len(lines)
        if len(rows) > room:
            lines.extend(rows[:room])
            truncated = True
            break
        lines.extend(rows)
        if len(lines) >= limit and index < len(customer_ids) - 1:
            truncated = True
            break
    return lines, truncated


def list_aged_stock(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None = None,
) -> dict[str, Any]:
    """Slow and unsold lines for the board. This read does not create a case."""
    lines, truncated = _collect_aged_stock(
        session,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=MAX_LISTED_LINES,
    )
    return {"lines": lines, "truncated": truncated}


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
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .where(
            CommercialLineupLine.product_id == int(product_id),
            CommercialLineupLine.customer_id == int(customer_id),
            CommercialLineupLine.msrp_local.is_not(None),
            CommercialLineupCase.superseded_by_case_id.is_(None),
            CommercialLineupCase.commercial_status.notin_(("cancelled", "superseded")),
        )
        .order_by(CommercialLineupLine.id.desc())
        .limit(1)
    ).scalar()
    return _positive_srp(listing_price, float(msrp) if msrp is not None else None)


def _row_evidence(row: Any) -> dict | None:
    """A two-column result has no site list and stays unscoped. A dict may name sites."""
    if len(row) < 3:
        return None
    evidence = row[2]
    return evidence if isinstance(evidence, dict) else None


def _open_case_id(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_id: int,
    action: str,
    site_label: str | None = None,
) -> int | None:
    rows = session.execute(
        select(CporCase.id, CporCase.notes, CporCaseLine.cost_evidence_json)
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(
            CporCase.tenant_id == tenant_id,
            CporCase.customer_id == int(customer_id),
            CporCaseLine.product_id == int(product_id),
            CporCase.status.in_(OPEN_CASE_STATUSES),
        )
    ).all()
    wanted = _blank_site(site_label)
    for row in rows:
        if stock_action_in_notes(row[1]) != action:
            continue
        if stock_action_covers_site(_row_evidence(row), wanted):
            return int(row[0])
    return None


def _matching_line(
    rows: list[dict[str, Any]],
    *,
    product_id: int,
    site_label: str | None,
) -> dict[str, Any] | None:
    matches = [row for row in rows if int(row["product_id"]) == int(product_id)]
    if site_label is not None and str(site_label).strip():
        wanted = _blank_site(site_label)
        matches = [row for row in matches if _blank_site(row.get("site_label")) == wanted]
        return matches[0] if matches else None
    unlabeled = [row for row in matches if _blank_site(row.get("site_label")) is None]
    if unlabeled:
        return unlabeled[0]
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
    acted_site = _blank_site(line.get("site_label"))
    existing = _open_case_id(
        session,
        tenant_id=tenant_id,
        customer_id=int(customer_id),
        product_id=int(product_id),
        action=action,
        site_label=acted_site,
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
                "site_labels": [acted_site],
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
        site = _blank_site(row.get("site_label"))
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
            site_label=site,
        ) is not None:
            skipped.append({"customer_id": customer_id, "product_id": product_id, "reason": "already_open"})
            continue
        current = by_product.get(product_id)
        if current is None:
            by_product[product_id] = {"product_id": product_id, "estimate_qty": float(soh), "site_labels": [site]}
        else:
            current["estimate_qty"] = float(current["estimate_qty"]) + float(soh)
            if site not in current["site_labels"]:
                current["site_labels"].append(site)
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
                "site_labels": list(spec["site_labels"]),
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
    """Raise one draft promotion per customer from slow or unsold stock.

    The board list stops at 200 rows. This read does not: a later product or
    customer must still be proposed.
    """
    period = period_label or current_period_label()
    lines, _truncated = _collect_aged_stock(
        session,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=None,
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in lines:
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
    return {"created": created, "skipped": skipped, "period_label": period, "truncated": False}
