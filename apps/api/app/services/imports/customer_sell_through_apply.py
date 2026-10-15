"""Apply resolved customer sell-through staging lines to fact_customer_sellthrough."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine

_T = "fact_customer_sellthrough"


def _figure_update(fig: str) -> Any:
    """A figure is replaced only when the incoming row carries it (N-0111)."""
    return text(f"CASE WHEN EXCLUDED.figure_import_jobs ? '{fig}' THEN EXCLUDED.{fig} ELSE {_T}.{fig} END")


# Rows stored before N-0111 have an empty map: units and each non-empty stock figure came from
# import_job_id. The upsert spells that out before laying the incoming map over it.
_STORED_FIGURE_JOBS = (
    f"COALESCE(NULLIF({_T}.figure_import_jobs, '{{}}'::jsonb), jsonb_strip_nulls(jsonb_build_object("
    f"'units_sold', {_T}.import_job_id, "
    f"'reported_soh', CASE WHEN {_T}.reported_soh IS NOT NULL THEN {_T}.import_job_id END, "
    f"'in_transit_units', CASE WHEN {_T}.in_transit_units IS NOT NULL THEN {_T}.import_job_id END, "
    f"'on_order_units', CASE WHEN {_T}.on_order_units IS NOT NULL THEN {_T}.import_job_id END)))"
)

# Conflict-update column set (one statement per chunk). N-0111: units sold, on-hand, in-transit
# and on-order are each replaced only when the incoming row carries them, so a stock-only load
# never wipes sales and a sales-only load never wipes stock. Prices keep the stored value when
# the incoming row has none.
_CONFLICT_SET = {
    "units_sold": _figure_update("units_sold"),
    "raw_mtd_units": text(f"COALESCE(EXCLUDED.raw_mtd_units, {_T}.raw_mtd_units)"),
    "is_mtd_estimate": text(
        f"CASE WHEN EXCLUDED.figure_import_jobs ? 'units_sold' THEN EXCLUDED.is_mtd_estimate ELSE {_T}.is_mtd_estimate END"
    ),
    "unit_sell_price": text(f"COALESCE(EXCLUDED.unit_sell_price, {_T}.unit_sell_price)"),
    "unit_cost": text(f"COALESCE(EXCLUDED.unit_cost, {_T}.unit_cost)"),
    "unit_mac": text(f"COALESCE(EXCLUDED.unit_mac, {_T}.unit_mac)"),
    "reported_soh": _figure_update("reported_soh"),
    "figure_import_jobs": text(f"{_STORED_FIGURE_JOBS} || EXCLUDED.figure_import_jobs"),
    "period_grain": text("EXCLUDED.period_grain"),
    "period_week": text("EXCLUDED.period_week"),
    "period_year": text("EXCLUDED.period_year"),
    "week_start_date": text("EXCLUDED.week_start_date"),
    "in_transit_units": _figure_update("in_transit_units"),
    "on_order_units": _figure_update("on_order_units"),
    "site_label": text("EXCLUDED.site_label"),
    "vat_basis": text("EXCLUDED.vat_basis"),
    "import_job_id": text("EXCLUDED.import_job_id"),
    "raw_source_row": text("EXCLUDED.raw_source_row"),
    "tenant_id": text("EXCLUDED.tenant_id"),
    "updated_at": text("EXCLUDED.updated_at"),
}

_APPLY_CHUNK_SIZE = 500

# Flows summed over differing source rows of one key (D-0091).
_SUMMED_FIELDS = ("units_sold", "raw_mtd_units")
# Stock snapshots: a value every differing row repeats is one snapshot and is kept once (a week
# split over two months repeats the week's on-hand on each line); values that differ are separate
# holdings and are summed.
_STOCK_FIELDS = ("reported_soh", "in_transit_units", "on_order_units")


def _source_identity(line: ImportCustomerSellthroughStagingLine) -> str:
    """Every source column of a row (``_`` keys are CIP's own notes), plus what was parsed from it."""
    payload = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else {}
    source = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    parsed = [getattr(line, k, None) for k in ("raw_period_ref", "units_sold", "reported_soh", "period_start_date")]
    return hashlib.sha256(json.dumps([source, parsed], sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _merge_into(group: dict[str, Any], values: dict[str, Any]) -> None:
    """Add a differing source row of the same key to its group (D-0091)."""
    merged = group["values"]
    for key in _SUMMED_FIELDS:
        if values.get(key) is not None:
            merged[key] = (float(merged[key]) if merged.get(key) is not None else 0.0) + float(values[key])
    merged["is_mtd_estimate"] = bool(merged.get("is_mtd_estimate")) or bool(values.get("is_mtd_estimate"))
    for key in _STOCK_FIELDS:
        group["stock"][key].append(values.get(key))
        seen = [float(v) for v in group["stock"][key] if v is not None]
        if not seen:
            merged[key] = None
        elif len(set(seen)) == 1:
            merged[key] = seen[0]
        else:
            merged[key] = sum(seen)
    # Prices and the source payload: the later row's, as before.
    for key in ("unit_sell_price", "unit_cost", "unit_mac", "raw_source_row"):
        if values.get(key) is not None:
            merged[key] = values[key]

logger = logging.getLogger(__name__)


@dataclass
class ApplySummary:
    applied: int = 0
    skipped_unresolved: int = 0
    errors: list[str] = field(default_factory=list)
    # N-0110 (D-0090): older rows for the same customer, product and period moved aside because
    # this newer load restated them.
    superseded_rows: int = 0
    superseded_units: float = 0.0
    # N-0110 (D-0091): extra copies of a source row identical in every source column.
    duplicate_lines: int = 0
    # N-0111: figures superseded on their own (rows that kept their other figures, and how many
    # figures of each kind were superseded, same key or not).
    superseded_partial_rows: int = 0
    superseded_figures: dict[str, int] = field(default_factory=dict)


def apply_customer_sellthrough_staging(
    db: Session,
    job_id: int,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = _APPLY_CHUNK_SIZE,
    recompute_stock_gap: bool = True,
) -> ApplySummary:
    """Upsert fact rows for staging lines that are resolved and not yet applied.

    Batched: lines are grouped by ``source_key`` and upserted in chunked multi-row
    ``INSERT … ON CONFLICT DO UPDATE`` statements rather than one round-trip per row. The conflict
    target/columns are unchanged. Dedup-by-source_key within a chunk is required: Postgres rejects an
    ``ON CONFLICT DO UPDATE`` that touches the same key twice in one statement.
    ``on_progress(current, total)`` reports per chunk (optional). ``recompute_stock_gap`` (N-0110)
    refreshes the expected stock position for the customers and products this load touched.

    Source rows sharing one key (N-0110, D-0091): rows that differ are separate lines and their
    units are summed; a row identical in every source column to one already counted is kept once
    and its copies are marked ``apply_status = "duplicate"`` (see ``_merge_into``).

    A newer load supersedes the figures it carries in older rows for the same customer, product
    and period, whatever their site or day grain (N-0110 D-0090, N-0111; see
    ``customer_sell_through_supersede``). A figure the source line leaves empty is not carried.

    N-0111: a job whose files carry week numbers without a year applies nothing until the
    uploader confirms the year.
    """
    from app.models.ingestion import ImportJob
    from app.services.imports.customer_sell_through import (
        YEAR_PENDING_APPLY_MESSAGE,
        customer_sellthrough_source_key,
        job_year_pending,
    )
    from app.services.imports.customer_sell_through_supersede import (
        carried_figures,
        record_same_key_replacements,
    )

    summary = ApplySummary()
    tbl = FactCustomerSellthrough.__table__
    job = db.get(ImportJob, int(job_id))
    tid = (getattr(job, "tenant_id", None) or "default").strip() or "default" if job else "default"
    if job is not None and job_year_pending(job):
        summary.errors.append(YEAR_PENDING_APPLY_MESSAGE)
        return summary

    lines = list(
        db.scalars(
            select(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job_id)
            .where(ImportCustomerSellthroughStagingLine.resolution_status == "resolved")
            .where(ImportCustomerSellthroughStagingLine.apply_status.is_(None))
        ).all()
    )

    summary.skipped_unresolved = int(
        db.scalar(
            select(func.count())
            .select_from(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job_id)
            .where(ImportCustomerSellthroughStagingLine.resolution_status != "resolved")
        )
        or 0
    )

    now = datetime.now(timezone.utc)

    # Group by source_key (D-0091): differing lines are summed, identical copies count once. Every
    # line in the group is remembered so it is marked and pointed at the resulting fact id.
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        if (
            line.resolved_customer_id is None
            or line.resolved_product_id is None
            or line.period_start_date is None
            or (line.units_sold is None and all(getattr(line, k, None) is None for k in _STOCK_FIELDS))
        ):
            summary.skipped_unresolved += 1
            continue
        cust_id = int(line.resolved_customer_id)
        prod_id = int(line.resolved_product_id)
        loc_id = int(line.resolved_location_id) if line.resolved_location_id is not None else None
        period = line.period_start_date
        # site_label: prefer explicit staging column; fall back to raw location token (verbatim).
        site_label = getattr(line, "site_label", None)
        if site_label is None and line.raw_location_token:
            site_label = str(line.raw_location_token).strip() or None
        sk = customer_sellthrough_source_key(
            customer_id=cust_id,
            customer_location_id=loc_id,
            product_id=prod_id,
            period_start_date=period,
            site_label=site_label,
        )
        values = {
            "source_key": sk,
            "customer_id": cust_id,
            "customer_location_id": loc_id,
            "product_id": prod_id,
            "period_start_date": period,
            "period_type": line.period_type or "weekly",
            "units_sold": float(line.units_sold) if line.units_sold is not None else None,
            "raw_mtd_units": line.raw_mtd_units,
            "is_mtd_estimate": bool(line.is_mtd_estimate),
            "unit_sell_price": line.unit_sell_price,
            "unit_cost": line.unit_cost,
            "unit_mac": getattr(line, "unit_mac", None),
            "reported_soh": line.reported_soh,
            "period_grain": getattr(line, "period_grain", None),
            "period_week": getattr(line, "period_week", None),
            "period_year": getattr(line, "period_year", None),
            "week_start_date": getattr(line, "week_start_date", None),
            "in_transit_units": getattr(line, "in_transit_units", None),
            "on_order_units": getattr(line, "on_order_units", None),
            "site_label": site_label,
            "vat_basis": getattr(line, "vat_basis", None) or "ex_vat",
            "import_job_id": job_id,
            "raw_source_row": line.raw_row_payload,
            "tenant_id": tid,
            "updated_at": now,
        }
        ident = _source_identity(line)
        if sk in grouped:
            group = grouped[sk]
            if ident in group["idents"]:
                group["duplicates"].append(line)
            else:
                group["idents"].add(ident)
                _merge_into(group, values)
                group["lines"].append(line)
        else:
            grouped[sk] = {
                "values": values,
                "lines": [line],
                "duplicates": [],
                "idents": {ident},
                "stock": {k: [values[k]] for k in _STOCK_FIELDS},
            }
            order.append(sk)

    def _row_for_insert(values: dict[str, Any]) -> dict[str, Any]:
        # N-0111: the figures this row carries, and which load set them. Units not carried are
        # stored as 0 (the column is required) and are not marked as set by this load.
        row = dict(values)
        row["figure_import_jobs"] = {f: int(job_id) for f in carried_figures(values)}
        if row["units_sold"] is None:
            row["units_sold"] = 0.0
        return row

    total = len(order)
    written_keys: set[str] = set()
    for start in range(0, total, chunk_size):
        chunk_sks = order[start : start + chunk_size]
        rows = [_row_for_insert(grouped[sk]["values"]) for sk in chunk_sks]
        try:
            # The kept copies of replaced figures and the upsert land together or not at all.
            with db.begin_nested():
                kept = record_same_key_replacements(
                    db, job_id=int(job_id), incoming={sk: grouped[sk]["values"] for sk in chunk_sks}
                )
                stmt = (
                    pg_insert(tbl)
                    .values(rows)
                    .on_conflict_do_update(
                        constraint="uq_fact_customer_sellthrough_source_key",
                        set_=_CONFLICT_SET,
                    )
                    .returning(tbl.c.id, tbl.c.source_key)
                )
                returned = db.execute(stmt).all()
            summary.superseded_partial_rows += kept.partial_rows
            for fig, n in kept.figures.items():
                summary.superseded_figures[fig] = summary.superseded_figures.get(fig, 0) + n
            id_by_sk = {r.source_key: int(r.id) for r in returned}
            written_keys.update(id_by_sk)
            for sk in chunk_sks:
                fid = id_by_sk.get(sk)
                for line in grouped[sk]["lines"]:
                    line.apply_status = "applied"
                    if fid is not None:
                        line.fact_sellthrough_row_id = fid
                    db.add(line)
                    summary.applied += 1
                for line in grouped[sk]["duplicates"]:
                    line.apply_status = "duplicate"
                    if fid is not None:
                        line.fact_sellthrough_row_id = fid
                    db.add(line)
                    summary.duplicate_lines += 1
        except Exception as exc:  # noqa: BLE001
            for sk in chunk_sks:
                for line in grouped[sk]["lines"]:
                    summary.errors.append(f"line {line.id}: {exc}")
        if on_progress is not None:
            on_progress(min(start + chunk_size, total), total)

    # N-0110: recompute the expected stock position for what this load touched.
    # A failure is logged and recorded on the summary; it never undoes the load.
    touched: dict[int, set[int]] = {}
    for sk in order:
        vals = grouped[sk]["values"]
        touched.setdefault(int(vals["customer_id"]), set()).add(int(vals["product_id"]))

    # N-0110 (D-0090): this newer load supersedes older rows for the same customer, product and
    # period stored under other keys. Skipped when any chunk failed, so a partial load never moves
    # old rows aside.
    if touched and written_keys and not summary.errors:
        from app.services.imports.customer_sell_through_supersede import supersede_restated_rows

        restated = [grouped[sk]["values"] for sk in order]
        try:
            with db.begin_nested():
                moved = supersede_restated_rows(
                    db, job_id=int(job_id), tenant_id=tid, written_keys=written_keys, restated=restated
                )
            summary.superseded_rows = moved.rows
            summary.superseded_units = moved.units
            summary.superseded_partial_rows += moved.partial_rows
            for fig, n in moved.figures.items():
                summary.superseded_figures[fig] = summary.superseded_figures.get(fig, 0) + n
        except Exception as exc:  # noqa: BLE001
            logger.warning("customer sell-through supersede failed job_id=%s: %s", job_id, exc)
            summary.errors.append(f"supersede of re-uploaded rows: {exc}")
    if recompute_stock_gap and touched and summary.applied:
        from app.services.channel_intelligence.customer_stock_gap import recompute_customer_stock_positions

        for cust_id, product_ids in touched.items():
            try:
                with db.begin_nested():
                    recompute_customer_stock_positions(
                        db, tenant_id=tid, customer_id=cust_id, product_ids=sorted(product_ids)
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("customer stock gap recompute failed customer_id=%s: %s", cust_id, exc)
                summary.errors.append(f"stock gap recompute customer {cust_id}: {exc}")

    return summary
