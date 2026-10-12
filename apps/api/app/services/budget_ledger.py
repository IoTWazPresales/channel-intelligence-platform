"""Append-only budget ledger.

Nobody types a pot. A lineup approval reserves the campaign portion. A case
approval commits. Settlement consumes and releases the unused commitment.
Payment is a separate paid row. Draft and cancelled cases are not left as
open commitment. Caps flag and never block.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.budget_ledger import ENTRY_TYPES, BudgetLedgerEntry
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimProduct


def balances_from_amounts(rows: list[tuple[str, float]]) -> dict[str, float]:
    """Sum rows of (entry_type, amount_usd). Remaining is reserve minus what is still drawn."""
    totals = {key: 0.0 for key in ENTRY_TYPES}
    for entry_type, amount in rows:
        if entry_type in totals:
            totals[entry_type] += float(amount or 0)
    commit = totals["commit"] + totals["commit_adjust"]
    open_commit = commit - totals["release"] - totals["consume"]
    if open_commit < 0:
        open_commit = 0.0
    used = totals["consume"] + open_commit
    remaining = totals["reserve"] + totals["transfer"] - used
    return {
        "reserved": round(totals["reserve"], 4),
        "transfer": round(totals["transfer"], 4),
        "committed": round(commit, 4),
        "released": round(totals["release"], 4),
        "consumed": round(totals["consume"], 4),
        "paid": round(totals["paid"], 4),
        "pending_headroom_used": round(used, 4),
        "remaining": round(remaining, 4),
    }


def _money(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), 4)))


def add_entry(session: Session, **fields: Any) -> BudgetLedgerEntry:
    entry_type = str(fields.get("entry_type") or "")
    if entry_type not in ENTRY_TYPES:
        raise ValueError(f"unknown budget entry type {entry_type}")
    row = BudgetLedgerEntry(
        tenant_id=str(fields.get("tenant_id") or "default"),
        entry_type=entry_type,
        product_line=str(fields.get("product_line") or ""),
        customer_id=fields.get("customer_id"),
        product_id=fields.get("product_id"),
        landed_quarter=str(fields.get("landed_quarter") or ""),
        amount_usd=_money(fields.get("amount_usd")),
        amount_local=_money(fields.get("amount_local")),
        fx_rate=_money(fields.get("fx_rate")) if fields.get("fx_rate") is not None else None,
        case_id=fields.get("case_id"),
        case_line_id=fields.get("case_line_id"),
        lineup_item_id=fields.get("lineup_item_id"),
        payment_evidence_id=fields.get("payment_evidence_id"),
        source_event_id=fields.get("source_event_id"),
        actor=fields.get("actor"),
        reverses_entry_id=fields.get("reverses_entry_id"),
        source_tag=fields.get("source_tag"),
    )
    session.add(row)
    session.flush()
    return row


def used_usd(session: Session, *, landed_quarter: str | None = None) -> float | None:
    """Headroom used from the ledger. None when the table is not there yet."""
    stmt = select(BudgetLedgerEntry.entry_type, func.coalesce(func.sum(BudgetLedgerEntry.amount_usd), 0)).group_by(
        BudgetLedgerEntry.entry_type
    )
    if landed_quarter:
        stmt = stmt.where(BudgetLedgerEntry.landed_quarter == landed_quarter)
    nested = session.begin_nested()
    try:
        rows = list(session.execute(stmt).all())
        nested.commit()
    except ProgrammingError:
        nested.rollback()
        return None
    balances = balances_from_amounts([(str(kind), float(amount)) for kind, amount in rows])
    return balances["pending_headroom_used"]


def position_rows(session: Session) -> list[dict[str, Any]]:
    stmt = select(
        BudgetLedgerEntry.product_line,
        BudgetLedgerEntry.landed_quarter,
        BudgetLedgerEntry.entry_type,
        func.coalesce(func.sum(BudgetLedgerEntry.amount_usd), 0),
    ).group_by(
        BudgetLedgerEntry.product_line,
        BudgetLedgerEntry.landed_quarter,
        BudgetLedgerEntry.entry_type,
    )
    grouped: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for product_line, quarter, entry_type, amount in session.execute(stmt).all():
        grouped.setdefault((str(product_line or ""), str(quarter or "")), []).append(
            (str(entry_type), float(amount))
        )
    out = []
    for (product_line, quarter), pairs in sorted(grouped.items()):
        balances = balances_from_amounts(pairs)
        out.append({"product_line": product_line, "landed_quarter": quarter, **balances})
    return out


def _product_line(session: Session, product_id: int | None) -> str:
    if product_id is None:
        return ""
    product = session.get(DimProduct, int(product_id))
    if product is None or not product.product_line:
        return ""
    return str(product.product_line)


def _net_for_line(session: Session, case_line_id: int, entry_types: set[str]) -> tuple[float, int | None]:
    rows = session.execute(
        select(BudgetLedgerEntry.id, BudgetLedgerEntry.entry_type, BudgetLedgerEntry.amount_usd).where(
            BudgetLedgerEntry.case_line_id == int(case_line_id),
            BudgetLedgerEntry.entry_type.in_(tuple(entry_types)),
        )
    ).all()
    total = 0.0
    last_id = None
    for row_id, entry_type, amount in rows:
        sign = 1.0
        total += sign * float(amount or 0)
        last_id = int(row_id)
    return total, last_id


def apply_case_transition(session: Session, case: CporCase, action: str, *, actor: str | None) -> int:
    """Write ledger rows for approve, cancel, and settle. Same session, no commit."""
    lines = list(session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == int(case.id))).all())
    written = 0
    for line in lines:
        product_line = _product_line(session, line.product_id)
        common = {
            "tenant_id": getattr(case, "tenant_id", None) or "default",
            "product_line": product_line,
            "customer_id": case.customer_id,
            "product_id": line.product_id,
            "landed_quarter": line.pod_quarter or "",
            "case_id": case.id,
            "case_line_id": line.id,
            "actor": actor,
            "fx_rate": float(case.roe_snapshot) if getattr(case, "roe_snapshot", None) is not None else None,
        }
        if action == "approve":
            amount = float(line.ttl_support_usd or 0)
            if amount == 0:
                continue
            add_entry(session, entry_type="commit", amount_usd=amount, source_event_id=f"approve:{case.id}", **common)
            written += 1
        elif action == "cancel":
            committed, last_id = _net_for_line(session, int(line.id), {"commit", "commit_adjust"})
            released, _ = _net_for_line(session, int(line.id), {"release"})
            consumed, _ = _net_for_line(session, int(line.id), {"consume"})
            open_amount = committed - released - consumed
            if open_amount <= 0:
                continue
            add_entry(
                session,
                entry_type="release",
                amount_usd=open_amount,
                source_event_id=f"cancel:{case.id}",
                reverses_entry_id=last_id,
                **common,
            )
            written += 1
        elif action == "settle":
            committed, last_id = _net_for_line(session, int(line.id), {"commit", "commit_adjust"})
            released, _ = _net_for_line(session, int(line.id), {"release"})
            consumed, _ = _net_for_line(session, int(line.id), {"consume"})
            result = float(line.ttl_result_usd or 0)
            already = consumed
            consume_delta = result - already
            if consume_delta > 0:
                add_entry(
                    session,
                    entry_type="consume",
                    amount_usd=consume_delta,
                    source_event_id=f"settle:{case.id}",
                    **common,
                )
                written += 1
            open_amount = committed - released - max(result, already)
            if open_amount > 0:
                add_entry(
                    session,
                    entry_type="release",
                    amount_usd=open_amount,
                    source_event_id=f"settle-release:{case.id}",
                    reverses_entry_id=last_id,
                    **common,
                )
                written += 1
    return written


def load_historical_settled(session: Session, *, actor: str = "historical_import") -> dict[str, int]:
    """Consume rows for settled cases. Skips a line that already has one."""
    existing = set(
        session.execute(
            select(BudgetLedgerEntry.case_line_id).where(
                BudgetLedgerEntry.entry_type == "consume",
                BudgetLedgerEntry.source_tag == "historical_import",
                BudgetLedgerEntry.case_line_id.is_not(None),
            )
        ).scalars().all()
    )
    rows = session.execute(
        select(CporCase, CporCaseLine)
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(CporCase.status == "settled")
    ).all()
    written = 0
    skipped_present = 0
    skipped_no_result = 0
    for case, line in rows:
        if int(line.id) in existing:
            skipped_present += 1
            continue
        if line.ttl_result_usd is None:
            skipped_no_result += 1
            continue
        add_entry(
            session,
            entry_type="consume",
            tenant_id=getattr(case, "tenant_id", None) or "default",
            product_line=_product_line(session, line.product_id),
            customer_id=case.customer_id,
            product_id=line.product_id,
            landed_quarter=line.pod_quarter or "",
            amount_usd=float(line.ttl_result_usd),
            case_id=case.id,
            case_line_id=line.id,
            actor=actor,
            source_event_id=f"historical:{case.id}:{line.id}",
            source_tag="historical_import",
            fx_rate=float(case.roe_snapshot) if getattr(case, "roe_snapshot", None) is not None else None,
        )
        written += 1
    return {
        "written": written,
        "skipped_present": skipped_present,
        "skipped_no_result": skipped_no_result,
    }


def _campaign_reserve_usd(session: Session, item: Any) -> float | None:
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.commercial_planner import CommercialSkuAssumption
    from app.services.lineup.profit_reservation import compute_profit_with_reservation

    sku = session.scalar(
        select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id == int(item.product_id))
    )
    if sku is None:
        return None
    line = session.scalar(
        select(CommercialLineupLine)
        .where(CommercialLineupLine.product_id == int(item.product_id))
        .order_by(CommercialLineupLine.id.desc())
    )
    srp = None
    if line is not None:
        for raw in (line.dap_evidence_local, line.msrp_local):
            if raw is not None and float(raw) > 0:
                srp = float(raw)
                break
    if srp is None:
        return None
    qty = float(item.planned_volume_units or 0)
    if qty <= 0:
        return None
    economics = compute_profit_with_reservation(
        net_requirement_units=qty,
        target_srp_local=srp,
        promo_srp_local=None,
        controlled_cost_amount=float(sku.controlled_cost_amount),
        reserve_total_pct=float(sku.reserve_total_pct),
        promo_reserve_split_pct=float(sku.promo_reserve_split_pct),
        vat_rate_pct=float(sku.vat_rate_pct),
        fx_plan_currency_per_cost_currency=float(sku.fx_plan_currency_per_cost_currency),
    )
    campaign = (economics.get("reservation") or {}).get("campaign_support")
    if campaign is None:
        return None
    return round(float(campaign), 4)


def apply_lineup_approval(session: Session, item: Any, old_status: str | None, new_status: str, *, actor: str | None) -> int:
    """Reserve on approve. Reverse that reserve when approval is taken away."""
    product_line = _product_line(session, item.product_id)
    quarter = item.period_label or ""
    if not quarter and getattr(item, "period_start", None) is not None:
        start = item.period_start
        quarter = f"{start.year}Q{(start.month - 1) // 3 + 1}"
    common = {
        "product_line": product_line,
        "customer_id": item.customer_id,
        "product_id": item.product_id,
        "landed_quarter": quarter,
        "lineup_item_id": item.id,
        "actor": actor,
    }
    existing = session.execute(
        select(BudgetLedgerEntry.id, BudgetLedgerEntry.amount_usd).where(
            BudgetLedgerEntry.lineup_item_id == int(item.id),
            BudgetLedgerEntry.entry_type == "reserve",
        )
    ).all()
    net = sum(float(amount or 0) for _row_id, amount in existing)
    last_id = int(existing[-1][0]) if existing else None
    written = 0
    if new_status == "approved" and (old_status or "") != "approved":
        amount = _campaign_reserve_usd(session, item)
        if amount is None or amount == 0:
            return 0
        if abs(net - amount) < 0.0001:
            return 0
        if net:
            add_entry(
                session,
                entry_type="reserve",
                amount_usd=-net,
                reverses_entry_id=last_id,
                source_event_id=f"lineup-reverse:{item.id}",
                **common,
            )
            written += 1
        add_entry(session, entry_type="reserve", amount_usd=amount, source_event_id=f"lineup-approve:{item.id}", **common)
        return written + 1
    if (old_status or "") == "approved" and new_status != "approved" and net:
        add_entry(
            session,
            entry_type="reserve",
            amount_usd=-net,
            reverses_entry_id=last_id,
            source_event_id=f"lineup-unapprove:{item.id}",
            **common,
        )
        return 1
    return 0


def record_paid_evidence(session: Session, evidence: Any, *, actor: str | None) -> bool:
    """One paid row per payment evidence id. Local amount stays local unless the currency is USD."""
    status = str(getattr(evidence, "payment_status", "") or "").lower()
    if status not in {"paid", "closed"} or getattr(evidence, "case_id", None) is None:
        return False
    already = session.scalar(
        select(BudgetLedgerEntry.id).where(BudgetLedgerEntry.payment_evidence_id == int(evidence.id))
    )
    if already is not None:
        return False
    case = session.get(CporCase, int(evidence.case_id))
    currency = str(getattr(evidence, "currency_code", "") or "").upper()
    amount = float(evidence.amount or 0)
    add_entry(
        session,
        entry_type="paid",
        tenant_id=getattr(evidence, "tenant_id", None) or "default",
        product_line="",
        customer_id=getattr(evidence, "customer_id", None) or (case.customer_id if case is not None else None),
        landed_quarter="",
        amount_usd=amount if currency == "USD" else None,
        amount_local=None if currency == "USD" else amount,
        case_id=evidence.case_id,
        payment_evidence_id=evidence.id,
        actor=actor,
        source_event_id=f"payment:{evidence.id}",
    )
    return True
