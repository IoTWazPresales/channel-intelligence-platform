"""Candidate queue. Asks once. Does not create a location, customer, distributor, or product."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.dimensions import CustomerLocation, DimCustomer, DimDistributor, DistributorLocation
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment
from app.models.store_dc import DcServedAccount, SiteCandidate, StoreDcTenantConfig
from app.services.store_dc.rules import (
    DEFAULT_LEAD_TIME_MIN_DELIVERIES,
    DEFAULT_STOCK_BEHAVIOUR_MIN_SOH,
    norm_label,
    pattern_matches,
)


def tenant_config(db: Session, tenant_id: str) -> dict[str, Any]:
    row = db.get(StoreDcTenantConfig, tenant_id)
    patterns = list(row.dc_name_patterns) if row and isinstance(row.dc_name_patterns, list) else []
    return {
        "tenant_id": tenant_id,
        "lead_time_min_deliveries": int(row.lead_time_min_deliveries) if row else DEFAULT_LEAD_TIME_MIN_DELIVERIES,
        "dc_name_patterns": [p for p in patterns if isinstance(p, str)],
        "stock_behaviour_min_soh": float(row.stock_behaviour_min_soh) if row else DEFAULT_STOCK_BEHAVIOUR_MIN_SOH,
        "stored": row is not None,
    }


def save_tenant_config(
    db: Session,
    tenant_id: str,
    *,
    lead_time_min_deliveries: int | None = None,
    dc_name_patterns: list[str] | None = None,
    stock_behaviour_min_soh: float | None = None,
) -> dict[str, Any]:
    row = db.get(StoreDcTenantConfig, tenant_id)
    if row is None:
        row = StoreDcTenantConfig(tenant_id=tenant_id)
        db.add(row)
    if lead_time_min_deliveries is not None:
        if not 1 <= int(lead_time_min_deliveries) <= 1000:
            raise ValueError("lead_time_min_deliveries must be from 1 to 1000")
        row.lead_time_min_deliveries = int(lead_time_min_deliveries)
    if stock_behaviour_min_soh is not None:
        if float(stock_behaviour_min_soh) <= 0:
            raise ValueError("stock_behaviour_min_soh must be greater than 0")
        row.stock_behaviour_min_soh = float(stock_behaviour_min_soh)
    if dc_name_patterns is not None:
        import re

        clean: list[str] = []
        for raw in dc_name_patterns:
            text = str(raw).strip()
            if not text:
                continue
            re.compile(text)
            clean.append(text)
        row.dc_name_patterns = clean
    db.flush()
    return tenant_config(db, tenant_id)


def distributor_site_norms(db: Session, tenant_id: str) -> set[str]:
    """Exact labels of distributor locations and distributor identity. Not a substring."""
    norms: set[str] = set()
    locations = db.execute(
        select(DistributorLocation.location_name, DistributorLocation.location_code)
        .join(DimDistributor, DimDistributor.id == DistributorLocation.distributor_id)
        .where(DimDistributor.tenant_id == tenant_id)
    ).all()
    identities = db.execute(
        select(DimDistributor.name, DimDistributor.code).where(DimDistributor.tenant_id == tenant_id)
    ).all()
    for name, code in list(locations) + list(identities):
        for part in (name, code):
            norm = norm_label(part)
            if norm:
                norms.add(norm)
    return norms


def _find_candidate(db: Session, tenant_id: str, customer_id: int | None, label_norm: str) -> SiteCandidate | None:
    stmt = select(SiteCandidate).where(
        SiteCandidate.tenant_id == tenant_id,
        SiteCandidate.site_label_norm == label_norm,
    )
    if customer_id is None:
        stmt = stmt.where(SiteCandidate.customer_id.is_(None))
    else:
        stmt = stmt.where(SiteCandidate.customer_id == customer_id)
    return db.execute(stmt).scalar_one_or_none()


def _remember(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int | None,
    distributor_id: int | None,
    site_label: str,
    evidence_kind: str,
    blocked: set[str],
) -> bool:
    """Insert one open question. A row that already exists is left as the steward left it."""
    label = site_label.strip()
    key = norm_label(label)
    if not key:
        return False
    if _find_candidate(db, tenant_id, customer_id, key) is not None:
        return False
    db.add(
        SiteCandidate(
            tenant_id=tenant_id,
            customer_id=customer_id,
            distributor_id=distributor_id,
            site_label=label,
            site_label_norm=key,
            evidence_kind=evidence_kind,
            status="open",
            evidence={"kind": evidence_kind},
            blocked_as_distributor_site=key in blocked,
        )
    )
    db.flush()
    return True


def refresh_candidates(db: Session, tenant_id: str) -> dict[str, int]:
    """Propose candidates from patterns, stock behaviour, and direct shipments.

    Does not insert a location. A second pass does not open a second question.
    """
    cfg = tenant_config(db, tenant_id)
    blocked = distributor_site_norms(db, tenant_id)
    before = db.execute(
        select(func.count()).select_from(SiteCandidate).where(SiteCandidate.tenant_id == tenant_id)
    ).scalar_one()
    locations_before = db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()

    shipments = db.execute(
        select(
            FactInboundShipment.customer_id,
            FactInboundShipment.resolved_customer_id,
            FactInboundShipment.distributor_id,
            FactInboundShipment.ship_to_raw,
        ).where(
            FactInboundShipment.tenant_id == tenant_id,
            FactInboundShipment.line_state != "closed_superseded",
            FactInboundShipment.ship_to_raw.is_not(None),
            or_(
                FactInboundShipment.customer_id.is_not(None),
                FactInboundShipment.resolved_customer_id.is_not(None),
            ),
        )
    ).all()
    seen_direct: set[tuple[int, str]] = set()
    for customer_id, resolved_customer_id, distributor_id, ship_to in shipments:
        cust = resolved_customer_id or customer_id
        label = (ship_to or "").strip()
        if cust is None or not label:
            continue
        key = (int(cust), norm_label(label))
        if key in seen_direct:
            continue
        seen_direct.add(key)
        kind = "pattern" if pattern_matches(label, cfg["dc_name_patterns"]) else "direct_shipment"
        _remember(
            db,
            tenant_id=tenant_id,
            customer_id=int(cust),
            distributor_id=int(distributor_id) if distributor_id is not None else None,
            site_label=label,
            evidence_kind=kind,
            blocked=blocked,
        )

    site_rows = db.execute(
        select(
            FactCustomerSellthrough.customer_id,
            FactCustomerSellthrough.site_label,
            func.sum(FactCustomerSellthrough.units_sold),
            func.max(FactCustomerSellthrough.reported_soh),
        )
        .where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.site_label.is_not(None),
        )
        .group_by(FactCustomerSellthrough.customer_id, FactCustomerSellthrough.site_label)
    ).all()
    for customer_id, site_label, units, soh in site_rows:
        label = (site_label or "").strip()
        if not label:
            continue
        if pattern_matches(label, cfg["dc_name_patterns"]):
            _remember(
                db,
                tenant_id=tenant_id,
                customer_id=int(customer_id),
                distributor_id=None,
                site_label=label,
                evidence_kind="pattern",
                blocked=blocked,
            )
        soh_value = float(soh or 0)
        if float(units or 0) == 0 and soh_value >= float(cfg["stock_behaviour_min_soh"]):
            _remember(
                db,
                tenant_id=tenant_id,
                customer_id=int(customer_id),
                distributor_id=None,
                site_label=label,
                evidence_kind="stock_behaviour",
                blocked=blocked,
            )

    after = db.execute(
        select(func.count()).select_from(SiteCandidate).where(SiteCandidate.tenant_id == tenant_id)
    ).scalar_one()
    locations_after = db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    return {
        "inserted": int(after) - int(before),
        "open_questions": int(after),
        "locations_created": int(locations_after) - int(locations_before),
    }


def list_candidates(db: Session, tenant_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
    stmt = select(SiteCandidate).where(SiteCandidate.tenant_id == tenant_id).order_by(SiteCandidate.id.asc())
    if status:
        stmt = stmt.where(SiteCandidate.status == status)
    rows = db.execute(stmt).scalars().all()
    names = _customer_names(db, [r.customer_id for r in rows if r.customer_id])
    return [_candidate_payload(r, names.get(r.customer_id)) for r in rows]


def _customer_names(db: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(set(ids)))).all()
    return {int(i): name for i, name in rows}


def _candidate_payload(row: SiteCandidate, customer_name: str | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "customer_id": row.customer_id,
        "customer_name": customer_name,
        "distributor_id": row.distributor_id,
        "location_id": row.location_id,
        "site_label": row.site_label,
        "evidence_kind": row.evidence_kind,
        "status": row.status,
        "blocked_as_distributor_site": bool(row.blocked_as_distributor_site),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_by": row.decided_by,
    }


def decide_candidate(db: Session, tenant_id: str, candidate_id: int, decision: str, actor: str) -> dict[str, Any]:
    row = db.get(SiteCandidate, candidate_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError(str(candidate_id))
    choice = decision.strip().lower()
    if choice not in {"confirm", "reject", "reopen"}:
        raise ValueError("decision must be confirm, reject, or reopen")
    if choice == "confirm":
        blocked = row.blocked_as_distributor_site or row.site_label_norm in distributor_site_norms(db, tenant_id)
        if blocked:
            row.blocked_as_distributor_site = True
            db.flush()
            raise ValueError("A distributor warehouse or business-unit account cannot be confirmed as a customer distribution centre")
        row.status = "confirmed"
    elif choice == "reject":
        row.status = "rejected"
    else:
        row.status = "open"
    row.decided_at = None if choice == "reopen" else datetime.now(timezone.utc)
    row.decided_by = None if choice == "reopen" else actor
    db.flush()
    # Confirm remembers the answer. It does not create a location.
    name = None
    if row.customer_id:
        cust = db.get(DimCustomer, row.customer_id)
        name = cust.name if cust else None
    return _candidate_payload(row, name)


def merge_served_account_ids(
    before: set[int],
    wanted: set[int],
    visible: set[int],
) -> list[int]:
    """Combine the UI selection with links the editor could not see (no checkbox row).

    `visible` is the set of customer IDs that had a checkbox row on save (see ReplenishmentView).
    Any ID in `before` that is not in `visible` is preserved unless removed explicitly — but removal
    is only possible when the ID is visible, so out-of-scope links are never dropped.
    """
    preserve = before - visible
    return sorted(wanted | preserve)


def set_served_accounts(
    db: Session,
    tenant_id: str,
    candidate_id: int,
    customer_ids: list[int],
    *,
    context_customer_id: int | None = None,
    visible_customer_ids: list[int] | None = None,
) -> dict[str, Any]:
    row = db.get(SiteCandidate, candidate_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError(str(candidate_id))
    if row.status != "confirmed":
        raise ValueError("Link accounts only after the site is confirmed as a customer distribution centre")
    if row.blocked_as_distributor_site:
        raise ValueError("A distributor-owned site cannot serve customer accounts as a distribution centre")
    wanted: list[int] = []
    for raw in customer_ids:
        cid = int(raw)
        if cid not in wanted:
            wanted.append(cid)
    wanted_set = set(wanted)

    before = set(served_customer_ids(db, tenant_id, row))
    if context_customer_id is not None:
        ctx = int(context_customer_id)
        if ctx not in before:
            raise ValueError(
                "Saving from this customer context is not allowed until that account is linked to this site, "
                "or open the board for a customer that this distribution centre already serves."
            )
        if not visible_customer_ids:
            raise ValueError(
                "visible_customer_ids is required (non-empty) when context_customer_id is set so the server can preserve "
                "served-account links that are not shown as checkboxes for this board view."
            )
        visible: set[int] = set()
        for raw in visible_customer_ids:
            visible.add(int(raw))
        wanted_set = set(merge_served_account_ids(before, wanted_set, visible))

    wanted = sorted(wanted_set)
    if wanted:
        found = db.execute(
            select(DimCustomer.id).where(DimCustomer.id.in_(wanted), DimCustomer.tenant_id == tenant_id)
        ).scalars().all()
        if set(found) != set(wanted):
            raise LookupError("customer")
    db.query(DcServedAccount).filter(DcServedAccount.candidate_id == row.id).delete(synchronize_session=False)
    for cid in wanted:
        db.add(DcServedAccount(tenant_id=tenant_id, candidate_id=row.id, customer_id=cid))
    db.flush()
    return {"candidate_id": row.id, "customer_ids": wanted}


def served_customer_ids(db: Session, tenant_id: str, candidate: SiteCandidate) -> list[int]:
    ids: list[int] = []
    if candidate.customer_id:
        ids.append(int(candidate.customer_id))
    extra = db.execute(
        select(DcServedAccount.customer_id).where(
            DcServedAccount.tenant_id == tenant_id,
            DcServedAccount.candidate_id == candidate.id,
        )
    ).scalars().all()
    for cid in extra:
        if int(cid) not in ids:
            ids.append(int(cid))
    return ids
