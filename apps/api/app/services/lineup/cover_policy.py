"""Per-customer target cover weeks (D-045).

Resolver: commercial_customer_term.target_cover_weeks → tenant default
(REPLENISHMENT_WOC_THRESHOLD_WEEKS). Query/body override is explicit and flags
cover_override. No hard-coded customer ids.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commercial_planner import CommercialCustomerTerm
from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS

COVER_SOURCE_CUSTOMER_TERM = "customer_term"
COVER_SOURCE_TENANT_DEFAULT = "tenant_default"
COVER_SOURCE_OVERRIDE = "override"
COVER_SOURCE_MIXED = "mixed"

TENANT_DEFAULT_COVER_WEEKS = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)


def weeks_from_term(term: CommercialCustomerTerm | None) -> tuple[float, str]:
    """(weeks, source) for one customer term row. Missing/null → tenant default."""
    if term is not None:
        raw = getattr(term, "target_cover_weeks", None)
        if raw is not None:
            return float(raw), COVER_SOURCE_CUSTOMER_TERM
    return TENANT_DEFAULT_COVER_WEEKS, COVER_SOURCE_TENANT_DEFAULT


def resolve_target_cover_weeks_sync(
    session: Session,
    customer_id: int,
    *,
    override_weeks: float | None = None,
) -> tuple[float, str]:
    """Sync resolver for CPOR/cost paths. override_weeks wins with source=override."""
    if override_weeks is not None:
        return float(override_weeks), COVER_SOURCE_OVERRIDE
    row = session.scalar(
        select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == int(customer_id))
    )
    return weeks_from_term(row)


def share_weighted_cover_weeks(
    shares: list[dict[str, Any]],
    weeks_by_customer: dict[int, tuple[float, str]],
    *,
    fallback_weeks: float,
    fallback_source: str,
) -> tuple[float, str]:
    """Share-weighted weeks for a dist×product row. Empty shares → fallback."""
    if not shares:
        return float(fallback_weeks), fallback_source
    weighted = 0.0
    share_sum = 0.0
    sources: set[str] = set()
    for part in shares:
        share = float(part.get("share") or 0.0)
        if share <= 0:
            continue
        cid = int(part["customer_id"])
        weeks, src = weeks_by_customer.get(cid, (fallback_weeks, fallback_source))
        weighted += share * float(weeks)
        share_sum += share
        sources.add(src)
    if share_sum <= 0:
        return float(fallback_weeks), fallback_source
    weeks_out = weighted / share_sum
    if len(sources) == 1:
        return weeks_out, next(iter(sources))
    return weeks_out, COVER_SOURCE_MIXED


async def load_cover_weeks_by_customer(
    db: AsyncSession,
    customer_ids: Iterable[int],
    *,
    override_weeks: float | None = None,
) -> dict[int, tuple[float, str]]:
    """Batch resolve cover weeks. override_weeks applies to every id."""
    ids = {int(cid) for cid in customer_ids}
    if override_weeks is not None:
        ov = float(override_weeks)
        return {cid: (ov, COVER_SOURCE_OVERRIDE) for cid in ids}
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id.in_(ids))
        )
    ).scalars().all()
    by_id = {int(r.customer_id): r for r in rows}
    return {cid: weeks_from_term(by_id.get(cid)) for cid in ids}
