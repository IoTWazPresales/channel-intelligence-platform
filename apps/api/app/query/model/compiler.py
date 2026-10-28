"""Compile a validated plan into SQLAlchemy Core statements.

Shape of the rows statement::

    WITH agg AS (                       -- one GROUP BY over the fact model
      SELECT <period bucket>, <breakdown keys>, <base measures>
      FROM <fact> [JOIN <base joins>] [JOIN dim_product tenant path]
           [LEFT JOIN <dimension> ON key AND dimension.tenant_id = :tenant_id] ...
      WHERE <tenant> AND <model rules> AND <filters> AND <period window>
      GROUP BY <period bucket>, <breakdown keys>)
    SELECT agg.*, <calculated measures>
    FROM agg [LEFT JOIN agg AS prev ON prev.bucket = agg.bucket - 1 grain AND same keys]
    ORDER BY <sort> NULLS LAST, <keys> LIMIT :row_limit

Identifiers come only from the loaded model (validated against the ORM metadata); every value
is a bound parameter. Period buckets use ``calendar_grain.date_trunc_expr`` (the function
``volume_series`` uses), so ``bucket_key`` matches v1 (2026-W05, 2026-03, 2026-Q1).
Totals come from a second, ungrouped statement over the same FROM / WHERE, never by adding rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Numeric, and_, bindparam, cast, func, literal_column, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ColumnElement, Select

from app.query.calendar_grain import PERIOD_GRAINS, bucket_end as _v1_bucket_end, bucket_start_to_key, date_trunc_expr
from app.query.model.calendar_sql import bucket_end_exclusive, bucket_start_expr, prior_year_bucket_expr
from app.query.model.graph import Plan
from app.query.model.loader import DataModel, FactModel, Measure, _tables
from app.query.model.rules import MEASURE_RULES, MODEL_RULES
from app.query.model.tenant_restrictions import SPEC_KEY_RE, SPEC_PREFIX

UNASSIGNED = "Unassigned"
_UNASSIGNED_SQL = literal_column(f"'{UNASSIGNED}'")
_INTERVAL = {
    "day": literal_column("interval '1 day'"),
    "week": literal_column("interval '1 week'"),
    "month": literal_column("interval '1 month'"),
    "quarter": literal_column("interval '3 months'"),
    "year": literal_column("interval '1 year'"),
}


def platform_calendar(calendar: Any) -> bool:
    """Gregorian months, Monday weeks, year starting in January: the date_trunc path."""
    if calendar is None:
        return True
    cfg = getattr(calendar, "config", None) or {}
    return (
        getattr(calendar, "type", None) == "gregorian"
        and int(cfg.get("fiscal_year_start_month") or 1) == 1
        and int(cfg.get("week_start_day") or 0) == 0
        and not cfg.get("custom_periods")
    )


STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '10s'"


# ----------------------------------------------------------------------------- calendar helpers


def bucket_expr(col: Any, grain: str, calendar: Any = None) -> ColumnElement[Any]:
    if grain == "day":
        return cast(func.date_trunc(literal_column("'day'"), col), Date)
    if calendar is not None and not platform_calendar(calendar):
        return bucket_start_expr(col, grain, calendar)
    if grain in PERIOD_GRAINS:
        return date_trunc_expr(col, grain)
    if grain == "year":
        return cast(func.date_trunc(literal_column("'year'"), col), Date)
    raise ValueError(f"Illegal period grain {grain!r}")


def _shift_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _bucket_floor(d: date, grain: str, calendar: Any) -> date:
    if calendar is None:
        return bucket_start_of(d, grain)
    return calendar.bucket(d, grain).start


def _previous_floor(bucket_start: date, grain: str, calendar: Any) -> date:
    if calendar is None:
        return prev_bucket_start(bucket_start, grain)
    return calendar.bucket(bucket_start - timedelta(days=1), grain).start


def _prior_year_floor(bucket_start: date, grain: str, calendar: Any) -> date:
    if calendar is None:
        return bucket_start_of(_shift_year(bucket_start), grain)
    return calendar.bucket(calendar.same_day_last_year(bucket_start), grain).start


def bucket_start_of(d: date, grain: str) -> date:
    if grain == "day":
        return d
    if grain == "week":
        return d - timedelta(days=d.weekday())
    if grain == "month":
        return d.replace(day=1)
    if grain == "quarter":
        return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)
    return date(d.year, 1, 1)


def prev_bucket_start(bs: date, grain: str) -> date:
    if grain == "day":
        return bs - timedelta(days=1)
    if grain == "week":
        return bs - timedelta(days=7)
    months = {"month": 1, "quarter": 3, "year": 12}[grain]
    y, m = bs.year, bs.month - months
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


def bucket_last_day(bs: date, grain: str) -> date:
    if grain == "day":
        return bs
    if grain == "year":
        return date(bs.year, 12, 31)
    return _v1_bucket_end(bs, grain)


def bucket_key(bs: date, grain: str) -> str:
    if grain == "day":
        return bs.isoformat()
    if grain == "year":
        return f"{bs.year:04d}"
    return bucket_start_to_key(bs, grain)


def bucket_fields(bs: date, grain: str, calendar: Any = None) -> dict[str, str]:
    if calendar is not None and not platform_calendar(calendar):
        b = calendar.bucket(bs, grain)
        return {"bucket_key": b.label, "bucket_start": b.start.isoformat(), "bucket_end": b.end.isoformat()}
    return {
        "bucket_key": bucket_key(bs, grain),
        "bucket_start": bs.isoformat(),
        "bucket_end": bucket_last_day(bs, grain).isoformat(),
    }


# ----------------------------------------------------------------------------- compiled output


@dataclass
class OutputColumn:
    id: str
    kind: str  # breakdown | measure
    label: str
    fields: list[str]
    unit: str | None = None
    group: str | None = None
    sql_label: str | None = None  # measure column label in SQL


@dataclass
class Compiled:
    rows: Select
    totals: Select
    count: Select
    stored_types: Select | None
    columns: list[OutputColumn]
    measure_labels: dict[str, str]  # measure id -> SQL label
    total_labels: dict[str, str]  # base measure id -> label in totals
    joins: list[str]
    weeks_in_window: Decimal | None
    first_bucket_start: date | None
    notes: list[str] = field(default_factory=list)

    def sql_text(self) -> str:
        """Rows statement with bound parameter NAMES (never values)."""
        return str(self.rows.compile(dialect=postgresql.dialect()))


class _Ctx:
    """Aliases and joins for one compile."""

    def __init__(self, dm: DataModel, model: FactModel, tenant_id: str) -> None:
        self.dm = dm
        self.model = model
        self.tables = _tables()
        self.f = self.tables[model.table].alias("f")
        self.tid = bindparam("tenant_id", value=tenant_id)
        self.base: dict[str, Any] = {
            alias: self.tables[bj.table].alias(f"b_{alias}") for alias, bj in model.base_joins.items()
        }
        self.dims: dict[str, Any] = {}
        self.refs: dict[str, Any] = {}
        self.join_notes: list[str] = []
        self.calendar: Any = None
        self.shipment_counted_qty: Any = None
        self.shipment_kept: Any = None

    def owner(self, via: str | None) -> Any:
        return self.f if via is None else self.base[via]

    def aliases(self) -> dict[str, Any]:
        out = {"__base__": self.f, **self.base}
        if self.shipment_counted_qty is not None:
            out["__shipment_counted_qty__"] = self.shipment_counted_qty
        return out

    def dim(self, did: str) -> Any:
        if did not in self.dims:
            self.dims[did] = self.tables[self.dm.dimensions[did].table].alias(f"d_{did}")
        return self.dims[did]

    def ref(self, did: str, rid: str) -> Any:
        self.dim(did)
        if rid not in self.refs:
            ref = self.dm.dimensions[did].references[rid]
            self.refs[rid] = (did, self.tables[ref.table].alias(f"r_{rid}"))
        return self.refs[rid][1]

    def from_clause(self) -> Any:
        model = self.model
        fr: Any = self.f
        for alias, bj in model.base_joins.items():
            b = self.base[alias]
            fr = fr.join(b, b.c[bj.key] == self.f.c[bj.fk])
            self.join_notes.append(f"JOIN {bj.table} AS b_{alias} (base, many-to-one)")
        if model.tenant_via == "dim_product":
            tp = self.tables["dim_product"].alias("t_product")
            fr = fr.join(tp, and_(tp.c.id == self.f.c.product_id, tp.c[model.tenant_column] == self.tid))
            self.join_notes.append("JOIN dim_product AS t_product (tenant path)")
        for did, d in self.dims.items():
            j = model.joins[did]
            dim = self.dm.dimensions[did]
            on = d.c[dim.key] == self.owner(j.on).c[j.fk]
            if dim.tenant_column:
                on = and_(on, d.c[dim.tenant_column] == self.tid)
            fr = fr.outerjoin(d, on)
            self.join_notes.append(f"LEFT JOIN {dim.table} AS d_{did} (tenant-checked; null -> {UNASSIGNED})")
        for rid, (did, r) in self.refs.items():
            ref = self.dm.dimensions[did].references[rid]
            fr = fr.outerjoin(r, r.c[ref.key] == self.dims[did].c[ref.fk])
            self.join_notes.append(f"LEFT JOIN {ref.table} AS r_{rid} via d_{did} (current; null -> {UNASSIGNED})")
        if "shipment_twin_remainder" in model.rules:
            from app.models.facts import FactInboundShipment
            from app.services.shipment_strict_pair import twin_remainder

            twin = twin_remainder(FactInboundShipment)
            fr = fr.outerjoin(twin.subquery, twin.subquery.c.fact_id == self.f.c.id)
            self.shipment_counted_qty = func.coalesce(twin.subquery.c.counted_qty, self.f.c.quantity)
            self.shipment_kept = or_(twin.subquery.c.fact_id.is_(None), twin.subquery.c.counted_qty > 0)
            self.join_notes.append(
                "LEFT JOIN shipment twin remainder (covered open lines left out; a partial line keeps the remainder)"
            )
        return fr

    def tenant_conds(self) -> list[ColumnElement[bool]]:
        model = self.model
        if model.tenant_via is None:
            return [self.f.c[model.tenant_column] == self.tid]
        if model.tenant_via == "dim_product":
            return []  # inner join carries it
        return [self.base[model.tenant_via].c[model.tenant_column] == self.tid]


@dataclass
class _Breakdown:
    id: str
    kind: str  # period | entity | reference | attribute | local
    key_expr: Any
    name_expr: Any = None
    filter_expr: Any = None


def _breakdown(ctx: _Ctx, bid: str, grain: str | None) -> _Breakdown:
    dm, model = ctx.dm, ctx.model
    if bid == "period":
        assert model.time is not None and grain is not None
        tcol = ctx.owner(model.time.on).c[model.time.column]
        return _Breakdown(id=bid, kind="period", key_expr=bucket_expr(tcol, grain, ctx.calendar))
    if bid in model.joins:
        j = model.joins[bid]
        col = ctx.owner(j.on).c[j.fk]
        return _Breakdown(id=bid, kind="entity", key_expr=col, filter_expr=col)
    if bid in model.local:
        loc = model.local[bid]
        col = ctx.owner(loc.on).c[loc.column]
        if loc.name_column:
            return _Breakdown(
                id=bid, kind="reference", key_expr=col,
                name_expr=ctx.owner(loc.on).c[loc.name_column], filter_expr=col,
            )
        expr = func.coalesce(col, _UNASSIGNED_SQL)
        return _Breakdown(id=bid, kind="local", key_expr=expr, filter_expr=expr)
    for did in model.joins:
        dim = dm.dimensions[did]
        if bid in dim.attributes:
            col = ctx.dim(did).c[dim.attributes[bid].column]
            expr = func.coalesce(col, _UNASSIGNED_SQL)
            return _Breakdown(id=bid, kind="attribute", key_expr=expr, filter_expr=expr)
        if bid in dim.references:
            ref = dim.references[bid]
            r = ctx.ref(did, bid)
            return _Breakdown(
                id=bid,
                kind="reference",
                key_expr=r.c[ref.key],
                name_expr=r.c[ref.name_column],
                filter_expr=r.c[ref.key],
            )
    if bid.startswith(SPEC_PREFIX) and "product" in model.joins:
        key = bid[len(SPEC_PREFIX):]
        if SPEC_KEY_RE.fullmatch(key):
            # One fixed extractor. The key is a bound parameter, never concatenated SQL.
            extracted = ctx.dim("product").c.specs_json.op("->>")(bindparam(f"spec_key_{key}", value=key))
            expr = func.coalesce(extracted, _UNASSIGNED_SQL)
            return _Breakdown(id=bid, kind="attribute", key_expr=expr, filter_expr=expr)
    raise ValueError(f"breakdown {bid!r} is not on model {model.id}")  # graph refused it already


def _measure_expr(ctx: _Ctx, m: Measure, window: ColumnElement[bool] | None, latest: Any) -> ColumnElement[Any]:
    f = ctx.f
    if m.rule:
        value = MEASURE_RULES[m.rule](ctx.aliases())
    elif m.column:
        value = f.c[m.column]
    else:
        value = None
    conds: list[ColumnElement[bool]] = []
    if m.when_not_null:
        conds.append(f.c[m.when_not_null].is_not(None))
    if m.agg == "latest_sum":
        assert ctx.model.time is not None and latest is not None and value is not None
        conds = [f.c[ctx.model.time.column] == latest.c.d, value.is_not(None)]
        return func.sum(value).filter(and_(*conds))
    if window is not None:
        conds.append(window)
    if m.agg == "sum":
        agg = func.sum(value)
    elif m.agg == "count":
        agg = func.count()
    elif m.agg == "avg":
        agg = func.avg(value)
    elif m.agg == "min":
        agg = func.min(value)
    elif m.agg == "max":
        agg = func.max(value)
    else:  # count_distinct
        agg = func.count(func.distinct(value))
    if conds:
        agg = agg.filter(and_(*conds))
    # avg/min/max of no rows is null. Coalescing them to 0 would invent a quantity.
    if m.agg in {"avg", "min", "max"}:
        return agg
    return func.coalesce(agg, literal_column("0"))


def _num(x: Any) -> Any:
    return cast(x, Numeric)


def compile_plan(dm: DataModel, plan: Plan, *, tenant_id: str, calendar: Any = None) -> Compiled:
    model = plan.model
    assert model is not None
    ctx = _Ctx(dm, model, tenant_id)
    ctx.calendar = None if platform_calendar(calendar) else calendar
    grain = plan.period_grain
    tcol = ctx.owner(model.time.on).c[model.time.column] if model.time is not None else None

    bds = [_breakdown(ctx, b, grain) for b in plan.breakdowns]
    filter_bds = {flt.breakdown: _breakdown(ctx, flt.breakdown, grain) for flt in plan.filters}

    # --- WHERE (shared by rows, totals and the stored-period check)
    conds: list[ColumnElement[bool]] = list(ctx.tenant_conds())
    for rule in model.rules:
        if rule == "shipment_twin_remainder":
            continue
        conds.extend(MODEL_RULES[rule](ctx.aliases()))
    for i, flt in enumerate(plan.filters):
        expr = filter_bds[flt.breakdown].filter_expr
        vals = [UNASSIGNED if v is None else v for v in flt.values]
        if len(vals) == 1 and not flt.is_list:
            conds.append(expr == bindparam(f"filter_{flt.breakdown}", value=vals[0]))
        else:
            conds.append(expr.in_(bindparam(f"filter_{flt.breakdown}", value=vals, expanding=True)))
    for b in plan.breakdowns:
        j = model.joins.get(b)
        if j is not None and j.null_keys == "exclude_when_grouped":
            conds.append(ctx.owner(j.on).c[j.fk].is_not(None))

    window_parts: list[ColumnElement[bool]] = []
    if tcol is not None and plan.period_from is not None:
        window_parts.append(tcol >= bindparam("period_from", value=plan.period_from, type_=Date))
    if tcol is not None and plan.period_to is not None:
        window_parts.append(tcol <= bindparam("period_to", value=plan.period_to, type_=Date))
    window = and_(*window_parts) if window_parts else None

    # Read the previous bucket, and when a prior year is asked for, the year-earlier buckets.
    # Both stop at the first displayed bucket, so days of that bucket before period.from stay out.
    first_bucket: date | None = None
    widened = window
    if grain and plan.period_from is not None and tcol is not None and (plan.needs_prev or plan.needs_prior_year):
        first_bucket = _bucket_floor(plan.period_from, grain, ctx.calendar)
        if plan.needs_prior_year:
            extra_from = _prior_year_floor(first_bucket, grain, ctx.calendar)
            extra_name = "prior_year_from"
        else:
            extra_from = _previous_floor(first_bucket, grain, ctx.calendar)
            extra_name = "prev_bucket_from"
        early = and_(
            tcol >= bindparam(extra_name, value=extra_from, type_=Date),
            tcol < bindparam("first_bucket_start", value=first_bucket, type_=Date),
        )
        widened = or_(window, early) if window is not None else early

    # Semi-additive (latest report per key) measures: CST reported stock.
    latest = None
    latest_measures = [m for m in plan.base_measures if m.agg == "latest_sum"]
    if latest_measures:
        lm = latest_measures[0]
        assert tcol is not None and lm.latest_per and lm.column
        f2 = ctx.tables[model.table].alias("f_latest")
        lconds: list[ColumnElement[bool]] = [f2.c[model.tenant_column] == ctx.tid, f2.c[lm.column].is_not(None)]
        if plan.period_to is not None:
            lconds.append(f2.c[model.time.column] <= bindparam("period_to", value=plan.period_to, type_=Date))  # type: ignore[union-attr]
        # Same filters as load_stock_positions: customer and site narrow the latest date; product
        # filters only narrow what is summed at that date.
        for flt in plan.filters:
            col = None
            if flt.breakdown in model.joins and model.joins[flt.breakdown].on is None and model.joins[flt.breakdown].fk == lm.latest_per:
                col = f2.c[lm.latest_per]
            elif flt.breakdown in model.local and model.local[flt.breakdown].on is None:
                col = func.coalesce(f2.c[model.local[flt.breakdown].column], _UNASSIGNED_SQL)
            if col is not None:
                vals = [UNASSIGNED if v is None else v for v in flt.values]
                lconds.append(col.in_(bindparam(f"latest_filter_{flt.breakdown}", value=vals, expanding=True)))
        latest = (
            select(f2.c[lm.latest_per].label("k"), func.max(f2.c[model.time.column]).label("d"))  # type: ignore[union-attr]
            .where(*lconds)
            .group_by(f2.c[lm.latest_per])
            .subquery("latest")
        )

    fr = ctx.from_clause()
    if ctx.shipment_kept is not None:
        conds.append(ctx.shipment_kept)
    if latest is not None:
        fr = fr.outerjoin(latest, latest.c.k == ctx.f.c[latest_measures[0].latest_per])
        ctx.join_notes.append("LEFT JOIN latest stock report date per customer (on or before period.to)")

    def where_for(win: ColumnElement[bool] | None) -> list[ColumnElement[bool]]:
        out = list(conds)
        if latest is not None and win is not None:
            out.append(or_(win, ctx.f.c[model.time.column] == latest.c.d))  # type: ignore[union-attr]
        elif win is not None:
            out.append(win)
        return out

    flow_window = window if latest is not None else None

    # --- agg CTE
    agg_cols: list[Any] = []
    group_by: list[Any] = []
    for b in bds:
        if b.kind == "period":
            agg_cols.append(b.key_expr.label("bucket_start"))
            group_by.append(b.key_expr)
        elif b.kind == "reference":
            agg_cols.append(b.key_expr.label(f"{b.id}_id"))
            agg_cols.append(func.coalesce(b.name_expr, _UNASSIGNED_SQL).label(f"{b.id}_name"))
            group_by.extend([b.key_expr, b.name_expr])
        elif b.kind == "entity":
            agg_cols.append(b.key_expr.label(f"{b.id}_id"))
            group_by.append(b.key_expr)
        else:
            agg_cols.append(b.key_expr.label(b.id))
            group_by.append(b.key_expr)
    measure_labels: dict[str, str] = {}
    for i, m in enumerate(plan.base_measures):
        lab = f"m{i}"
        measure_labels[m.id] = lab
        agg_cols.append(_measure_expr(ctx, m, flow_window, latest).label(lab))

    agg_q = select(*agg_cols).select_from(fr).where(*where_for(widened))
    if group_by:
        agg_q = agg_q.group_by(*group_by)
    agg = agg_q.cte("agg")

    # --- final select
    key_cols: list[str] = []
    for b in bds:
        if b.kind == "period":
            key_cols.append("bucket_start")
        elif b.kind in ("entity", "reference"):
            key_cols.append(f"{b.id}_id")
        else:
            key_cols.append(b.id)

    prev = None
    from_final: Any = agg
    if plan.needs_prev and grain:
        prev = agg.alias("prev")
        if ctx.calendar is None:
            prev_bucket = cast(agg.c.bucket_start - _INTERVAL[grain], Date)
        else:
            prev_bucket = bucket_start_expr(
                agg.c.bucket_start - literal_column("interval '1 day'"), grain, ctx.calendar
            )
        on = [prev.c.bucket_start == prev_bucket]
        on.extend(prev.c[k].is_not_distinct_from(agg.c[k]) for k in key_cols if k != "bucket_start")
        from_final = agg.outerjoin(prev, and_(*on))

    yearago = None
    if plan.needs_prior_year and grain:
        yearago = agg.alias("yearago")
        if ctx.calendar is None:
            shifted = bucket_expr(agg.c.bucket_start - literal_column("interval '1 year'"), grain, None)
        else:
            shifted = prior_year_bucket_expr(agg.c.bucket_start, grain, ctx.calendar)
        on_year = [yearago.c.bucket_start == shifted]
        on_year.extend(yearago.c[k].is_not_distinct_from(agg.c[k]) for k in key_cols if k != "bucket_start")
        from_final = from_final.outerjoin(yearago, and_(*on_year))

    weeks_in_window: Decimal | None = None
    if plan.period_from is not None and plan.period_to is not None:
        weeks_in_window = Decimal((plan.period_to - plan.period_from).days + 1) / Decimal(7)

    def weeks_expr() -> Any:
        if "period" in plan.breakdowns and grain:
            start: Any = agg.c.bucket_start
            if ctx.calendar is None:
                end_excl: Any = cast(agg.c.bucket_start + _INTERVAL[grain], Date)
            else:
                end_excl = bucket_end_exclusive(agg.c.bucket_start, grain, ctx.calendar)
            if plan.period_from is not None:
                start = func.greatest(start, bindparam("rate_from", value=plan.period_from, type_=Date))
            if plan.period_to is not None:
                end_excl = func.least(end_excl, bindparam("rate_to_excl", value=plan.period_to + timedelta(days=1), type_=Date))
            return _num(end_excl - start) / literal_column("7")
        return bindparam("weeks_in_window", value=weeks_in_window, type_=Numeric)

    def expr_for(mid: str) -> Any:
        m = dm.measure(mid)
        assert m is not None
        if isinstance(m, Measure):
            return agg.c[measure_labels[m.id]]
        a = m.inputs[0]
        if m.kind == "prior_period":
            assert prev is not None
            return prev.c[measure_labels[a]]
        if m.kind == "prior_year":
            assert yearago is not None
            return yearago.c[measure_labels[a]]
        if m.kind == "running_total":
            base = expr_for(a)
            parts = [agg.c[k] for k in key_cols if k != "bucket_start"]
            return func.sum(base).over(partition_by=parts or None, order_by=agg.c.bucket_start)
        if m.kind == "share_of_total":
            base = expr_for(a)
            return _num(base) / func.nullif(func.sum(_num(base)).over(), 0)
        if m.kind == "pct_change":
            assert prev is not None
            cur_v, prev_v = _num(agg.c[measure_labels[a]]), _num(prev.c[measure_labels[a]])
            return (cur_v - prev_v) / func.nullif(prev_v, 0)
        if m.kind == "ratio":
            return _num(expr_for(m.inputs[0])) / func.nullif(_num(expr_for(m.inputs[1])), 0)
        if m.kind == "difference":
            return expr_for(m.inputs[0]) - expr_for(m.inputs[1])
        if m.kind == "per_week_rate":
            return _num(expr_for(a)) / func.nullif(weeks_expr(), 0)
        raise ValueError(m.kind)

    breakdown_labels = [c.name for c in agg_cols if c.name not in measure_labels.values()]
    final_cols: list[Any] = [agg.c[name] for name in breakdown_labels]
    out_labels: dict[str, str] = {}
    for i, m in enumerate(plan.measures):
        lab = f"out{i}"
        out_labels[m.id] = lab
        final_cols.append(expr_for(m.id).label(lab))
    final_q = select(*final_cols).select_from(from_final)
    if first_bucket is not None:
        final_q = final_q.where(agg.c.bucket_start >= bindparam("rows_from_bucket", value=first_bucket, type_=Date))

    # Sort: measure or breakdown from this request; then every key, for a stable order.
    order: list[Any] = []
    sort_col = None
    if plan.sort_by:
        if plan.sort_by in out_labels:
            sort_col = literal_column(out_labels[plan.sort_by])
        else:
            sort_col = agg.c[key_cols[plan.breakdowns.index(plan.sort_by)]]
    elif "period" in plan.breakdowns:
        sort_col = agg.c.bucket_start
    elif plan.measures:
        sort_col = literal_column(out_labels[plan.measures[0].id])
    if sort_col is not None:
        order.append(sort_col.asc().nulls_last() if plan.sort_dir == "asc" else sort_col.desc().nulls_last())
    order.extend(agg.c[k].asc().nulls_last() for k in key_cols if agg.c[k] is not sort_col)
    rows_q = final_q.order_by(*order).limit(bindparam("row_limit", value=plan.limit + 1))
    count_q = select(func.count()).select_from(final_q.subquery("counted"))

    # --- totals: same FROM / WHERE, no GROUP BY, unwidened window
    total_cols: list[Any] = []
    total_labels: dict[str, str] = {}
    for i, m in enumerate(plan.base_measures):
        lab = f"t{i}"
        total_labels[m.id] = lab
        total_cols.append(_measure_expr(ctx, m, flow_window, latest).label(lab))
    if tcol is not None:
        total_cols.append(func.min(tcol).label("vintage_min"))
        total_cols.append(func.max(tcol).label("vintage_max"))
    totals_q = select(*total_cols).select_from(fr).where(*where_for(window))

    stored_q = None
    if model.time is not None and model.time.floor == "stored_period_type" and "period" in plan.breakdowns:
        ptc = ctx.owner(model.time.on).c[model.time.period_type_column]
        stored_q = select(func.distinct(ptc)).select_from(fr).where(*where_for(window))

    columns: list[OutputColumn] = []
    for b in bds:
        label, group = dm.breakdown_label(b.id)
        if b.kind == "period":
            fields = ["bucket_key", "bucket_start", "bucket_end"]
        elif b.kind in ("entity", "reference"):
            fields = [f"{b.id}_id", f"{b.id}_name"]
        else:
            fields = [b.id]
        columns.append(OutputColumn(id=b.id, kind="breakdown", label=label, fields=fields, group=group))
    for m in plan.measures:
        columns.append(
            OutputColumn(id=m.id, kind="measure", label=m.label, fields=[m.id], unit=m.unit, sql_label=out_labels[m.id])
        )
    notes = []
    if first_bucket is not None and plan.period_from is not None and plan.period_from != first_bucket:
        notes.append("period.from falls inside a bucket: the first bucket is partial; its previous bucket is whole.")
    return Compiled(
        rows=rows_q,
        totals=totals_q,
        count=count_q,
        stored_types=stored_q,
        columns=columns,
        measure_labels=out_labels,
        total_labels=total_labels,
        joins=list(ctx.join_notes),
        weeks_in_window=weeks_in_window,
        first_bucket_start=first_bucket,
        notes=notes,
    )
