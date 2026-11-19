"""Per-customer timeline: our CPOR promotions beside the customer's own calendar, with clashes.

Our promotions are the existing CPOR case windows. A case is left out when it is superseded,
cancelled, a test/fixture case (``intelligence_exclude``), or every one of its lines is voided: the
same open/closed rules the portfolio and pivot reads already use. Calendar events are the customer's
uploaded campaign / pillar events. Clashes come from ``compute_clashes``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cpor import CporCase, CporCaseLine
from app.models.customer_calendar import CustomerCalendarEvent
from app.models.dimensions import DimCustomer
from app.services.cpor.customer_calendar.clashes import compute_clashes
from app.services.cpor.customer_calendar.scope import bind_calendar_tenant
from app.services.cpor.intelligence_scope import where_commercial_intelligence
from app.services.cpor.pivot import is_voided_line

# Case statuses that are closed for planning purposes (lifecycle.py: cancelled is terminal and
# carries zero payable). A superseded case is excluded by superseded_by_case_id.
EXCLUDED_CASE_STATUSES = ("cancelled", "voided", "superseded")


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _voided_case_ids(db: Session, case_ids: list[int]) -> set[int]:
    """Cases that have lines and all of them voided."""
    if not case_ids:
        return set()
    lines = db.scalars(
        select(CporCaseLine)
        .options(load_only(CporCaseLine.case_id, CporCaseLine.remark, CporCaseLine.estimate_qty))
        .where(CporCaseLine.case_id.in_(case_ids))
    ).all()
    total: dict[int, int] = defaultdict(int)
    voided: dict[int, int] = defaultdict(int)
    for line in lines:
        cid = int(line.case_id)
        total[cid] += 1
        if is_voided_line(line):
            voided[cid] += 1
    return {cid for cid, n in total.items() if n > 0 and voided[cid] == n}


def open_case_windows(
    db: Session,
    tenant_id: str,
    *,
    customer_id: int | None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Open case windows; ``customer_id`` None reads every customer of the tenant."""
    stmt = select(CporCase).where(
        CporCase.tenant_id == tenant_id,
        CporCase.superseded_by_case_id.is_(None),
        CporCase.status.notin_(EXCLUDED_CASE_STATUSES),
        where_commercial_intelligence(),
    )
    if customer_id is not None:
        stmt = stmt.where(CporCase.customer_id == int(customer_id))
    if date_from is not None:
        stmt = stmt.where(CporCase.window_end >= date_from)
    if date_to is not None:
        stmt = stmt.where(CporCase.window_start <= date_to)
    cases = list(db.scalars(stmt.order_by(CporCase.window_start, CporCase.id)).all())
    voided = _voided_case_ids(db, [int(c.id) for c in cases])
    return [
        {
            "case_id": int(c.id),
            "case_code": c.case_code,
            "case_name": c.case_name,
            "promotion_type": c.promotion_type,
            "status": c.status,
            "customer_id": int(c.customer_id),
            "window_start": c.window_start,
            "window_end": c.window_end,
        }
        for c in cases
        if int(c.id) not in voided
    ]


def calendar_events(
    db: Session,
    tenant_id: str,
    *,
    customer_id: int | None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Calendar events; ``customer_id`` None reads every customer of the tenant."""
    stmt = select(CustomerCalendarEvent).where(CustomerCalendarEvent.tenant_id == tenant_id)
    if customer_id is not None:
        stmt = stmt.where(CustomerCalendarEvent.customer_id == int(customer_id))
    if date_from is not None:
        stmt = stmt.where(CustomerCalendarEvent.end_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(CustomerCalendarEvent.start_date <= date_to)
    rows = db.scalars(
        stmt.order_by(CustomerCalendarEvent.start_date, CustomerCalendarEvent.id)
    ).all()
    return [
        {
            "id": int(r.id),
            "customer_id": int(r.customer_id),
            "name": r.name,
            "kind": r.kind,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "source_file": r.source_file,
            "upload_id": r.upload_id,
        }
        for r in rows
    ]


def build_timeline(
    db: Session,
    tenant_id: str,
    *,
    customer_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any] | None:
    """The timeline payload for one customer, or None when the customer is not in the tenant."""
    bind_calendar_tenant(db, tenant_id)
    from app.core.my_accounts import apply_account_predicate

    customer = db.scalar(
        apply_account_predicate(
            select(DimCustomer).where(
                DimCustomer.tenant_id == tenant_id, DimCustomer.id == int(customer_id)
            ),
            DimCustomer.id,
        )
    )
    if customer is None:
        return None
    promos = open_case_windows(
        db, tenant_id, customer_id=customer_id, date_from=date_from, date_to=date_to
    )
    events = calendar_events(
        db, tenant_id, customer_id=customer_id, date_from=date_from, date_to=date_to
    )
    clashes = compute_clashes(promos, events)
    return {
        "customer": {"id": int(customer.id), "name": customer.name},
        "from": _iso(date_from),
        "to": _iso(date_to),
        "promotions": [
            {**p, "window_start": _iso(p["window_start"]), "window_end": _iso(p["window_end"])}
            for p in promos
        ],
        "calendar_events": [
            {**e, "start_date": _iso(e["start_date"]), "end_date": _iso(e["end_date"])}
            for e in events
        ],
        "clashes": [
            {
                "case_id": c["case_id"],
                "case_code": c["promotion"].get("case_code"),
                "case_name": c["promotion"].get("case_name"),
                "event_id": c["event_id"],
                "event_name": c["event"].get("name"),
                "event_kind": c["event"].get("kind"),
                "overlap_start": _iso(c["overlap_start"]),
                "overlap_end": _iso(c["overlap_end"]),
                "overlap_days": c["overlap_days"],
            }
            for c in clashes
        ],
    }


def build_clash_summary(
    db: Session,
    tenant_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Exact tenant-wide clash counts for the planner card (same windows, events, maths as above).

    Customers outside the caller's account scope never count, as in the per-customer timeline.
    ``clash_count`` is promotion/event pairs; ``promotion_count`` and ``customer_count`` are the
    distinct promotions and customers involved.
    """
    bind_calendar_tenant(db, tenant_id)
    from app.core.my_accounts import apply_account_predicate

    allowed = {
        int(cid)
        for cid in db.scalars(
            apply_account_predicate(
                select(DimCustomer.id).where(DimCustomer.tenant_id == tenant_id),
                DimCustomer.id,
            )
        ).all()
    }
    promos = [
        p
        for p in open_case_windows(
            db, tenant_id, customer_id=None, date_from=date_from, date_to=date_to
        )
        if int(p["customer_id"]) in allowed
    ]
    events = [
        e
        for e in calendar_events(
            db, tenant_id, customer_id=None, date_from=date_from, date_to=date_to
        )
        if int(e["customer_id"]) in allowed
    ]
    clashes = compute_clashes(promos, events)
    return {
        "from": _iso(date_from),
        "to": _iso(date_to),
        "clash_count": len(clashes),
        "promotion_count": len({c["case_id"] for c in clashes}),
        "customer_count": len({c["customer_id"] for c in clashes}),
    }
