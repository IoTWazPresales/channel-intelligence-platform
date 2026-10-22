"""Deleting import jobs removes the data they loaded and brings back what they replaced (N-0112).

Warren 2026-10-22. Called by ``bulk_delete_import_jobs`` before the job rows go, inside the same
transaction, so the whole delete commits or rolls back as one. The preview runs the same code and
rolls back, so the counts it shows are the counts the delete produces.

For every fact row a deleted job holds, the row goes back to the figures it had before that job,
taken from the newest load that is not being deleted:

- **Customer sell-through** (``fact_customer_sellthrough``): each figure (units, on-hand, in-transit,
  on-order) on its own, following ``figure_import_jobs``. The earlier value comes from the
  superseded record the deleted job wrote (``fact_customer_sellthrough_superseded``), or, when the
  deleted job wrote the same value and so recorded nothing, from the earlier load's staging lines.
  A row moved aside whole comes back. A figure nobody else loaded is cleared; a row left with no
  figure is removed. A figure is not brought back when a newer load that stays now reports it for
  the same customer, product and period under another key (that load would have superseded it).
- **Distributor sell-out and returns** (``fact_sales_sellout``, ``fact_returns``): the whole line, from
  ``fact_distributor_line_superseded`` or the earlier load's staging lines; removed when no other
  load wrote it.
- **Distributor stock** (``fact_inventory_distributor``): from the newest other load whose staging
  line wrote that row; removed otherwise.
- **Shipments** (``fact_inbound_shipment``): a shipped line from the newest other load that reported
  it; an open-order line belongs to its load and is removed.

When a load that stays has since replaced the deleted job's figures, its figures stay; the
superseded record it wrote then points back at the figures from before the deleted job. The
superseded records a deleted job wrote, or that hold its figures, are removed.

Afterwards the stock positions of every customer touched are recomputed, the distributor-derived
tables (velocity, forecasts, stock reconciliation, weeks of cover) are rebuilt for every
distributor touched, and report slots a deleted job filled go back to due or missing.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.imports.customer_sell_through_supersede import FIGURES as ST_FIGURES
from app.services.imports.customer_sell_through_supersede import figure_jobs
from app.services.imports.dsi_line_supersede import FIGURES as LINE_FIGURES
from app.services.imports.dsi_line_supersede import RETURNS, SELLOUT, RepeatedLines, changed_figures

logger = logging.getLogger(__name__)

_LINE_JOB = {SELLOUT: "source_import_job_id", RETURNS: "import_job_id"}
# Columns a sell-through row takes from the load that set its units (prices travel with units).
_ST_UNIT_COMPANIONS = ("raw_mtd_units", "is_mtd_estimate", "unit_sell_price", "unit_cost", "unit_mac", "raw_source_row")
_ST_STOCK = ("reported_soh", "in_transit_units", "on_order_units")
_DERIVED = ("fact_customer_velocity", "fact_dsi_forecast", "fact_inventory_reconciliation", "weeks_of_cover_observation")
# Tables that keep their rows with the job link cleared: the record of what was learned or paid.
KEPT_LINKS = {
    "cpor_claim_evidence_line": "import_job_id",
    "cpor_payment_evidence": "import_job_id",
    "cst_listing_seed": "import_job_id",
    "customer_sellthrough_layout": "origin_import_job_id",
}


@dataclass
class RemovalSummary:
    """Per job: what goes and what comes back. Totals: what was recomputed."""

    per_job: dict[int, Counter] = field(default_factory=lambda: defaultdict(Counter))
    totals: Counter = field(default_factory=Counter)
    # Every superseded record removed, in full (Warren 2026-10-22: the audit event keeps them).
    removed_records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, job_id: int | None, key: str, n: int = 1) -> None:
        """Count against a deleted job; ``job_id`` None counts in the totals only."""
        if not n:
            return
        if job_id is not None:
            self.per_job[int(job_id)][key] += n
        self.totals[key] += n


def _table_exists(db: Session, name: str) -> bool:
    return bool(db.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{name}"}))


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return round(float(a), 4) == round(float(b), 4)


class JobDataRemoval:
    """Remove what ``job_ids`` loaded and restore what they replaced. One instance per delete."""

    def __init__(self, db: Session, job_ids: Iterable[int]) -> None:
        self.db = db
        self.d: set[int] = {int(j) for j in job_ids}
        self.d_list = sorted(self.d)
        self.summary = RemovalSummary()
        self._created: dict[int, tuple[datetime, int]] = {}
        # tenant -> customer -> products whose stock positions need a recompute
        self.customers: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        self.distributors: dict[int, str] = {}

    # ------------------------------------------------------------------ helpers
    def _order(self, job_ids: Iterable[int | None]) -> None:
        missing = sorted({int(j) for j in job_ids if j is not None and int(j) not in self._created})
        if not missing:
            return
        for jid, created in self.db.execute(
            text("SELECT id, created_at FROM import_job WHERE id = ANY(:ids)"), {"ids": missing}
        ).all():
            self._created[int(jid)] = (created or datetime.min.replace(tzinfo=timezone.utc), int(jid))
        for jid in missing:
            # A job row already gone sorts by id alone, before every job that still exists.
            self._created.setdefault(jid, (datetime.min.replace(tzinfo=timezone.utc), jid))

    def _when(self, job_id: int) -> tuple[datetime, int]:
        self._order([job_id])
        return self._created[int(job_id)]

    def _latest_before(self, candidates: Iterable[int], before: int) -> int | None:
        """The newest job of ``candidates`` loaded before ``before`` (job order: created, then id)."""
        cands = {int(c) for c in candidates if int(c) != int(before)}
        self._order([*cands, before])
        limit = self._when(before)
        older = [c for c in cands if self._created[c] < limit]
        return max(older, key=lambda c: self._created[c]) if older else None

    # ------------------------------------------------------------------ run
    def run(self) -> RemovalSummary:
        if not self.d:
            return self.summary
        if _table_exists(self.db, "fact_customer_sellthrough"):
            self._sellthrough()
        for table in (SELLOUT, RETURNS):
            if _table_exists(self.db, table):
                self._distributor_lines(table)
        if _table_exists(self.db, "fact_inventory_distributor"):
            self._inventory()
        if _table_exists(self.db, "fact_inbound_shipment"):
            self._shipments()
        self._report_slots()
        self._derived()
        self._stock_positions()
        self._kept_links()
        return self.summary

    # ------------------------------------------------------------------ customer sell-through
    def _st_records(self) -> list[dict[str, Any]]:
        if not _table_exists(self.db, "fact_customer_sellthrough_superseded"):
            return []
        return [
            dict(r)
            for r in self.db.execute(
                text(
                    """
                    SELECT * FROM fact_customer_sellthrough_superseded s
                    WHERE s.superseded_by_import_job_id = ANY(:d)
                       OR s.import_job_id = ANY(:d)
                       OR EXISTS (
                           SELECT 1 FROM jsonb_each_text(coalesce(s.row_json -> 'figure_import_jobs', '{}'::jsonb)) e
                           WHERE e.value ~ '^[0-9]+$' AND e.value::int = ANY(:d))
                    ORDER BY s.id
                    """
                ),
                {"d": self.d_list},
            ).mappings()
        ]

    @staticmethod
    def _record_figures(rec: dict[str, Any]) -> list[str]:
        figs = rec.get("figures")
        if figs:
            return [str(f) for f in figs if str(f) in ST_FIGURES]
        # Records made before N-0111 moved the whole row: every figure it held.
        return list(figure_jobs(rec.get("row_json") or {}))

    def _st_staging_value(self, row_id: int, job_id: int, fig: str) -> float | None:
        """What ``job_id`` loaded for ``fig`` into row ``row_id``: its applied lines, merged as apply does."""
        values = [
            r[0]
            for r in self.db.execute(
                text(
                    f"""
                    SELECT {fig} FROM import_customer_sellthrough_staging_line
                    WHERE import_job_id = :job AND fact_sellthrough_row_id = :row AND apply_status = 'applied'
                    ORDER BY source_row_number
                    """
                ),
                {"job": int(job_id), "row": int(row_id)},
            ).all()
        ]
        seen = [float(v) for v in values if v is not None]
        if not seen:
            return None
        if fig == "units_sold":
            return sum(seen)
        return seen[0] if len(set(seen)) == 1 else sum(seen)

    def _st_staging_jobs(self, row_id: int, fig: str) -> set[int]:
        return {
            int(r[0])
            for r in self.db.execute(
                text(
                    f"""
                    SELECT DISTINCT import_job_id FROM import_customer_sellthrough_staging_line
                    WHERE fact_sellthrough_row_id = :row AND apply_status = 'applied' AND {fig} IS NOT NULL
                    """
                ),
                {"row": int(row_id)},
            ).all()
        }

    def _st_walk(
        self, key: str, row_id: int | None, fig: str, holder: int | None, value: Any, by_record: dict
    ) -> tuple[int, Any, dict[str, Any] | None] | None:
        """Follow ``fig`` back from a deleted holder to the newest holder that stays.

        Returns (holder, value, record row_json the value came from or None), or None to clear.
        """
        base: dict[str, Any] | None = None
        seen: set[int] = set()
        while holder is not None and holder in self.d:
            if holder in seen:
                return None
            seen.add(holder)
            rec = next(
                (r for r in reversed(by_record.get((key, holder), [])) if fig in self._record_figures(r)), None
            )
            if rec is not None:
                state = rec.get("row_json") or {}
                base = state
                value = state.get(fig)
                holder = figure_jobs(state).get(fig)
                continue
            if row_id is None:
                return None
            prev = self._latest_before(self._st_staging_jobs(row_id, fig), holder)
            if prev is None:
                return None
            value = self._st_staging_value(row_id, prev, fig)
            holder = prev
            base = None
        if holder is None:
            return None
        return int(holder), value, base

    def _st_later_elsewhere(self, row: dict[str, Any], fig: str, holder: int) -> bool:
        """A newer load that stays reports ``fig`` for this customer, product and period under another key.

        Rows still waiting in this pass hold a deleted job's figure and do not count.
        """
        from app.services.channel_intelligence.customer_stock_gap import grain_of
        from app.services.imports.parsers.customer_sell_through_grain import period_end

        start = row.get("period_start_date")
        if isinstance(start, str):
            start = date.fromisoformat(start[:10])
        if start is None:
            return False
        end = period_end(start, grain_of(row.get("period_grain"), row.get("period_type")))
        others = self.db.execute(
            text(
                """
                SELECT id, source_key, period_start_date, period_grain, period_type, figure_import_jobs, import_job_id,
                       units_sold, reported_soh, in_transit_units, on_order_units
                FROM fact_customer_sellthrough
                WHERE customer_id = :c AND product_id = :p AND source_key <> :k
                  AND period_start_date <= :end AND period_start_date >= :start - 31
                """
            ),
            {"c": int(row["customer_id"]), "p": int(row["product_id"]), "k": row["source_key"], "end": end, "start": start},
        ).mappings()
        mine = self._when(holder)
        for o in others:
            o_end = period_end(o["period_start_date"], grain_of(o["period_grain"], o["period_type"]))
            if not (o["period_start_date"] <= end and start <= o_end):
                continue
            o_holder = figure_jobs(dict(o)).get(fig)
            if o_holder is None or o_holder in self.d:
                continue
            if self._when(o_holder) > mine:
                return True
        return False

    def _sellthrough(self) -> None:
        db = self.db
        rows = {
            r["source_key"]: dict(r)
            for r in db.execute(
                text(
                    """
                    SELECT * FROM fact_customer_sellthrough f
                    WHERE f.import_job_id = ANY(:d)
                       OR EXISTS (
                           SELECT 1 FROM jsonb_each_text(f.figure_import_jobs) e
                           WHERE e.value ~ '^[0-9]+$' AND e.value::int = ANY(:d))
                    """
                ),
                {"d": self.d_list},
            ).mappings()
        }
        records = self._st_records()
        by_record: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for rec in records:
            by_record[(rec["source_key"], int(rec["superseded_by_import_job_id"]))].append(rec)
        # Rows a deleted job moved aside, or emptied a figure of: they may come back.
        for rec in records:
            if int(rec["superseded_by_import_job_id"]) in self.d and rec["source_key"] not in rows:
                live = db.execute(
                    text("SELECT * FROM fact_customer_sellthrough WHERE source_key = :k"), {"k": rec["source_key"]}
                ).mappings().first()
                rows[rec["source_key"]] = dict(live) if live else {"_missing": True, **(rec.get("row_json") or {})}
        self._order(
            [j for r in rows.values() for j in figure_jobs(r).values()]
            + [int(r["superseded_by_import_job_id"]) for r in records]
        )
        for key, row in rows.items():
            self._st_restore_row(key, row, by_record)
        self._st_relink(records, by_record)
        ids = [int(r["id"]) for r in records]
        self._keep_removed("fact_customer_sellthrough_superseded", records)
        if ids:
            removed = int(
                db.execute(
                    text("DELETE FROM fact_customer_sellthrough_superseded WHERE id = ANY(:ids)"), {"ids": ids}
                ).rowcount
                or 0
            )
            if removed != len(ids):
                raise RuntimeError(
                    f"superseded sell-through records: {removed} of {len(ids)} removed "
                    "(is migration 20261022_0047 applied?)"
                )
        for rec in records:
            owner = int(rec["superseded_by_import_job_id"])
            self.summary.add(owner if owner in self.d else self._st_record_owner(rec), "superseded_records_removed")

    def _st_record_owner(self, rec: dict[str, Any]) -> int | None:
        for j in figure_jobs(rec.get("row_json") or {}).values():
            if j in self.d:
                return j
        j = rec.get("import_job_id")
        return int(j) if j is not None and int(j) in self.d else None

    def _st_restore_row(self, key: str, row: dict[str, Any], by_record: dict) -> None:
        missing = bool(row.pop("_missing", False))
        row_id = int(row["id"]) if row.get("id") is not None else None
        held = figure_jobs(row) if not missing else {}
        owner = next((j for j in held.values() if j in self.d), None)
        if owner is None and row.get("import_job_id") in self.d:
            owner = int(row["import_job_id"])
        new_jobs: dict[str, int] = {}
        new_values: dict[str, Any] = {}
        units_base: dict[str, Any] | None = None
        restored = kept = 0
        for fig in ST_FIGURES:
            holder = held.get(fig)
            if holder is not None and holder not in self.d:
                new_jobs[fig] = holder
                continue
            start = holder
            if start is None:
                # Emptied (or moved aside) by a deleted job: the newest record by a deleted job names it.
                jobs = [
                    j
                    for j in self.d
                    if any(fig in self._record_figures(r) for r in by_record.get((key, j), []))
                ]
                if not jobs:
                    continue
                start = max(jobs, key=self._when)
                owner = owner or start
            got = self._st_walk(key, row_id, fig, start, row.get(fig), by_record)
            if got is None:
                if holder is not None:
                    self.summary.add(holder, "sellthrough_figures_cleared")
                continue
            new_holder, value, base = got
            if self._st_later_elsewhere(row, fig, new_holder):
                self.summary.add(start, "sellthrough_figures_kept_later")
                kept += 1
                continue
            new_jobs[fig] = new_holder
            new_values[fig] = value
            restored += 1
            if fig == "units_sold" and base is not None:
                units_base = base
        if owner is None:
            return
        if restored:
            self.summary.add(owner, "sellthrough_figures_restored", restored)
        if not new_jobs:
            if not missing and row_id is not None:
                self.db.execute(text("DELETE FROM fact_customer_sellthrough WHERE id = :id"), {"id": row_id})
                self.summary.add(owner, "sellthrough_rows_removed")
                self._touch_customer(row)
            return
        merged = dict(row)
        for fig in ST_FIGURES:
            if fig in new_values:
                merged[fig] = new_values[fig]
            elif fig not in new_jobs:
                merged[fig] = 0.0 if fig == "units_sold" else None
        if merged.get("units_sold") is None:
            merged["units_sold"] = 0.0
        if units_base is not None:
            for col in _ST_UNIT_COMPANIONS:
                if col in units_base:
                    merged[col] = units_base[col]
        merged["figure_import_jobs"] = new_jobs
        merged["import_job_id"] = new_jobs.get("units_sold") or max(new_jobs.values(), key=self._when)
        if missing:
            merged.pop("figures", None)
            self.db.execute(
                text(
                    """
                    INSERT INTO fact_customer_sellthrough
                    SELECT * FROM jsonb_populate_record(NULL::fact_customer_sellthrough, CAST(:row AS jsonb))
                    """
                ),
                {"row": json.dumps(merged, default=str)},
            )
            self.summary.add(owner, "sellthrough_rows_restored")
        else:
            sets = ", ".join(f"{c} = :{c}" for c in (*ST_FIGURES, *_ST_UNIT_COMPANIONS) if c != "raw_source_row")
            self.db.execute(
                text(
                    f"""
                    UPDATE fact_customer_sellthrough
                    SET {sets}, raw_source_row = CAST(:raw_source_row AS jsonb),
                        figure_import_jobs = CAST(:jobs AS jsonb), import_job_id = :import_job_id, updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    **{c: merged.get(c) for c in (*ST_FIGURES, *_ST_UNIT_COMPANIONS) if c != "raw_source_row"},
                    "raw_source_row": json.dumps(merged.get("raw_source_row"), default=str)
                    if merged.get("raw_source_row") is not None
                    else None,
                    "jobs": json.dumps(new_jobs, sort_keys=True),
                    "import_job_id": merged["import_job_id"],
                    "id": row_id,
                },
            )
            if restored:
                self.summary.add(owner, "sellthrough_rows_restored")
        self._touch_customer(merged)

    def _st_relink(self, records: list[dict[str, Any]], by_record: dict) -> None:
        """A record by a load that stays, holding a deleted job's figures, points back past that job."""
        for rec in records:
            by = int(rec["superseded_by_import_job_id"])
            if by in self.d:
                continue
            state = dict(rec.get("row_json") or {})
            held = figure_jobs(state)
            figs = [f for f in self._record_figures(rec) if held.get(f) in self.d]
            if not figs:
                continue
            for fig in figs:
                self.summary.add(held[fig], "sellthrough_figures_kept_later")
            kept_figs: list[str] = []
            new_state = dict(state)
            new_jobs = dict(held)
            for fig in figs:
                got = self._st_walk(rec["source_key"], rec.get("fact_id"), fig, held[fig], state.get(fig), by_record)
                if got is None:
                    new_jobs.pop(fig, None)
                    continue
                holder, value, _base = got
                new_state[fig] = value
                new_jobs[fig] = holder
                kept_figs.append(fig)
            if not kept_figs:
                continue
            new_state["figure_import_jobs"] = new_jobs
            new_state["import_job_id"] = new_jobs.get("units_sold") or max(new_jobs.values(), key=self._when)
            self.db.execute(
                text(
                    """
                    INSERT INTO fact_customer_sellthrough_superseded (
                        fact_id, source_key, tenant_id, customer_id, product_id, period_start_date,
                        units_sold, reported_soh, import_job_id, superseded_by_import_job_id, reason, row_json, figures
                    ) VALUES (
                        :fact_id, :source_key, :tenant_id, :customer_id, :product_id, :period_start_date,
                        :units_sold, :reported_soh, :import_job_id, :by, :reason, CAST(:row_json AS jsonb), :figures
                    )
                    """
                ),
                {
                    "fact_id": rec["fact_id"],
                    "source_key": rec["source_key"],
                    "tenant_id": rec["tenant_id"],
                    "customer_id": rec["customer_id"],
                    "product_id": rec["product_id"],
                    "period_start_date": rec["period_start_date"],
                    "units_sold": _num(new_state.get("units_sold")) or 0.0,
                    "reported_soh": _num(new_state.get("reported_soh")),
                    "import_job_id": new_state["import_job_id"],
                    "by": by,
                    "reason": rec["reason"],
                    "row_json": json.dumps(new_state, default=str),
                    "figures": kept_figs,
                },
            )
            self.summary.totals["superseded_records_relinked"] += 1

    def _keep_removed(self, table: str, records: list[dict[str, Any]]) -> None:
        from app.utils.json_safe import to_jsonable

        for rec in records:
            self.summary.removed_records.append({"table": table, **to_jsonable(dict(rec))})

    def _touch_customer(self, row: dict[str, Any]) -> None:
        tid = str(row.get("tenant_id") or "default")
        if row.get("customer_id") is not None and row.get("product_id") is not None:
            self.customers[tid][int(row["customer_id"])].add(int(row["product_id"]))

    # ------------------------------------------------------------------ distributor sell-out and returns
    def _line_targets(self, keys: dict[str, dict[str, Any]], table: str) -> dict[str, dict[int, list[Any]]]:
        """Staging lines of other loads that wrote these keys: key -> job -> lines (row order)."""
        from app.models.import_distributor_si import ImportDistributorSiStagingLine as L
        from app.services.imports.distributor_sales_inventory import _dsi_sale_target

        if not keys:
            return {}
        quads = {
            (int(r["distributor_id"]), int(r["customer_id"]), int(r["product_id"]), r["transaction_date"])
            for r in keys.values()
        }
        dists, custs, prods, dates = (list(x) for x in zip(*quads))
        line_ids = [
            int(r[0])
            for r in self.db.execute(
                text(
                    """
                    SELECT l.id FROM import_distributor_si_staging_line l
                    JOIN unnest(CAST(:dists AS int[]), CAST(:custs AS int[]), CAST(:prods AS int[]), CAST(:dates AS date[]))
                         AS q(d, c, p, t)
                      ON l.resolved_distributor_id = q.d AND l.resolved_customer_id = q.c
                     AND l.resolved_product_id = q.p AND l.transaction_date = q.t
                    WHERE NOT (l.import_job_id = ANY(:d))
                      AND (l.apply_status LIKE '%sellout%' OR l.apply_status LIKE '%return%' OR l.apply_status LIKE '%duplicate%')
                    """
                ),
                {"dists": dists, "custs": custs, "prods": prods, "dates": dates, "d": self.d_list},
            ).all()
        ]
        out: dict[str, dict[int, list[Any]]] = defaultdict(lambda: defaultdict(list))
        if not line_ids:
            return out
        from sqlalchemy import select

        for start in range(0, len(line_ids), 1000):
            for line in self.db.scalars(
                select(L).where(L.id.in_(line_ids[start : start + 1000])).order_by(L.import_job_id, L.source_row_number)
            ).all():
                target = _dsi_sale_target(line)
                if target is None or target[0] != table or target[1] not in keys:
                    continue
                out[target[1]][int(line.import_job_id)].append((line, target[2]))
        return out

    @staticmethod
    def _figures_from_lines(table: str, key: str, lines: list[Any]) -> tuple[dict[str, Any], int]:
        repeats = RepeatedLines()
        for line, figs in lines:
            repeats.add(table, key, line, figs)
        return repeats.figures(table, key, {}), int(lines[0][0].id)

    def _distributor_lines(self, table: str) -> None:
        db = self.db
        job_col = _LINE_JOB[table]
        rows = {
            r["source_key"]: dict(r)
            for r in db.execute(text(f"SELECT * FROM {table} WHERE {job_col} = ANY(:d)"), {"d": self.d_list}).mappings()
        }
        has_records = _table_exists(db, "fact_distributor_line_superseded")
        records = (
            [
                dict(r)
                for r in db.execute(
                    text(
                        """
                        SELECT * FROM fact_distributor_line_superseded
                        WHERE fact_table = :t AND (superseded_by_import_job_id = ANY(:d) OR previous_import_job_id = ANY(:d))
                        ORDER BY id
                        """
                    ),
                    {"t": table, "d": self.d_list},
                ).mappings()
            ]
            if has_records
            else []
        )
        by_record: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for rec in records:
            by_record[(rec["source_key"], int(rec["superseded_by_import_job_id"]))].append(rec)
        # Lines kept by a load that stays: they need the rows' identity for the staging search too.
        kept_keys = {
            rec["source_key"]
            for rec in records
            if int(rec["superseded_by_import_job_id"]) not in self.d and rec["source_key"] not in rows
        }
        kept_rows = (
            {
                r["source_key"]: dict(r)
                for r in db.execute(
                    text(f"SELECT * FROM {table} WHERE source_key = ANY(:k)"), {"k": sorted(kept_keys)}
                ).mappings()
            }
            if kept_keys
            else {}
        )
        self._order(
            [r.get(job_col) for r in rows.values()]
            + [rec["superseded_by_import_job_id"] for rec in records]
            + [rec["previous_import_job_id"] for rec in records]
        )
        staged = self._line_targets({**rows, **kept_rows}, table)

        def walk(key: str, holder: int, state: dict[str, Any]) -> tuple[int, int | None, dict[str, Any]] | None:
            line_id = state.get("staging_line_id")
            seen: set[int] = set()
            while holder in self.d:
                if holder in seen:
                    return None
                seen.add(holder)
                recs = by_record.get((key, holder))
                if recs:
                    rec = recs[-1]
                    state = dict(rec["row_json"] or {})
                    prev = rec.get("previous_import_job_id")
                    if prev is None:
                        return None
                    holder, line_id = int(prev), rec.get("previous_staging_line_id")
                    continue
                prev = self._latest_before(staged.get(key, {}).keys(), holder)
                if prev is None:
                    return None
                figs, line_id = self._figures_from_lines(table, key, staged[key][prev])
                state = {**state, **figs}
                holder = prev
            return holder, line_id, state

        for key, row in rows.items():
            owner = int(row[job_col])
            got = walk(key, owner, row)
            self._touch_distributor(row)
            if got is None:
                db.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": int(row["id"])})
                self.summary.add(owner, f"{table}_rows_removed")
                continue
            holder, line_id, state = got
            figs = LINE_FIGURES[table]
            db.execute(
                text(
                    f"""
                    UPDATE {table} SET {", ".join(f"{c} = :{c}" for c in figs)},
                        staging_line_id = :line_id, {job_col} = :holder, updated_at = now()
                    WHERE id = :id
                    """
                ),
                {**{c: state.get(c) for c in figs}, "line_id": line_id, "holder": holder, "id": int(row["id"])},
            )
            self.summary.add(owner, f"{table}_rows_restored")

        # A load that stays replaced a deleted job's figures: its record now points past that job.
        for rec in records:
            by = int(rec["superseded_by_import_job_id"])
            prev = rec.get("previous_import_job_id")
            if by in self.d or prev is None or int(prev) not in self.d:
                continue
            self.summary.add(int(prev), f"{table}_kept_later")
            key = rec["source_key"]
            current = kept_rows.get(key)
            got = walk(key, int(prev), dict(rec["row_json"] or {}))
            if got is None or current is None:
                continue
            holder, line_id, state = got
            figures = changed_figures(table, state, current)
            if not figures:
                continue
            state = {**state, "staging_line_id": line_id, job_col: holder}
            db.execute(
                text(
                    """
                    INSERT INTO fact_distributor_line_superseded (
                        tenant_id, fact_table, fact_id, source_key, distributor_id, customer_id, product_id,
                        transaction_date, invoice_no, previous_staging_line_id, previous_import_job_id,
                        superseded_by_staging_line_id, superseded_by_import_job_id, figures, row_json
                    ) VALUES (
                        :tenant_id, :fact_table, :fact_id, :source_key, :distributor_id, :customer_id, :product_id,
                        :transaction_date, :invoice_no, :prev_line, :prev_job, :by_line, :by_job,
                        CAST(:figures AS jsonb), CAST(:row_json AS jsonb)
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "tenant_id": rec["tenant_id"],
                    "fact_table": table,
                    "fact_id": rec["fact_id"],
                    "source_key": key,
                    "distributor_id": rec["distributor_id"],
                    "customer_id": rec["customer_id"],
                    "product_id": rec["product_id"],
                    "transaction_date": rec["transaction_date"],
                    "invoice_no": rec["invoice_no"],
                    "prev_line": line_id,
                    "prev_job": holder,
                    "by_line": rec["superseded_by_staging_line_id"],
                    "by_job": by,
                    "figures": json.dumps(figures, default=str),
                    "row_json": json.dumps(state, default=str),
                },
            )
            self.summary.totals["superseded_records_relinked"] += 1

        ids = [int(r["id"]) for r in records]
        self._keep_removed("fact_distributor_line_superseded", records)
        if ids:
            removed = int(
                db.execute(text("DELETE FROM fact_distributor_line_superseded WHERE id = ANY(:ids)"), {"ids": ids}).rowcount
                or 0
            )
            if removed != len(ids):
                raise RuntimeError(
                    f"superseded distributor records: {removed} of {len(ids)} removed "
                    "(is migration 20261022_0047 applied?)"
                )
            for rec in records:
                by = int(rec["superseded_by_import_job_id"])
                prev = rec.get("previous_import_job_id")
                owner = by if by in self.d else (int(prev) if prev is not None and int(prev) in self.d else None)
                self.summary.add(owner, "superseded_records_removed")

    def _touch_distributor(self, row: dict[str, Any]) -> None:
        if row.get("distributor_id") is not None:
            self.distributors.setdefault(int(row["distributor_id"]), str(row.get("tenant_id") or "default"))

    # ------------------------------------------------------------------ distributor stock
    def _inventory(self) -> None:
        db = self.db
        rows = [
            dict(r)
            for r in db.execute(
                text("SELECT * FROM fact_inventory_distributor WHERE source_import_job_id = ANY(:d)"), {"d": self.d_list}
            ).mappings()
        ]
        if not rows:
            return
        by_row: dict[int, dict[int, tuple[int, float]]] = defaultdict(dict)
        for row_id, job_id, line_id, soh in db.execute(
            text(
                """
                SELECT fact_inventory_row_id, import_job_id, id, stock_on_hand
                FROM import_distributor_si_staging_line
                WHERE fact_inventory_row_id = ANY(:rows) AND NOT (import_job_id = ANY(:d)) AND stock_on_hand IS NOT NULL
                ORDER BY source_row_number
                """
            ),
            {"rows": [int(r["id"]) for r in rows], "d": self.d_list},
        ).all():
            by_row[int(row_id)][int(job_id)] = (int(line_id), float(soh))  # last line of the load wins
        for row in rows:
            owner = int(row["source_import_job_id"])
            self._touch_distributor(row)
            prev = self._latest_before(by_row.get(int(row["id"]), {}).keys(), owner)
            if prev is None:
                db.execute(text("DELETE FROM fact_inventory_distributor WHERE id = :id"), {"id": int(row["id"])})
                self.summary.add(owner, "fact_inventory_distributor_rows_removed")
                continue
            _line, soh = by_row[int(row["id"])][prev]
            db.execute(
                text(
                    """
                    UPDATE fact_inventory_distributor SET on_hand_units = :soh, source_import_job_id = :job,
                        calculated_soh = NULL, soh_variance = NULL, reconciliation_status = NULL,
                        reconciliation_run_at = NULL, updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"soh": soh, "job": prev, "id": int(row["id"])},
            )
            self.summary.add(owner, "fact_inventory_distributor_rows_restored")

    # ------------------------------------------------------------------ shipments
    def _shipments(self) -> None:
        from sqlalchemy import select

        from app.models.facts import FactInboundShipment
        from app.models.shipment_evidence import ShipmentEvidenceLine
        from app.services.imports.shipment_inbound_facts import _row_values_from_evidence, _upsert_shipped_chunk

        db = self.db
        rows = [
            dict(r)
            for r in db.execute(
                text("SELECT * FROM fact_inbound_shipment WHERE import_job_id = ANY(:d)"), {"d": self.d_list}
            ).mappings()
        ]
        if not rows:
            return
        for row in rows:
            for col in ("customer_id", "resolved_customer_id"):
                if row.get(col) is not None and row.get("product_id") is not None:
                    self.customers[str(row.get("tenant_id") or "default")][int(row[col])].add(int(row["product_id"]))
            for col in ("distributor_id", "resolved_distributor_id"):
                if row.get(col) is not None:
                    self.distributors.setdefault(int(row[col]), str(row.get("tenant_id") or "default"))
        shipped = [r for r in rows if (r.get("line_state") or "").strip().lower() == "shipped" and r.get("fact_upsert_key")]
        candidates: dict[str, dict[int, list[Any]]] = defaultdict(lambda: defaultdict(list))
        pairs = {(r.get("delivery_no"), r.get("item_code")) for r in shipped if r.get("delivery_no") and r.get("item_code")}
        if pairs:
            deliveries, items = (list(x) for x in zip(*pairs))
            keys = {str(r["fact_upsert_key"]) for r in shipped}
            line_ids = [
                int(x[0])
                for x in db.execute(
                    text(
                        """
                        SELECT l.id FROM shipment_evidence_line l
                        JOIN unnest(CAST(:deliveries AS text[]), CAST(:items AS text[])) AS q(dn, it)
                          ON l.delivery_no = q.dn AND l.item_code = q.it
                        WHERE NOT (l.import_job_id = ANY(:d))
                        """
                    ),
                    {"deliveries": deliveries, "items": items, "d": self.d_list},
                ).all()
            ]
            for start in range(0, len(line_ids), 1000):
                for line in db.scalars(
                    select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.id.in_(line_ids[start : start + 1000]))
                ).all():
                    values = _row_values_from_evidence(line)
                    if values["fact_upsert_key"] in keys:
                        candidates[values["fact_upsert_key"]][int(line.import_job_id)].append(values)
        tbl = FactInboundShipment.__table__
        shipped_ids = {int(r["id"]) for r in shipped}
        for row in rows:
            owner = int(row["import_job_id"])
            key = str(row.get("fact_upsert_key") or "")
            db.execute(text("DELETE FROM fact_inbound_shipment WHERE id = :id"), {"id": int(row["id"])})
            by_job = candidates.get(key) if int(row["id"]) in shipped_ids else None
            prev = self._latest_before(by_job.keys(), owner) if by_job else None
            if prev is None:
                self.summary.add(owner, "fact_inbound_shipment_rows_removed")
                continue
            values = [dict(v, tenant_id=row.get("tenant_id") or "default") for v in by_job[prev]]
            # Proof of delivery stays once any load that stays reported it (sticky POD).
            older_pods = [
                v.get("pod_date")
                for j in sorted(by_job, key=self._when)
                if self._when(j) <= self._when(prev)
                for v in by_job[j]
                if v.get("pod_date") is not None
            ]
            if older_pods and all(v.get("pod_date") is None for v in values):
                values[0]["pod_date"] = older_pods[-1]
            _upsert_shipped_chunk(db, tbl, values)
            self.summary.add(owner, "fact_inbound_shipment_rows_restored")

    # ------------------------------------------------------------------ what is derived from the facts
    def _report_slots(self) -> None:
        if not _table_exists(self.db, "customer_cst_report_slot"):
            return
        slots = self.db.execute(
            text("SELECT id, customer_id, week_start_date, import_job_id FROM customer_cst_report_slot WHERE import_job_id = ANY(:d)"),
            {"d": self.d_list},
        ).all()
        today = datetime.now(timezone.utc).date()
        for slot_id, cust, week_start, job in slots:
            other = self.db.scalar(
                text(
                    """
                    SELECT max(import_job_id) FROM fact_customer_sellthrough
                    WHERE customer_id = :c AND period_start_date BETWEEN :w AND :w + 6 AND NOT (import_job_id = ANY(:d))
                    """
                ),
                {"c": int(cust), "w": week_start, "d": self.d_list},
            )
            if other is not None:
                self.db.execute(
                    text("UPDATE customer_cst_report_slot SET import_job_id = :j, updated_at = now() WHERE id = :id"),
                    {"j": int(other), "id": int(slot_id)},
                )
                continue
            # The report is due the Monday after its week and late on the Tuesday (cst_d1).
            status = "missing" if today > week_start + timedelta(days=8) else "due"
            self.db.execute(
                text(
                    """
                    UPDATE customer_cst_report_slot SET status = :s, received_at = NULL, import_job_id = NULL,
                        updated_at = now() WHERE id = :id
                    """
                ),
                {"s": status, "id": int(slot_id)},
            )
            self.summary.add(int(job), "report_slots_reopened")

    def _derived(self) -> None:
        """Rebuild what is computed from distributor facts, for every distributor touched."""
        db = self.db
        for table in _DERIVED:
            if not _table_exists(db, table):
                continue
            for (dist,) in db.execute(
                text(f"SELECT DISTINCT distributor_id FROM {table} WHERE import_job_id = ANY(:d) AND distributor_id IS NOT NULL"),
                {"d": self.d_list},
            ).all():
                self.distributors.setdefault(int(dist), "default")
            n = int(db.execute(text(f"DELETE FROM {table} WHERE import_job_id = ANY(:d)"), {"d": self.d_list}).rowcount or 0)
            self.summary.totals[f"{table}_rows_removed"] += n
        if not self.distributors:
            return
        from app.services.demand_forecast.velocity_compute import generate_velocity_demand_forecasts
        from app.services.imports.dsi_forecasting import generate_distributor_forecasts
        from app.services.imports.dsi_soh_reconciliation import reconcile_distributor_soh
        from app.services.imports.dsi_velocity_intelligence import compute_distributor_velocity
        from app.services.imports.woc_observation import reconstruct_woc_observations

        for dist, tenant in sorted(self.distributors.items()):
            stamp = db.scalar(
                text(
                    """
                    SELECT max(j) FROM (
                        SELECT max(source_import_job_id) AS j FROM fact_sales_sellout WHERE distributor_id = :dist
                        UNION ALL SELECT max(source_import_job_id) FROM fact_inventory_distributor WHERE distributor_id = :dist
                        UNION ALL SELECT max(import_job_id) FROM fact_returns WHERE distributor_id = :dist
                    ) s
                    """
                ),
                {"dist": dist},
            )
            if stamp is None:
                # Nothing left to derive from: what was derived for this distributor goes too.
                for table in ("fact_customer_velocity", "fact_dsi_forecast", "fact_inventory_reconciliation"):
                    if _table_exists(db, table):
                        n = int(db.execute(text(f"DELETE FROM {table} WHERE distributor_id = :dist"), {"dist": dist}).rowcount or 0)
                        self.summary.totals[f"{table}_rows_removed"] += n
                self.summary.totals["distributors_recomputed"] += 1
                continue
            if _table_exists(db, "fact_customer_velocity"):
                db.execute(
                    text(
                        """
                        DELETE FROM fact_customer_velocity v WHERE v.distributor_id = :dist AND NOT EXISTS (
                            SELECT 1 FROM fact_sales_sellout s WHERE s.distributor_id = v.distributor_id
                              AND s.product_id = v.product_id AND s.customer_id = v.customer_id)
                        """
                    ),
                    {"dist": dist},
                )
            compute_distributor_velocity(db, dist, int(stamp))
            generate_distributor_forecasts(db, dist, int(stamp))
            generate_velocity_demand_forecasts(db, distributor_id=dist)
            period_end = db.scalar(
                text("SELECT max(as_of_date) FROM fact_inventory_distributor WHERE distributor_id = :dist"), {"dist": dist}
            )
            if period_end is not None and _table_exists(db, "fact_inventory_reconciliation"):
                reconcile_distributor_soh(db, distributor_id=dist, period_end_date=period_end, import_job_id=int(stamp))
            # The reconstruct sets a statement timeout for the rest of the transaction; put ours back.
            timeout = db.scalar(text("SHOW statement_timeout"))
            reconstruct_woc_observations(db, tenant_id=tenant, distributor_id=dist)
            db.execute(text("SELECT set_config('statement_timeout', :t, true)"), {"t": str(timeout)})
            self.summary.totals["distributors_recomputed"] += 1

    def _stock_positions(self) -> None:
        from app.services.channel_intelligence.customer_stock_gap import recompute_customer_stock_positions

        if not _table_exists(self.db, "customer_stock_position"):
            return
        for tid, cust, prod in self.db.execute(
            text("SELECT tenant_id, customer_id, product_id FROM customer_stock_position WHERE report_import_job_id = ANY(:d)"),
            {"d": self.d_list},
        ).all():
            self.customers[str(tid)][int(cust)].add(int(prod))
        for tid, by_customer in sorted(self.customers.items()):
            for cust, products in sorted(by_customer.items()):
                recompute_customer_stock_positions(self.db, tenant_id=tid, customer_id=cust, product_ids=sorted(products))
                self.summary.totals["customers_recomputed"] += 1

    def _kept_links(self) -> None:
        for table, col in KEPT_LINKS.items():
            if not _table_exists(self.db, table):
                continue
            for job, n in self.db.execute(
                text(f"SELECT {col}, count(*) FROM {table} WHERE {col} = ANY(:d) GROUP BY 1"), {"d": self.d_list}
            ).all():
                self.summary.add(int(job), f"{table}_kept", int(n))


def remove_job_data(db: Session, job_ids: Iterable[int]) -> RemovalSummary:
    return JobDataRemoval(db, job_ids).run()


__all__ = ["JobDataRemoval", "KEPT_LINKS", "RemovalSummary", "remove_job_data"]
