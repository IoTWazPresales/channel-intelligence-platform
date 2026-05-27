"""Distributor SOH reconciliation (post-apply background task)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.models.facts import (
    FactInboundShipment,
    FactInventoryDistributor,
    FactInventoryReconciliation,
    FactSalesSellout,
)
from app.services.imports.dsi_fact_source_keys import dsi_reconciliation_source_key

logger = logging.getLogger(__name__)

VARIANCE_THRESHOLD_PCT = Decimal("0.10")


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _reconciliation_status_for_variance(
    calculated: Decimal,
    reported: Decimal | None,
    *,
    base_status: str,
) -> tuple[str, Decimal | None, Decimal | None]:
    if reported is None:
        return base_status if base_status != "clean" else "no_reported_soh", None, None
    variance_units = reported - calculated
    variance_pct: Decimal | None = None
    status = base_status
    if calculated > 0:
        variance_pct = variance_units / calculated
        if abs(variance_pct) > VARIANCE_THRESHOLD_PCT:
            status = "variance_flagged"
        elif status not in ("no_baseline", "no_shipment_data"):
            status = "clean"
    return status, variance_units, variance_pct


def _upsert_reconciliation_row(
    session: Session,
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int | None,
    period_end_date: date,
    snapshot_date: date,
    allocation_type: str,
    calculated_units: Decimal,
    reported_units: Decimal | None,
    variance_units: Decimal | None,
    variance_pct: Decimal | None,
    reconciliation_status: str,
    import_job_id: int,
) -> None:
    source_key = dsi_reconciliation_source_key(
        distributor_id=distributor_id,
        product_id=product_id,
        customer_id=customer_id,
        period_end_date=period_end_date,
    )
    values = {
        "source_key": source_key,
        "distributor_id": int(distributor_id),
        "product_id": int(product_id),
        "customer_id": int(customer_id) if customer_id is not None else None,
        "period_end_date": period_end_date,
        "snapshot_date": snapshot_date,
        "allocation_type": allocation_type,
        "calculated_units": float(calculated_units),
        "reported_units": float(reported_units) if reported_units is not None else None,
        "variance_units": float(variance_units) if variance_units is not None else None,
        "variance_pct": float(variance_pct) if variance_pct is not None else None,
        "reconciliation_status": reconciliation_status,
        "import_job_id": int(import_job_id),
    }
    tbl = FactInventoryReconciliation.__table__
    stmt = pg_insert(tbl).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tbl.c.source_key],
        set_={
            "calculated_units": stmt.excluded.calculated_units,
            "reported_units": stmt.excluded.reported_units,
            "variance_units": stmt.excluded.variance_units,
            "variance_pct": stmt.excluded.variance_pct,
            "reconciliation_status": stmt.excluded.reconciliation_status,
            "import_job_id": stmt.excluded.import_job_id,
            "snapshot_date": stmt.excluded.snapshot_date,
            "allocation_type": stmt.excluded.allocation_type,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    session.execute(stmt)


def _write_customer_and_open_channel_reconciliation(
    session: Session,
    *,
    distributor_id: int,
    period_start: date,
    period_end: date,
    import_job_id: int,
    has_shipment: bool,
) -> int:
    """Write ``fact_inventory_reconciliation`` rows; returns row count upserted."""
    if not _table_exists(session, "fact_inventory_reconciliation"):
        return 0

    dist_id = int(distributor_id)
    inbound_by_pc: dict[tuple[int, int], Decimal] = {}
    q_in_c = (
        select(
            FactInboundShipment.product_id,
            FactInboundShipment.customer_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0),
        )
        .where(
            FactInboundShipment.distributor_id == dist_id,
            FactInboundShipment.product_id.isnot(None),
            FactInboundShipment.customer_id.isnot(None),
            FactInboundShipment.pod_date.isnot(None),
            FactInboundShipment.pod_date >= period_start,
            FactInboundShipment.pod_date <= period_end,
        )
        .group_by(FactInboundShipment.product_id, FactInboundShipment.customer_id)
    )
    for pid, cid, qty in session.execute(q_in_c).all():
        if pid is None or cid is None:
            continue
        inbound_by_pc[(int(pid), int(cid))] = Decimal(str(qty or 0))

    sellout_by_pc: dict[tuple[int, int], Decimal] = {}
    q_so_c = (
        select(
            FactSalesSellout.product_id,
            FactSalesSellout.customer_id,
            func.coalesce(func.sum(FactSalesSellout.units), 0),
        )
        .where(
            FactSalesSellout.distributor_id == dist_id,
            FactSalesSellout.transaction_date >= period_start,
            FactSalesSellout.transaction_date <= period_end,
        )
        .group_by(FactSalesSellout.product_id, FactSalesSellout.customer_id)
    )
    for pid, cid, qty in session.execute(q_so_c).all():
        sellout_by_pc[(int(pid), int(cid))] = Decimal(str(qty or 0))

    keys = set(inbound_by_pc) | set(sellout_by_pc)
    written = 0
    base_status = "no_shipment_data" if not has_shipment else "clean"

    for product_id, customer_id in sorted(keys):
        inbound_u = inbound_by_pc.get((product_id, customer_id), Decimal("0"))
        sellout_u = sellout_by_pc.get((product_id, customer_id), Decimal("0"))
        calculated = inbound_u - sellout_u
        status, var_u, var_pct = _reconciliation_status_for_variance(
            calculated, None, base_status=base_status
        )
        _upsert_reconciliation_row(
            session,
            distributor_id=dist_id,
            product_id=product_id,
            customer_id=customer_id,
            period_end_date=period_end,
            snapshot_date=period_end,
            allocation_type="customer_allocated",
            calculated_units=calculated,
            reported_units=None,
            variance_units=var_u,
            variance_pct=var_pct,
            reconciliation_status=status,
            import_job_id=import_job_id,
        )
        written += 1

    open_channel_id: int | None = session.scalar(
        select(DimCustomer.id).where(func.lower(DimCustomer.code) == "open_channel").limit(1)
    )

    inbound_open_by_product: dict[int, Decimal] = {}
    if has_shipment:
        q_open_in = (
            select(
                FactInboundShipment.product_id,
                func.coalesce(func.sum(FactInboundShipment.quantity), 0),
            )
            .where(
                FactInboundShipment.distributor_id == dist_id,
                FactInboundShipment.product_id.isnot(None),
                FactInboundShipment.customer_id.is_(None),
                FactInboundShipment.pod_date.isnot(None),
                FactInboundShipment.pod_date >= period_start,
                FactInboundShipment.pod_date <= period_end,
            )
            .group_by(FactInboundShipment.product_id)
        )
        for pid, qty in session.execute(q_open_in).all():
            if pid is not None:
                inbound_open_by_product[int(pid)] = Decimal(str(qty or 0))

    sellout_open_by_product: dict[int, Decimal] = {}
    if open_channel_id is not None:
        q_open_so = (
            select(
                FactSalesSellout.product_id,
                func.coalesce(func.sum(FactSalesSellout.units), 0),
            )
            .where(
                FactSalesSellout.distributor_id == dist_id,
                FactSalesSellout.customer_id == int(open_channel_id),
                FactSalesSellout.transaction_date >= period_start,
                FactSalesSellout.transaction_date <= period_end,
            )
            .group_by(FactSalesSellout.product_id)
        )
        for pid, qty in session.execute(q_open_so).all():
            sellout_open_by_product[int(pid)] = Decimal(str(qty or 0))

    open_products = set(inbound_open_by_product) | set(sellout_open_by_product)
    for product_id in sorted(open_products):
        inbound_u = inbound_open_by_product.get(product_id, Decimal("0"))
        sellout_u = sellout_open_by_product.get(product_id, Decimal("0"))
        calculated = inbound_u - sellout_u
        status, var_u, var_pct = _reconciliation_status_for_variance(
            calculated, None, base_status=base_status
        )
        _upsert_reconciliation_row(
            session,
            distributor_id=dist_id,
            product_id=product_id,
            customer_id=None,
            period_end_date=period_end,
            snapshot_date=period_end,
            allocation_type="open_channel",
            calculated_units=calculated,
            reported_units=None,
            variance_units=var_u,
            variance_pct=var_pct,
            reconciliation_status=status,
            import_job_id=import_job_id,
        )
        written += 1

    return written


def reconcile_distributor_soh(
    session: Session,
    distributor_id: int,
    period_end_date: date,
    import_job_id: int,
) -> dict[str, Any]:
    """Reconcile reported distributor SOH vs calculated bridge for each product."""
    dist_id = int(distributor_id)
    period_end = period_end_date

    period_start = session.scalar(
        select(func.min(FactSalesSellout.transaction_date)).where(
            FactSalesSellout.distributor_id == dist_id,
            FactSalesSellout.transaction_date <= period_end,
        )
    )
    if period_start is None:
        period_start = session.scalar(
            select(func.min(FactInventoryDistributor.as_of_date)).where(
                FactInventoryDistributor.distributor_id == dist_id,
                FactInventoryDistributor.as_of_date <= period_end,
            )
        )
    if period_start is None:
        period_start = period_end

    has_shipment = bool(
        session.scalar(
            select(func.count())
            .select_from(FactInboundShipment)
            .where(FactInboundShipment.distributor_id == dist_id)
            .limit(1)
        )
        or 0
    )

    product_ids: set[int] = set()
    for pid in session.scalars(
        select(FactSalesSellout.product_id).where(
            FactSalesSellout.distributor_id == dist_id,
            FactSalesSellout.transaction_date >= period_start,
            FactSalesSellout.transaction_date <= period_end,
        ).distinct()
    ).all():
        product_ids.add(int(pid))
    for pid in session.scalars(
        select(FactInventoryDistributor.product_id).where(
            FactInventoryDistributor.distributor_id == dist_id,
            FactInventoryDistributor.as_of_date == period_end,
        ).distinct()
    ).all():
        product_ids.add(int(pid))

    updated = 0
    statuses: dict[str, int] = {}
    now = datetime.now(timezone.utc)

    for product_id in sorted(product_ids):
        opening_row = session.scalar(
            select(FactInventoryDistributor)
            .where(
                FactInventoryDistributor.distributor_id == dist_id,
                FactInventoryDistributor.product_id == int(product_id),
                FactInventoryDistributor.as_of_date < period_start,
            )
            .order_by(FactInventoryDistributor.as_of_date.desc())
            .limit(1)
        )
        opening_soh = Decimal("0")
        reconciliation_status = "clean"
        if opening_row is None:
            reconciliation_status = "no_baseline"
        else:
            opening_soh = Decimal(str(opening_row.on_hand_units or 0))

        inbound_units = Decimal("0")
        if has_shipment:
            inbound_sum = session.scalar(
                select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                    FactInboundShipment.distributor_id == dist_id,
                    FactInboundShipment.product_id == int(product_id),
                    FactInboundShipment.pod_date.isnot(None),
                    FactInboundShipment.pod_date >= period_start,
                    FactInboundShipment.pod_date <= period_end,
                )
            )
            inbound_units = Decimal(str(inbound_sum or 0))
        else:
            reconciliation_status = "no_shipment_data"

        sell_out_sum = session.scalar(
            select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(
                FactSalesSellout.distributor_id == dist_id,
                FactSalesSellout.product_id == int(product_id),
                FactSalesSellout.transaction_date >= period_start,
                FactSalesSellout.transaction_date <= period_end,
            )
        )
        sell_out_units = Decimal(str(sell_out_sum or 0))

        calculated_soh = opening_soh + inbound_units - sell_out_units

        reported_row = session.scalar(
            select(FactInventoryDistributor).where(
                FactInventoryDistributor.distributor_id == dist_id,
                FactInventoryDistributor.product_id == int(product_id),
                FactInventoryDistributor.as_of_date == period_end,
            )
        )
        reported_soh: Decimal | None = None
        if reported_row is not None:
            reported_soh = Decimal(str(reported_row.on_hand_units or 0))
        else:
            if reconciliation_status == "clean":
                reconciliation_status = "no_reported_soh"
            elif reconciliation_status == "no_shipment_data":
                reconciliation_status = "no_reported_soh"

        variance_units: Decimal | None = None
        variance_pct: Decimal | None = None
        if reported_soh is not None and calculated_soh > 0:
            variance_units = reported_soh - calculated_soh
            variance_pct = variance_units / calculated_soh
            if abs(variance_pct) <= VARIANCE_THRESHOLD_PCT:
                if reconciliation_status not in ("no_baseline", "no_shipment_data"):
                    reconciliation_status = "clean"
            else:
                reconciliation_status = "variance_flagged"
        elif reported_soh is None and reconciliation_status not in (
            "no_baseline",
            "no_shipment_data",
        ):
            reconciliation_status = "no_reported_soh"

        target = reported_row
        if target is None:
            target = session.scalar(
                select(FactInventoryDistributor).where(
                    FactInventoryDistributor.distributor_id == dist_id,
                    FactInventoryDistributor.product_id == int(product_id),
                )
                .order_by(FactInventoryDistributor.as_of_date.desc())
                .limit(1)
            )
        if target is None:
            continue

        target.calculated_soh = float(calculated_soh)
        target.soh_variance = float(variance_units) if variance_units is not None else None
        target.reconciliation_status = reconciliation_status
        target.reconciliation_run_at = now
        session.add(target)
        updated += 1
        statuses[reconciliation_status] = statuses.get(reconciliation_status, 0) + 1

    allocation_rows = _write_customer_and_open_channel_reconciliation(
        session,
        distributor_id=dist_id,
        period_start=period_start,
        period_end=period_end,
        import_job_id=int(import_job_id),
        has_shipment=has_shipment,
    )

    session.flush()
    return {
        "import_job_id": int(import_job_id),
        "distributor_id": dist_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "products_updated": updated,
        "status_counts": statuses,
        "reconciliation_allocation_rows": allocation_rows,
        "customer_allocated_skipped": allocation_rows == 0
        and not _table_exists(session, "fact_inventory_reconciliation"),
    }
