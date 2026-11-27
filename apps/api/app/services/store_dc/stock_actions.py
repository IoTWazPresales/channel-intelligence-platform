"""Turn a slow or unsold line into a draft promotion, a move, or a return.

Viewing the board does not write. An explicit action does. Move and return are
stock actions: they are excluded from support comparisons and are not claims.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.store_dc import SiteCandidate
from app.services.cpor import planner_sellthrough
from app.services.cpor.customer_soh_check import customer_soh_check
from app.services.cpor.promo_plan_builder import create_case_from_promo_draft
from app.services.cpor.promotion_type_vocab import stock_promote_type
from app.services.store_dc.read_model import build_customer_view, build_lead_index
from app.services.store_dc.rules import (
    SUGGESTIONS,
    norm_label,
    stock_action_covers_site,
    stock_action_identity,
)

OPEN_CASE_STATUSES = ("draft", "proposed", "approved", "active")
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


def _scope_key(block: dict[str, Any], customer_id: int) -> tuple[int, str]:
    """Owner and site, with the site compared as the read model compares it (``norm_label``).

    Final wave (c): a store listed under the customer's sites and again under a confirmed DC
    with different case or spacing ("North Mall" / "north  mall") is one site, not two lines.
    """
    owner = _block_customer(block)
    site = norm_label(_blank_site(block.get("site_label")))
    return (int(customer_id) if owner is None else owner, site)


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
        needs = [
            item for item in (section.get("need_from_distributor") or []) if isinstance(item, dict)
        ]
        if not needs:
            continue
        label = section.get("site_label")
        key = (int(customer_id), norm_label(_blank_site(label)))
        if key in seen:
            continue
        seen.add(key)
        blocks.append({"site_label": label, "customer_id": int(customer_id), "lines": needs})
    return blocks


def _suggestion_rows(view: dict[str, Any], *, customer_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    # Every row belongs to the viewed customer (_blocks drops other owners). Name only: no code.
    customer_name = view.get("customer_name")
    for block in _blocks(view, customer_id=customer_id):
        site = _blank_site(block.get("site_label"))
        for line in block.get("lines") or []:
            if not isinstance(line, dict) or not line.get("suggestions"):
                continue
            product_id = line.get("product_id")
            if product_id is None:
                continue
            key = (int(product_id), norm_label(site))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    **line,
                    "site_label": site,
                    "customer_id": int(customer_id),
                    "customer_name": customer_name,
                }
            )
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


def _with_stock_evidence(session: Session, *, tenant_id: str, customer_ids: list[int]) -> list[int]:
    """Keep customers that can have a slow or unsold line, in the same order.

    A customer view lists a line only from stock that customer reported itself,
    or from a confirmed distribution centre it owns. A customer with neither
    has no suggestion, so it needs no view.
    """
    if not customer_ids:
        return []
    reporting = set(
        session.scalars(
            select(FactCustomerSellthrough.customer_id)
            .where(
                FactCustomerSellthrough.tenant_id == tenant_id,
                FactCustomerSellthrough.customer_id.in_(customer_ids),
                FactCustomerSellthrough.reported_soh.is_not(None),
            )
            .distinct()
        ).all()
    )
    owners = set(
        session.scalars(
            select(SiteCandidate.customer_id)
            .where(
                SiteCandidate.tenant_id == tenant_id,
                SiteCandidate.status == "confirmed",
                SiteCandidate.customer_id.is_not(None),
            )
            .distinct()
        ).all()
    )
    keep = {int(c) for c in reporting} | {int(c) for c in owners}
    return [cid for cid in customer_ids if cid in keep]


def _collect_aged_stock(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None = None,
    limit: int | None = MAX_LISTED_LINES,
) -> tuple[list[dict[str, Any]], bool]:
    """Slow and unsold lines. ``limit`` None reads every customer; the display uses the cap.

    A scan of every customer reads only those with stock evidence, and builds the
    tenant-wide lead index once for all of them. A named customer is always viewed.
    """
    customer_ids = _customer_ids(session, tenant_id=tenant_id, customer_id=customer_id)
    if customer_id is None:
        customer_ids = _with_stock_evidence(session, tenant_id=tenant_id, customer_ids=customer_ids)
    lead_index = build_lead_index(session, tenant_id) if customer_ids else None
    lines: list[dict[str, Any]] = []
    truncated = False
    for index, cid in enumerate(customer_ids):
        try:
            view = build_customer_view(session, tenant_id, cid, lead_index=lead_index)
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


# Money value of aged stock (Warren 2026-11-19, BACKLOG-254). Computed here, never on the client.
# Cost source: the customer's reported unit MAC, else unit cost, ex-VAT (incl-VAT divided by 1 + tenant VAT rate; a
# cost with an unknown VAT basis is left out), SOH-weighted over the customer's latest reported
# stock period for the product. This is the CST cost that the customer SOH check and the CPOR
# tier-1 cost suggestion already use (`customer_soh_check` -> `soh_unit_cost`). It is not a price
# and not a PM cost.
AGED_COST_BASIS = "customer_reported_unit_mac_else_unit_cost_ex_vat"

UnitCostLookup = Callable[[int, int], "tuple[str | None, float | None]"]


def _unit_cost_lookup(session: Session, *, tenant_id: str, as_of: date) -> UnitCostLookup:
    """``(customer_id, product_id) -> (cost field, ex-VAT unit cost)``, or ``(None, None)``."""

    def lookup(customer_id: int, product_id: int) -> tuple[str | None, float | None]:
        found = customer_soh_check(
            session,
            customer_id=int(customer_id),
            product_id=int(product_id),
            as_of=as_of,
            tenant_id=tenant_id,
        )
        cost = found.get("soh_unit_cost") if found.get("status") == "available" else None
        if cost is None:
            return None, None
        return found.get("cost_field"), float(cost)

    return lookup


def value_aged_lines(lines: list[dict[str, Any]], lookup: UnitCostLookup) -> list[dict[str, Any]]:
    """Add ``unit_cost``, ``unit_cost_field`` and ``stock_value`` to each line.

    A line with no cost, or with no reported stock, gets ``None``: never zero. One lookup per
    customer and product.
    """
    cache: dict[tuple[int, int], tuple[str | None, float | None]] = {}
    out: list[dict[str, Any]] = []
    for line in lines:
        cid, pid = line.get("customer_id"), line.get("product_id")
        field_used: str | None = None
        unit_cost: float | None = None
        if cid is not None and pid is not None:
            key = (int(cid), int(pid))
            if key not in cache:
                cache[key] = lookup(*key)
            field_used, unit_cost = cache[key]
        soh = line.get("stock_on_hand")
        value = None if unit_cost is None or soh is None else round(float(soh) * unit_cost, 2)
        out.append(
            {**line, "unit_cost": unit_cost, "unit_cost_field": field_used, "stock_value": value}
        )
    return out


def _is_unplanned(line: dict[str, Any]) -> bool:
    return not line.get("suggestion_executed") and not (line.get("executed_actions") or [])


def _value_block(lines: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [ln for ln in lines if ln.get("stock_value") is not None]
    unpriced = [ln for ln in lines if ln.get("stock_value") is None]
    return {
        "lines": len(lines),
        "units": round(sum(float(ln.get("stock_on_hand") or 0) for ln in lines), 2),
        "value": round(sum(float(ln["stock_value"]) for ln in priced), 2) if priced else None,
        "lines_with_cost": len(priced),
        "lines_without_cost": len(unpriced),
        "units_without_cost": round(sum(float(ln.get("stock_on_hand") or 0) for ln in unpriced), 2),
    }


def summarise_aged_value(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals for the listed lines: ``unplanned`` (no executed action) and ``all``.

    ``value`` covers only lines that have a cost; the lines and units without one are counted
    separately so the figure is never read as a complete valuation.
    """
    return {
        "cost_basis": AGED_COST_BASIS,
        "unplanned": _value_block([ln for ln in lines if _is_unplanned(ln)]),
        "all": _value_block(lines),
    }


def list_aged_stock(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None = None,
    with_value: bool = False,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Slow and unsold lines for the board. This read does not create a case.

    ``with_value`` adds a money value per line and a ``valuation`` summary (``AGED_COST_BASIS``).
    The summary covers the listed lines only; ``truncated`` says whether the list was capped.
    """
    lines, truncated = _collect_aged_stock(
        session,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=MAX_LISTED_LINES,
    )
    out: dict[str, Any] = {"lines": lines, "truncated": truncated}
    if with_value:
        lookup = _unit_cost_lookup(session, tenant_id=tenant_id, as_of=as_of or date.today())
        out["lines"] = value_aged_lines(lines, lookup)
        out["valuation"] = summarise_aged_value(out["lines"])
    return out


def _srp_for_line(
    session: Session, *, customer_id: int, product_id: int, tenant_id: str
) -> float | None:
    """Promotion price for aged-stock Promote: the customer's own sell-through ``unit_sell_price``.

    The latest reported week with a positive price for this customer and product. Warren
    2026-11-19: the planner uses customer sell-through only, so the earlier rule (shopper
    listing price, else line-up shelf price) is gone, and so are competitor prices and earlier
    cases. With no sell-through price this returns ``None`` and the caller keeps its
    ``no_positive_srp`` outcome: no draft is created.
    """
    book = planner_sellthrough.read_book(
        session,
        tenant_id=tenant_id,
        customer_id=int(customer_id),
        product_ids=[int(product_id)],
        want=("price",),
    )
    # Opus R-04: the VAT-inclusive SRP (ex-VAT grossed up by the tenant rate), never the raw price.
    srp = book.figures(int(product_id)).get("srp")
    return float(srp) if srp is not None else None


def _row_evidence(row: Any) -> dict | None:
    """A two-column result has no site list and stays unscoped. A dict may name sites."""
    if len(row) < 3:
        return None
    evidence = row[2]
    return evidence if isinstance(evidence, dict) else None


def _retired_stock_action_clauses():
    """A superseded case or a voided line is not an open stock action."""
    return (
        CporCase.superseded_by_case_id.is_(None),
        or_(
            CporCaseLine.remark.is_(None),
            and_(
                CporCaseLine.remark.notlike("%[voided]%"),
                CporCaseLine.remark.notlike("%[split into layers]%"),
            ),
        ),
    )


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
            *_retired_stock_action_clauses(),
        )
    ).all()
    wanted = _blank_site(site_label)
    for row in rows:
        if stock_action_identity(_row_evidence(row), row[1]) != action:
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


def _lock_stock_action_create(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_id: int,
    action: str,
    site_label: str | None,
) -> None:
    """One transaction may create this customer, product, site, and action.

    The lock lasts until the transaction commits, which is after the draft
    insert. The next request then sees that draft as already open.
    """
    if not isinstance(session, Session):
        return
    key = "\x1f".join(
        (
            str(tenant_id),
            str(int(customer_id)),
            str(int(product_id)),
            str(action),
            norm_label(site_label),
        )
    )
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key), hashtext('cip.stock_action.create'))"),
        {"key": key},
    )


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
    promote_type = stock_promote_type(tenant_id)
    if not promote_type:
        raise ValueError("stock_promotion_type_missing")
    view = build_customer_view(session, tenant_id, int(customer_id))
    line = _matching_line(
        _suggestion_rows(view, customer_id=int(customer_id)),
        product_id=product_id,
        site_label=site_label,
    )
    if line is None:
        raise ValueError("line_not_slow_or_unsold")
    soh = line.get("stock_on_hand")
    if soh is None or float(soh) <= 0:
        raise ValueError("no_stock_to_act_on")
    acted_site = _blank_site(line.get("site_label"))
    _lock_stock_action_create(
        session,
        tenant_id=tenant_id,
        customer_id=int(customer_id),
        product_id=int(product_id),
        action=action,
        site_label=acted_site,
    )
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
    srp = _srp_for_line(
        session, customer_id=int(customer_id), product_id=int(product_id), tenant_id=tenant_id
    )
    if srp is None:
        raise ValueError("no_positive_srp")
    period = period_label or current_period_label()
    logistics = action != "promote"
    created = create_case_from_promo_draft(
        session,
        customer_id=int(customer_id),
        promotion_type=promote_type,
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
    eligible: list[tuple[int, str | None, float]] = []
    for row in rows:
        product_id = int(row["product_id"])
        site = _blank_site(row.get("site_label"))
        soh = row.get("stock_on_hand")
        if soh is None or float(soh) <= 0:
            skipped.append(
                {
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "reason": "no_stock_to_act_on",
                }
            )
            continue
        eligible.append((product_id, site, float(soh)))
    for product_id, site, _soh in sorted(eligible, key=lambda item: (item[0], norm_label(item[1]))):
        _lock_stock_action_create(
            session,
            tenant_id=tenant_id,
            customer_id=customer_id,
            product_id=product_id,
            action="promote",
            site_label=site,
        )
    for product_id, site, soh in eligible:
        if (
            _open_case_id(
                session,
                tenant_id=tenant_id,
                customer_id=customer_id,
                product_id=product_id,
                action="promote",
                site_label=site,
            )
            is not None
        ):
            skipped.append(
                {"customer_id": customer_id, "product_id": product_id, "reason": "already_open"}
            )
            continue
        current = by_product.get(product_id)
        if current is None:
            by_product[product_id] = {
                "product_id": product_id,
                "estimate_qty": float(soh),
                "site_labels": [site],
            }
        else:
            current["estimate_qty"] = float(current["estimate_qty"]) + float(soh)
            if site not in current["site_labels"]:
                current["site_labels"].append(site)
    ready: list[dict[str, Any]] = []
    for product_id, spec in by_product.items():
        srp = _srp_for_line(
            session, customer_id=customer_id, product_id=product_id, tenant_id=tenant_id
        )
        if srp is None:
            skipped.append(
                {"customer_id": customer_id, "product_id": product_id, "reason": "no_positive_srp"}
            )
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
    promote_type = stock_promote_type(tenant_id)
    if not promote_type:
        raise ValueError("stock_promotion_type_missing")
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
        specs = _merged_promote_lines(
            session, tenant_id=tenant_id, customer_id=cid, rows=rows, skipped=skipped
        )
        if not specs:
            continue
        for spec in specs:
            spec["pod_quarter"] = period
        try:
            case = create_case_from_promo_draft(
                session,
                customer_id=cid,
                promotion_type=promote_type,
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
