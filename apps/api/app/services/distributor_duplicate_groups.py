"""Read-only potential-duplicate distributor groups keyed by similarity-normalised name."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.models.commercial_planner import CommercialDistributorTerm, CommercialPlanLine
from app.models.dimensions import DistributorContact, DistributorLocation, DimDistributor
from app.models.facts import FactInboundShipment
from app.models.import_distributor_si import DistributorSourceTokenAlias, ImportDistributorSiStagingLine
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_PROVISIONAL_CODE_PREFIX = "TMP-DIST-"


@dataclass(frozen=True)
class _DistributorRow:
    id: int
    code: str
    name: str
    distributor_status: str
    created_at: datetime | None


def is_verified_for_survivor_hint(distributor_status: str | None, code: str | None = None) -> bool:
    if (code or "").startswith(_PROVISIONAL_CODE_PREFIX):
        return False
    return (distributor_status or "").strip().lower() not in ("unverified", "needs_review", "merged")


def survivor_hint_sort_key(row: _DistributorRow) -> tuple[int, float, int]:
    verified_rank = 0 if is_verified_for_survivor_hint(row.distributor_status, row.code) else 1
    created_ts = row.created_at.timestamp() if row.created_at is not None else float("inf")
    return (verified_rank, created_ts, row.id)


def build_duplicate_groups(rows: list[_DistributorRow]) -> list[dict[str, Any]]:
    buckets: dict[str, list[_DistributorRow]] = defaultdict(list)
    for row in rows:
        key = normalize_customer_name_for_similarity(row.name)
        if not key:
            continue
        buckets[key].append(row)

    groups: list[dict[str, Any]] = []
    for similarity_key, members in buckets.items():
        if len(members) < 2:
            continue
        sorted_members = sorted(members, key=survivor_hint_sort_key)
        groups.append(
            {
                "similarity_key": similarity_key,
                "member_count": len(sorted_members),
                "members": sorted_members,
            }
        )
    groups.sort(key=lambda g: (-int(g["member_count"]), str(g["similarity_key"])))
    return groups


def paginate_groups(groups: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total = len(groups)
    if total == 0:
        return [], 0
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return groups[start:end], total


def _fk_reference_subqueries(distributor_ids: list[int]) -> list:
    from app.models.fact_customer_velocity import FactCustomerVelocity
    from app.models.facts import (
        FactBuyPlan,
        FactInventoryDistributor,
        FactInventoryReconciliation,
        FactReturns,
        FactSalesSellin,
        FactSalesSellout,
    )
    from app.models.fact_dsi_forecast import FactDsiForecast
    from app.models.historical_lineup import HistoricalLineupImportHeader
    from app.models.shipment_evidence import ShipmentEvidenceLine
    from app.services.distributor_usage import _extra_distributor_subqueries

    specs = [
        ("Sell-in", FactSalesSellin.distributor_id),
        ("Sell-out", FactSalesSellout.distributor_id),
        ("Returns", FactReturns.distributor_id),
        ("Distributor inventory", FactInventoryDistributor.distributor_id),
        ("Inventory reconciliation", FactInventoryReconciliation.distributor_id),
        ("Inbound shipments", FactInboundShipment.distributor_id),
        ("Buy plans", FactBuyPlan.distributor_id),
        ("DSI forecasts", FactDsiForecast.distributor_id),
        ("Customer velocity", FactCustomerVelocity.distributor_id),
        ("Commercial distributor terms", CommercialDistributorTerm.distributor_id),
        ("Commercial plan lines", CommercialPlanLine.distributor_id),
        ("Commercial lineup lines", CommercialLineupLine.distributor_id),
        ("Historical lineup headers", HistoricalLineupImportHeader.distributor_id),
        ("Shipment evidence (resolved distributor)", ShipmentEvidenceLine.distributor_id),
        ("DSI import staging (resolved distributor)", ImportDistributorSiStagingLine.resolved_distributor_id),
        ("Distributor source token aliases", DistributorSourceTokenAlias.distributor_id),
    ]
    subqueries = [count_subquery_for_columns(label, [col], distributor_ids) for label, col in specs]
    subqueries.extend(
        [
            count_subquery_for_columns("Distributor locations", [DistributorLocation.distributor_id], distributor_ids),
            count_subquery_for_columns("Distributor contacts", [DistributorContact.distributor_id], distributor_ids),
        ]
    )
    subqueries.extend(_extra_distributor_subqueries(distributor_ids))
    return subqueries


async def distributor_fk_reference_counts_batch(
    db: AsyncSession, distributor_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in distributor_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    return await batch_counts_multi_table(db, _fk_reference_subqueries(ids), ids)


def _member_to_api(row: _DistributorRow, *, survivor_hint: bool, reference_counts: list[dict[str, int | str]]) -> dict:
    return {
        "id": row.id,
        "distributor_code": row.code,
        "distributor_name": row.name,
        "distributor_status": row.distributor_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "survivor_hint": survivor_hint,
        "reference_counts": sorted(reference_counts, key=lambda r: str(r.get("label", ""))),
    }


async def list_distributor_duplicate_groups(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(
                DimDistributor.id,
                DimDistributor.code,
                DimDistributor.name,
                DimDistributor.distributor_status,
                DimDistributor.created_at,
            )
            .where(DimDistributor.merged_into_distributor_id.is_(None))
            .order_by(DimDistributor.id.asc())
        )
    ).all()

    distributors = [
        _DistributorRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            distributor_status=str(getattr(r, "distributor_status", None) or "active"),
            created_at=r.created_at,
        )
        for r in rows
    ]

    all_groups = build_duplicate_groups(distributors)
    page_groups, total = paginate_groups(all_groups, page, page_size)

    member_ids: list[int] = []
    for group in page_groups:
        for member in group["members"]:
            member_ids.append(member.id)

    ref_counts = await distributor_fk_reference_counts_batch(db, member_ids)

    items: list[dict[str, Any]] = []
    for group in page_groups:
        members_out: list[dict[str, Any]] = []
        for idx, member in enumerate(group["members"]):
            members_out.append(
                _member_to_api(
                    member,
                    survivor_hint=idx == 0,
                    reference_counts=ref_counts.get(member.id, []),
                )
            )
        items.append(
            {
                "similarity_key": group["similarity_key"],
                "member_count": group["member_count"],
                "members": members_out,
            }
        )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "distributors_scanned": len(distributors),
    }
