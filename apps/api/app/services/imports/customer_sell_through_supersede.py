"""A newer customer sell-through load supersedes the figures it carries (N-0110 D-0090, N-0111).

An older load can have stored the same sales under other keys: several sites as one chain-level
row (``loc=0``), a week where the newer load has sale days, or another file entirely. Without
this step the old rows stay beside the new ones and units count twice.

Each figure is superseded on its own (N-0111, Warren 2026-10-16): units sold, on-hand,
in-transit and on-order. A stock-only load never wipes sales; a sales-only load never wipes
stock. After a load applies, figure F of an older stored row is superseded when all of these hold:

- the load that set F on that row is older than this load and is not this load;
- this load wrote F for the same customer and product for a period that overlaps the row's
  period (a product this load could not resolve keeps its old figures);
- the row's period lies inside the span this load reports for that customer (a month row is
  not superseded by one week of it);
- this load did not write that row's key itself (same-key restatement is the source_key upsert,
  which keeps the replaced figures through ``record_same_key_replacements``).

Site, day grain and file bytes do not matter. A row that gives up every figure it holds is moved
verbatim (``row_json``) into ``fact_customer_sellthrough_superseded``. A row that gives up some
figures keeps the others; a copy of the row as it was is kept there with ``figures`` naming what
it gave up, and those figures are cleared on the row (units to 0, stock to empty). Raw staging
rows are not touched. Nothing is hard-deleted.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.ingestion import ImportJob
from app.services.imports.parsers.customer_sell_through_grain import period_end

logger = logging.getLogger(__name__)

REASON_RESTATED = "restated_by_newer_load"
# N-0111: some figures of the row were restated by a newer load; the rest stay on the row.
REASON_FIGURES_RESTATED = "figures_restated_by_newer_load"
# N-0111: a newer load wrote a different value for a figure under the same key.
REASON_SAME_KEY = "figure_replaced_same_key"
# A week stored under a year that had not happened when its file was received (N-0110 repair).
REASON_FUTURE_WEEK = "week_not_yet_happened"

# Figures superseded independently (N-0111). Units are a flow; the other three are stock.
FIGURES: tuple[str, ...] = ("units_sold", "reported_soh", "in_transit_units", "on_order_units")


@dataclass
class SupersedeSummary:
    rows: int = 0
    units: float = 0.0
    from_jobs: list[int] = field(default_factory=list)
    product_ids: set[int] = field(default_factory=set)
    # N-0111: rows that kept some figures and gave up others, and how many figures each kind gave up.
    partial_rows: int = 0
    figures: dict[str, int] = field(default_factory=dict)


def _grain(period_grain: str | None, period_type: str | None) -> str:
    from app.services.channel_intelligence.customer_stock_gap import grain_of

    return grain_of(period_grain, period_type)


def _range(values: Any) -> tuple[date, date]:
    get = values.get if isinstance(values, dict) else lambda k: getattr(values, k)
    start = get("period_start_date")
    return start, period_end(start, _grain(get("period_grain"), get("period_type")))


def figure_jobs(row: Any) -> dict[str, int]:
    """Which load set each figure the row holds.

    Rows stored before N-0111 have an empty map: units always came from ``import_job_id``, and
    each stock figure did when it is not empty.
    """
    get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
    raw = get("figure_import_jobs")
    if isinstance(raw, dict) and raw:
        return {str(k): int(v) for k, v in raw.items() if v is not None and str(k) in FIGURES}
    job = get("import_job_id")
    if job is None:
        return {}
    out = {"units_sold": int(job)}
    for f in FIGURES[1:]:
        if get(f) is not None:
            out[f] = int(job)
    return out


def carried_figures(values: dict[str, Any]) -> list[str]:
    """Figures a new fact row carries: the ones the source line gave a value for."""
    return [f for f in FIGURES if values.get(f) is not None]


def _count(summary: SupersedeSummary, figures: Iterable[str]) -> None:
    for f in figures:
        summary.figures[f] = summary.figures.get(f, 0) + 1


def move_to_superseded(
    db: Session,
    fact_ids: Iterable[int],
    *,
    by_job_id: int,
    reason: str,
    figures: dict[int, list[str]] | None = None,
) -> SupersedeSummary:
    """Move stored rows verbatim into ``fact_customer_sellthrough_superseded``.

    ``figures`` names, per fact id, the figures each row gave up (N-0111). It is written with the
    record: the table takes inserts only (no update policy under row security).
    """
    summary = SupersedeSummary()
    ids = sorted({int(i) for i in fact_ids})
    if not ids:
        return summary
    by_figures: dict[tuple[str, ...] | None, list[int]] = defaultdict(list)
    for fid in ids:
        figs = (figures or {}).get(fid)
        by_figures[tuple(figs) if figs else None].append(fid)
    moved: list[Any] = []
    for figs, group in by_figures.items():
        moved.extend(
            db.execute(
                text(
                    """
                    INSERT INTO fact_customer_sellthrough_superseded (
                        fact_id, source_key, tenant_id, customer_id, product_id, period_start_date,
                        units_sold, reported_soh, import_job_id, superseded_by_import_job_id, reason, row_json,
                        figures
                    )
                    SELECT f.id, f.source_key, f.tenant_id, f.customer_id, f.product_id, f.period_start_date,
                           f.units_sold, f.reported_soh, f.import_job_id, :job_id, :reason, to_jsonb(f.*),
                           CAST(:figures AS text[])
                    FROM fact_customer_sellthrough f
                    WHERE f.id IN :ids
                    RETURNING id, fact_id, units_sold, import_job_id, product_id
                    """
                ).bindparams(bindparam("ids", expanding=True)),
                {"job_id": int(by_job_id), "reason": reason, "ids": group, "figures": list(figs) if figs else None},
            ).all()
        )
    db.execute(
        text("DELETE FROM fact_customer_sellthrough WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": [int(r[1]) for r in moved]},
    )
    summary.rows = len(moved)
    summary.units = float(sum(float(r[2] or 0) for r in moved))
    summary.from_jobs = sorted({int(r[3]) for r in moved if r[3] is not None})
    summary.product_ids = {int(r[4]) for r in moved}
    logger.info(
        "cst supersede job_id=%s reason=%s rows=%s units=%s from_jobs=%s",
        by_job_id,
        reason,
        summary.rows,
        summary.units,
        summary.from_jobs,
    )
    return summary


def _keep_copy(db: Session, fact_id: int, *, by_job_id: int, reason: str, figures: list[str]) -> None:
    """Keep the row as it was, naming the figures it gives up (the row itself stays)."""
    db.execute(
        text(
            """
            INSERT INTO fact_customer_sellthrough_superseded (
                fact_id, source_key, tenant_id, customer_id, product_id, period_start_date,
                units_sold, reported_soh, import_job_id, superseded_by_import_job_id, reason, row_json, figures
            )
            SELECT f.id, f.source_key, f.tenant_id, f.customer_id, f.product_id, f.period_start_date,
                   f.units_sold, f.reported_soh, f.import_job_id, :job_id, :reason, to_jsonb(f.*), :figures
            FROM fact_customer_sellthrough f
            WHERE f.id = :id
            """
        ),
        {"job_id": int(by_job_id), "reason": reason, "figures": list(figures), "id": int(fact_id)},
    )


def _clear_figures(db: Session, fact_id: int, *, remaining: dict[str, int], cleared: list[str]) -> None:
    """Clear the given figures on a row (units to 0, stock to empty) and record who set the rest."""
    import json

    sets = ["figure_import_jobs = CAST(:jobs AS jsonb)", "updated_at = now()"]
    for f in cleared:
        sets.append("units_sold = 0" if f == "units_sold" else f"{f} = NULL")
    db.execute(
        text(f"UPDATE fact_customer_sellthrough SET {', '.join(sets)} WHERE id = :id"),
        {"jobs": json.dumps(remaining, sort_keys=True), "id": int(fact_id)},
    )


def record_same_key_replacements(
    db: Session,
    *,
    job_id: int,
    incoming: dict[str, dict[str, Any]],
) -> SupersedeSummary:
    """Before the source_key upsert: keep the stored row when this load replaces a figure with a
    different value that another load set (N-0111). A figure this load does not carry is left
    alone by the upsert, so nothing is recorded for it; an identical value is not a replacement.
    """
    summary = SupersedeSummary()
    if not incoming:
        return summary
    f = FactCustomerSellthrough
    stored = db.execute(
        select(f.id, f.source_key, f.import_job_id, f.figure_import_jobs, *[getattr(f, x) for x in FIGURES]).where(
            f.source_key.in_(list(incoming))
        )
    ).all()
    for row in stored:
        values = incoming[row.source_key]
        held = figure_jobs(row._mapping)
        replaced: list[str] = []
        for fig in carried_figures(values):
            old_job = held.get(fig)
            if old_job is None or old_job == int(job_id):
                continue
            old = getattr(row, fig)
            if old is None or float(old) != float(values[fig]):
                replaced.append(fig)
        if replaced:
            _keep_copy(db, int(row.id), by_job_id=int(job_id), reason=REASON_SAME_KEY, figures=replaced)
            summary.partial_rows += 1
            _count(summary, replaced)
    return summary


def supersede_restated_rows(
    db: Session,
    *,
    job_id: int,
    tenant_id: str,
    written_keys: set[str],
    restated: list[dict[str, Any]],
) -> SupersedeSummary:
    """Supersede the figures of older rows this load restated under other keys.

    ``restated`` are the fact values this load wrote (customer_id, product_id, period fields and
    the figures, ``None`` where the source line carried none).
    """
    if not written_keys or not restated:
        return SupersedeSummary()
    this_job = db.get(ImportJob, int(job_id))
    this_created = getattr(this_job, "created_at", None)

    # (customer, product, figure) -> periods this load carried that figure for.
    ranges: dict[tuple[int, int, str], list[tuple[date, date]]] = defaultdict(list)
    span: dict[int, tuple[date, date]] = {}
    products: dict[int, set[int]] = defaultdict(set)
    for v in restated:
        start, end = _range(v)
        cust, prod = int(v["customer_id"]), int(v["product_id"])
        for fig in carried_figures(v):
            ranges[(cust, prod, fig)].append((start, end))
        products[cust].add(prod)
        lo, hi = span.get(cust, (start, end))
        span[cust] = (min(lo, start), max(hi, end))

    f = FactCustomerSellthrough
    candidates: list[Any] = []
    for cust, (lo, hi) in span.items():
        candidates.extend(
            db.execute(
                select(
                    f.id,
                    f.source_key,
                    f.customer_id,
                    f.product_id,
                    f.period_start_date,
                    f.period_grain,
                    f.period_type,
                    f.import_job_id,
                    f.figure_import_jobs,
                    *[getattr(f, x) for x in FIGURES],
                ).where(
                    f.tenant_id == tenant_id,
                    f.customer_id == cust,
                    f.product_id.in_(sorted(products[cust])),
                    f.import_job_id != int(job_id),
                    f.period_start_date >= lo,
                    f.period_start_date <= hi,
                )
            ).all()
        )

    job_ids = {j for row in candidates for j in figure_jobs(row._mapping).values()}
    created_by_job = (
        dict(db.execute(select(ImportJob.id, ImportJob.created_at).where(ImportJob.id.in_(sorted(job_ids)))).all())
        if job_ids
        else {}
    )

    whole: dict[int, list[str]] = {}
    partial: dict[int, tuple[list[str], dict[str, int], float]] = {}
    for row in candidates:
        if row.source_key in written_keys:
            continue
        start = row.period_start_date
        end = period_end(start, _grain(row.period_grain, row.period_type))
        if end > span[int(row.customer_id)][1]:
            continue
        held = figure_jobs(row._mapping)
        gone: list[str] = []
        for fig, fig_job in held.items():
            if fig_job == int(job_id):
                continue
            created = created_by_job.get(fig_job)
            if this_created is not None and created is not None and created > this_created:
                continue  # a newer load's figure is never superseded by an older one
            if any(start <= r_end and r_start <= end for r_start, r_end in ranges.get((int(row.customer_id), int(row.product_id), fig), [])):
                gone.append(fig)
        if not gone:
            continue
        remaining = {k: v for k, v in held.items() if k not in gone}
        if remaining:
            partial[int(row.id)] = (sorted(gone, key=FIGURES.index), remaining, float(row.units_sold or 0))
        else:
            whole[int(row.id)] = sorted(gone, key=FIGURES.index)

    summary = move_to_superseded(db, whole, by_job_id=int(job_id), reason=REASON_RESTATED, figures=whole)
    for figs in whole.values():
        _count(summary, figs)
    for fid, (gone, remaining, units) in sorted(partial.items()):
        _keep_copy(db, fid, by_job_id=int(job_id), reason=REASON_FIGURES_RESTATED, figures=gone)
        _clear_figures(db, fid, remaining=remaining, cleared=gone)
        summary.partial_rows += 1
        if "units_sold" in gone:
            summary.units += units
        _count(summary, gone)
    if partial:
        logger.info(
            "cst supersede job_id=%s reason=%s partial_rows=%s figures=%s",
            job_id,
            REASON_FIGURES_RESTATED,
            len(partial),
            summary.figures,
        )
    return summary
