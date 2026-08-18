"""Build the shipping digest from the applied inbound job vs last usable report."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.shipping.newly_landed import (
    import_jobs_unusable_date_snapshots,
    latest_inbound_shipment_job_id,
    newly_landed_transitions,
)
from app.services.shipping.observation_transitions import (
    attach_fact_line_columns,
    compute_eta_shifts,
    identity_scope_for_job,
    _iso,
    _merge_line_columns,
    _qty,
)
from app.services.shipping_digest.recipients_store import resolve_shipping_recipients

SECTION_ARRIVING = "arriving_week"
SECTION_ARRIVING_NEXT = "arriving_next_week"
SECTION_NEWLY_LANDED = "newly_landed"
SECTION_ETA_CHANGES = "eta_changes"


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _iso_week_bounds(d: date) -> tuple[date, date]:
    mon = d - timedelta(days=d.weekday())
    return mon, mon + timedelta(days=6)


def _line_row(*, distributor: str, customer: str, date_value: str | None, sales_model: str | None, qty: float | None) -> dict[str, Any]:
    return {
        "distributor": distributor,
        "customer": customer,
        "date": date_value,
        "sales_model": sales_model,
        "qty": qty,
    }


def section_dims(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinct disti / customer / model counts plus summed qty for a digest section."""
    distis = {str(r.get("distributor") or "").strip() for r in rows}
    distis.discard("")
    distis.discard("—")
    customers = {str(r.get("customer") or "").strip() for r in rows}
    customers.discard("")
    customers.discard("—")
    models = {str(r.get("sales_model") or "").strip() for r in rows}
    models.discard("")
    qty = 0.0
    for r in rows:
        q = r.get("qty")
        if q is None:
            continue
        try:
            qty += float(q)
        except (TypeError, ValueError):
            continue
    return {
        "rows": len(rows),
        "distis": len(distis),
        "customers": len(customers),
        "models": len(models),
        "qty": qty,
    }


def group_line_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse invoice-line grain to disti × customer × date × sales_model, summing qty."""
    totals: dict[tuple[str, str, str | None, str | None], float] = {}
    order: list[tuple[str, str, str | None, str | None]] = []
    for row in rows:
        key = (
            str(row.get("distributor") or "—"),
            str(row.get("customer") or "—"),
            row.get("date"),
            row.get("sales_model"),
        )
        qty = row.get("qty")
        add = float(qty) if qty is not None else 0.0
        if key not in totals:
            totals[key] = 0.0
            order.append(key)
        totals[key] += add
    grouped = [
        _line_row(
            distributor=key[0],
            customer=key[1],
            date_value=key[2],
            sales_model=key[3],
            qty=totals[key],
        )
        for key in order
    ]
    grouped.sort(key=_row_sort_key)
    return grouped


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("distributor") or "").casefold(),
        str(row.get("customer") or "").casefold(),
        str(row.get("date") or ""),
        str(row.get("sales_model") or "").casefold(),
    )


def rows_by_distributor(rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Sort disti then customer, then split into one block per distributor."""
    blocks: list[tuple[str, list[dict[str, Any]]]] = []
    current: str | None = None
    bucket: list[dict[str, Any]] = []
    for row in sorted(rows, key=_row_sort_key):
        dist = str(row.get("distributor") or "—")
        if current is None:
            current = dist
        if dist != current:
            blocks.append((current, bucket))
            current = dist
            bucket = []
        bucket.append(row)
    if current is not None:
        blocks.append((current, bucket))
    return blocks


async def _job_unpod_eta_in_range(
    db: AsyncSession,
    *,
    import_job_id: int,
    week_start: date,
    week_end: date,
) -> list[dict[str, Any]]:
    """Open lines on this job whose Est POD (else Promise) falls in the ISO week."""
    eff = func.coalesce(ShipmentEvidenceObservation.est_pod_date, ShipmentEvidenceObservation.promise_date)
    stmt = (
        select(
            ShipmentEvidenceObservation.source_key,
            ShipmentEvidenceObservation.sales_model_name,
            ShipmentEvidenceObservation.quantity,
            ShipmentEvidenceObservation.bill_to_raw,
            ShipmentEvidenceObservation.customer_dealer_token,
            eff.label("eta"),
        )
        .where(
            ShipmentEvidenceObservation.import_job_id == int(import_job_id),
            ShipmentEvidenceObservation.pod_date.is_(None),
            eff.is_not(None),
            eff >= week_start,
            eff <= week_end,
        )
        .order_by(eff.asc(), ShipmentEvidenceObservation.source_key.asc())
    )
    raw = (await db.execute(stmt)).mappings().all()
    fact_cols = await attach_fact_line_columns(
        db, [str(r["source_key"]) for r in raw if r.get("source_key")]
    )
    rows: list[dict[str, Any]] = []
    for r in raw:
        item: dict[str, Any] = {}
        _merge_line_columns(
            item,
            fact_cols=fact_cols,
            source_key=str(r.get("source_key") or ""),
            date_value=r.get("eta"),
            fallback_sales_model=r.get("sales_model_name"),
            fallback_qty=r.get("quantity"),
            fallback_customer_token=r.get("customer_dealer_token"),
            fallback_bill_to=r.get("bill_to_raw"),
        )
        rows.append(
            _line_row(
                distributor=str(item.get("distributor") or "—"),
                customer=str(item.get("customer") or "—"),
                date_value=_iso(r.get("eta")),
                sales_model=item.get("sales_model") or r.get("sales_model_name"),
                qty=item.get("qty") if item.get("qty") is not None else _qty(r.get("quantity")),
            )
        )
    return rows


async def _eta_change_rows(db: AsyncSession, *, import_job_id: int) -> tuple[list[dict[str, Any]], list[int]]:
    evid_ids, identity_keys = identity_scope_for_job(import_job_id)
    skip = [
        jid
        for jid in await import_jobs_unusable_date_snapshots(db, identity_keys)
        if jid != int(import_job_id)
    ]
    payload = await compute_eta_shifts(
        db,
        evid_ids=evid_ids,
        identity_keys=identity_keys,
        sample_limit=0,
        require_current_incoming=False,
        cap_samples=False,
        include_line_columns=True,
        exclude_import_job_ids=skip,
        open_only=True,
    )
    rows: list[dict[str, Any]] = []
    for s in payload.get("samples") or []:
        prev_s = s.get("previous_effective")
        cur_s = s.get("date") or s.get("current_effective")
        date_s = f"{prev_s} → {cur_s}" if prev_s and cur_s else cur_s
        rows.append(
            _line_row(
                distributor=str(s.get("distributor") or "—"),
                customer=str(s.get("customer") or "—"),
                date_value=date_s,
                sales_model=s.get("sales_model"),
                qty=s.get("qty"),
            )
        )
    return rows, skip


async def build_shipping_digest(
    db: AsyncSession,
    *,
    tenant_id: str = "default",
    import_job_id: int | None = None,
) -> dict[str, Any]:
    today = _utc_today()
    this_w0, this_w1 = _iso_week_bounds(today)
    next_w0, next_w1 = _iso_week_bounds(today + timedelta(days=7))
    source_job_id = int(import_job_id) if import_job_id is not None else await latest_inbound_shipment_job_id(db)
    if source_job_id is None:
        arriving: list[dict[str, Any]] = []
        arriving_next: list[dict[str, Any]] = []
        newly_rows: list[dict[str, Any]] = []
        eta_rows: list[dict[str, Any]] = []
        skip_ids: list[int] = []
        newly: dict[str, Any] = {}
    else:
        arriving = group_line_rows(
            await _job_unpod_eta_in_range(
                db, import_job_id=source_job_id, week_start=this_w0, week_end=this_w1
            )
        )
        arriving_next = group_line_rows(
            await _job_unpod_eta_in_range(
                db, import_job_id=source_job_id, week_start=next_w0, week_end=next_w1
            )
        )
        newly = await newly_landed_transitions(
            db,
            import_job_id=source_job_id,
            with_line_columns=True,
            today=today,
        )
        newly_rows = group_line_rows(
            [
                _line_row(
                    distributor=str(r.get("distributor") or "—"),
                    customer=str(r.get("customer") or "—"),
                    date_value=r.get("date") or r.get("current_pod"),
                    sales_model=r.get("sales_model"),
                    qty=r.get("qty"),
                )
                for r in newly.get("rows") or []
            ]
        )
        eta_raw, skip_ids = await _eta_change_rows(db, import_job_id=source_job_id)
        eta_rows = group_line_rows(eta_raw)
    sections = [
        {
            "id": SECTION_ARRIVING,
            "title": "Stock with ETA this week (not yet POD'd)",
            "rows": arriving,
        },
        {
            "id": SECTION_ARRIVING_NEXT,
            "title": "Stock with ETA next week (not yet POD'd)",
            "rows": arriving_next,
        },
        {
            "id": SECTION_NEWLY_LANDED,
            "title": "Stock POD'd that was not POD'd on the last report",
            "rows": newly_rows,
        },
        {
            "id": SECTION_ETA_CHANGES,
            "title": "ETA changes vs last usable report (still open)",
            "rows": eta_rows,
        },
    ]
    return {
        "title": "Shipping digest",
        "data_vintage": {
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "source_job_id": source_job_id,
            "reference_date": today.isoformat(),
            "this_week": f"{this_w0.isoformat()}…{this_w1.isoformat()}",
            "next_week": f"{next_w0.isoformat()}…{next_w1.isoformat()}",
            "skipped_unusable_job_ids": skip_ids,
            "html_preview": True,
            "section_counts": {s["id"]: len(s["rows"]) for s in sections},
            "section_dims": {s["id"]: section_dims(s["rows"]) for s in sections},
        },
        "intended_recipients": list(await resolve_shipping_recipients(db, tenant_id)),
        "sections": sections,
    }
