"""Load and validate the data model file (``app/semantics/models/default.yaml``).

Every table, column and id the compiler will ever use comes from this file and is checked here
against the ORM metadata. Anything the loader cannot resolve is refused at load time, so a
request can only ever name ids that exist in the loaded model (lookups, never string building).

Tenant isolation is structural: a model must name a ``tenant_column`` on its base table, or a
``tenant_via`` path (``dim_product`` through ``product_id``, or one of its own inner
``base_joins``) whose table carries that column. The loader refuses a model with neither.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

MODEL_PATH = Path(__file__).resolve().parents[2] / "semantics" / "models" / "default.yaml"

AGGS = frozenset({"sum", "count", "count_distinct", "latest_sum", "avg", "min", "max"})
ADDITIVITY = frozenset({"additive", "semi_additive", "non_additive"})
CALC_KINDS = frozenset({
    "ratio",
    "difference",
    "prior_period",
    "pct_change",
    "per_week_rate",
    "prior_year",
    "running_total",
    "share_of_total",
})
TIME_FLOORS = frozenset({"day", "stored_period_type"})
NULL_KEYS = frozenset({"unassigned", "exclude_when_grouped"})
# Rules and measure expressions that need SQL are built in code (rules.py); the file only names them.
KNOWN_RULES = frozenset({"cpor_portfolio_lines", "lineup_current_cases", "shipment_twin_remainder"})
KNOWN_MEASURE_RULES = frozenset({"cpor_line_support_usd", "shipment_counted_quantity"})

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_MEASURE_ID = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class ModelLoadError(ValueError):
    """The model file names something that does not exist or breaks a format rule."""


@dataclass(frozen=True)
class Attribute:
    id: str
    dimension: str
    column: str
    label: str
    group: str


@dataclass(frozen=True)
class Reference:
    """A dimension reached through another dimension (region / channel via customer)."""

    id: str
    dimension: str
    table: str
    fk: str
    key: str
    name_column: str
    label: str
    group: str


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    group: str
    table: str
    key: str
    tenant_column: str | None
    attributes: dict[str, Attribute]
    references: dict[str, Reference]


@dataclass(frozen=True)
class Join:
    dimension: str
    fk: str
    on: str | None  # None = base table, else a base_joins alias
    role: str | None
    null_keys: str


@dataclass(frozen=True)
class BaseJoin:
    alias: str
    table: str
    fk: str
    key: str


@dataclass(frozen=True)
class Local:
    id: str
    column: str
    on: str | None
    label: str
    group: str
    # Optional named identity on the same owner, e.g. CPOR case ID + case_name.
    name_column: str | None = None


@dataclass(frozen=True)
class TimeDef:
    column: str
    on: str | None
    floor: str
    period_type_column: str | None


@dataclass(frozen=True)
class Measure:
    id: str
    model: str
    local_id: str
    label: str
    unit: str
    agg: str
    column: str | None
    rule: str | None
    when_not_null: str | None
    latest_per: str | None
    additivity: str
    legacy_key: str | None
    kind: str = "base"


@dataclass(frozen=True)
class Calculated:
    id: str
    model: str
    kind: str
    inputs: tuple[str, ...]
    label: str
    unit: str
    additivity: str = "non_additive"


@dataclass(frozen=True)
class FactModel:
    id: str
    label: str
    table: str
    tenant_column: str
    tenant_via: str | None  # None = base table; "dim_product"; or a base_joins alias
    base_joins: dict[str, BaseJoin]
    rules: tuple[str, ...]
    time: TimeDef | None
    joins: dict[str, Join]
    local: dict[str, Local]
    measures: dict[str, Measure]


@dataclass(frozen=True)
class WallKeep:
    metric: str
    grains: frozenset[str]
    text: str


@dataclass(frozen=True)
class Wall:
    id: str
    reason: str
    trigger: dict[str, Any]
    keeps: tuple[WallKeep, ...]


@dataclass(frozen=True)
class PeriodDef:
    label: str
    group: str
    grains: tuple[str, ...]
    default_grain: str


@dataclass(frozen=True)
class DataModel:
    version: int
    digest: str
    source_doc: str
    groups: tuple[str, ...]
    period: PeriodDef
    dimensions: dict[str, Dimension]
    models: dict[str, FactModel]
    calculated: dict[str, Calculated]
    walls: tuple[Wall, ...]
    pending: tuple[dict[str, str], ...]
    measures: dict[str, Measure] = field(default_factory=dict)

    def measure(self, measure_id: str) -> Measure | Calculated | None:
        key = str(measure_id or "")
        return self.measures.get(key) or self.calculated.get(key)

    def model_of(self, measure_id: str) -> str | None:
        m = self.measure(measure_id)
        return m.model if m is not None else None

    def wall(self, wall_id: str) -> Wall | None:
        for w in self.walls:
            if w.id == wall_id:
                return w
        return None

    def breakdown_label(self, bid: str) -> tuple[str, str]:
        """(label, group) of any breakdown id known to the file."""
        if bid == "period":
            return self.period.label, self.period.group
        for dim in self.dimensions.values():
            if bid == dim.id:
                return dim.label, dim.group
            if bid in dim.attributes:
                return dim.attributes[bid].label, dim.attributes[bid].group
            if bid in dim.references:
                return dim.references[bid].label, dim.references[bid].group
        for model in self.models.values():
            if bid in model.local:
                return model.local[bid].label, model.local[bid].group
        if bid.startswith("spec_"):
            return f"Spec: {bid[5:]}", "Product"
        return bid, ""

    def breakdown_ids(self) -> frozenset[str]:
        out = {"period"}
        for dim in self.dimensions.values():
            out.add(dim.id)
            out.update(dim.attributes)
            out.update(dim.references)
        for model in self.models.values():
            out.update(model.local)
        return frozenset(out)


def _tables() -> dict[str, Any]:
    import app.models  # noqa: F401  (registers every mapped table on Base.metadata)
    from app.db.base import Base

    return dict(Base.metadata.tables)


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ModelLoadError(msg)


def _ident(raw: Any, what: str) -> str:
    s = str(raw or "").strip()
    _need(bool(_ID.match(s)), f"{what}: {raw!r} is not a valid id")
    return s


def _column(tables: dict[str, Any], table: str, column: Any, what: str) -> str:
    col = str(column or "").strip()
    _need(table in tables, f"{what}: unknown table {table!r}")
    _need(col in tables[table].c, f"{what}: table {table!r} has no column {col!r}")
    return col


def _parse_dimensions(raw: dict[str, Any], tables: dict[str, Any]) -> dict[str, Dimension]:
    out: dict[str, Dimension] = {}
    for did, body in (raw or {}).items():
        did = _ident(did, "dimension")
        table = str(body.get("table") or "")
        key = _column(tables, table, body.get("key") or "id", f"dimension {did}")
        tenant_column = body.get("tenant_column")
        if tenant_column:
            tenant_column = _column(tables, table, tenant_column, f"dimension {did} tenant")
        group = str(body.get("group") or body.get("label") or did)
        attrs: dict[str, Attribute] = {}
        for aid, ab in (body.get("attributes") or {}).items():
            aid = _ident(aid, f"dimension {did} attribute")
            attrs[aid] = Attribute(
                id=aid,
                dimension=did,
                column=_column(tables, table, ab.get("column"), f"attribute {aid}"),
                label=str(ab.get("label") or aid),
                group=str(ab.get("group") or group),
            )
        refs: dict[str, Reference] = {}
        for rid, rb in (body.get("references") or {}).items():
            rid = _ident(rid, f"dimension {did} reference")
            rtable = str(rb.get("table") or "")
            refs[rid] = Reference(
                id=rid,
                dimension=did,
                table=rtable,
                fk=_column(tables, table, rb.get("fk"), f"reference {rid} fk"),
                key=_column(tables, rtable, rb.get("key") or "id", f"reference {rid} key"),
                name_column=_column(tables, rtable, rb.get("name_column") or "name", f"reference {rid} name"),
                label=str(rb.get("label") or rid),
                group=str(rb.get("group") or group),
            )
        out[did] = Dimension(
            id=did,
            label=str(body.get("label") or did),
            group=group,
            table=table,
            key=key,
            tenant_column=tenant_column or None,
            attributes=attrs,
            references=refs,
        )
    return out


def _owner_table(model_table: str, base_joins: dict[str, BaseJoin], on: str | None, what: str) -> str:
    if on is None:
        return model_table
    _need(on in base_joins, f"{what}: 'via: {on}' is not one of the model's base_joins")
    return base_joins[on].table


def _parse_model(
    mid: str, body: dict[str, Any], tables: dict[str, Any], dims: dict[str, Dimension]
) -> FactModel:
    table = str(body.get("table") or "")
    _need(table in tables, f"model {mid}: unknown table {table!r}")

    base_joins: dict[str, BaseJoin] = {}
    for alias, bj in (body.get("base_joins") or {}).items():
        alias = _ident(alias, f"model {mid} base_join")
        bt = str(bj.get("table") or "")
        base_joins[alias] = BaseJoin(
            alias=alias,
            table=bt,
            fk=_column(tables, table, bj.get("fk"), f"model {mid} base_join {alias} fk"),
            key=_column(tables, bt, bj.get("key") or "id", f"model {mid} base_join {alias} key"),
        )

    # Tenant isolation: a column on the base table, or a declared path that carries it.
    tenant_via = body.get("tenant_via")
    tenant_column = str(body.get("tenant_column") or "").strip()
    if tenant_via in (None, ""):
        _need(
            bool(tenant_column) and tenant_column in tables[table].c,
            f"model {mid}: no tenant path (needs tenant_column on {table} or tenant_via)",
        )
        tenant_via = None
    elif tenant_via == "dim_product":
        _need("product_id" in tables[table].c, f"model {mid}: tenant_via dim_product needs product_id")
        tenant_column = tenant_column or "tenant_id"
        _column(tables, "dim_product", tenant_column, f"model {mid} tenant_via")
    else:
        _need(tenant_via in base_joins, f"model {mid}: tenant_via {tenant_via!r} is not dim_product or a base_join")
        _need(bool(tenant_column), f"model {mid}: tenant_via {tenant_via} needs tenant_column")
        _column(tables, base_joins[tenant_via].table, tenant_column, f"model {mid} tenant_via")

    rules = tuple(str(r) for r in (body.get("rules") or []))
    for r in rules:
        _need(r in KNOWN_RULES, f"model {mid}: unknown rule {r!r}")

    time: TimeDef | None = None
    if body.get("time"):
        tb = body["time"]
        on = tb.get("via")
        owner = _owner_table(table, base_joins, on, f"model {mid} time")
        floor = str(tb.get("floor") or "day")
        _need(floor in TIME_FLOORS, f"model {mid}: time floor {floor!r} unknown")
        ptc = tb.get("period_type_column")
        if floor == "stored_period_type":
            _need(bool(ptc), f"model {mid}: floor stored_period_type needs period_type_column")
            ptc = _column(tables, owner, ptc, f"model {mid} period_type_column")
        time = TimeDef(
            column=_column(tables, owner, tb.get("column"), f"model {mid} time"),
            on=on,
            floor=floor,
            period_type_column=ptc or None,
        )

    joins: dict[str, Join] = {}
    for did, jb in (body.get("joins") or {}).items():
        _need(did in dims, f"model {mid}: join to unknown dimension {did!r}")
        jb = jb or {}
        on = jb.get("via")
        owner = _owner_table(table, base_joins, on, f"model {mid} join {did}")
        null_keys = str(jb.get("null_keys") or "unassigned")
        _need(null_keys in NULL_KEYS, f"model {mid}: join {did} null_keys {null_keys!r} unknown")
        joins[did] = Join(
            dimension=did,
            fk=_column(tables, owner, jb.get("fk"), f"model {mid} join {did}"),
            on=on,
            role=(str(jb["role"]) if jb.get("role") else None),
            null_keys=null_keys,
        )

    local: dict[str, Local] = {}
    for lid, lb in (body.get("local") or {}).items():
        lid = _ident(lid, f"model {mid} local")
        on = lb.get("via")
        owner = _owner_table(table, base_joins, on, f"model {mid} local {lid}")
        local[lid] = Local(
            id=lid,
            column=_column(tables, owner, lb.get("column"), f"model {mid} local {lid}"),
            on=on,
            label=str(lb.get("label") or lid),
            group=str(lb.get("group") or ""),
            name_column=(
                _column(tables, owner, lb["name_column"], f"model {mid} local {lid} name")
                if lb.get("name_column") is not None else None
            ),
        )

    measures: dict[str, Measure] = {}
    for lid, mb in (body.get("measures") or {}).items():
        lid = _ident(lid, f"model {mid} measure")
        full = f"{mid}.{lid}"
        agg = str(mb.get("agg") or "")
        _need(agg in AGGS, f"measure {full}: agg {agg!r} unknown")
        additivity = str(mb.get("additivity") or "additive")
        _need(additivity in ADDITIVITY, f"measure {full}: additivity {additivity!r} unknown")
        column = mb.get("column")
        rule = mb.get("rule")
        if rule:
            _need(rule in KNOWN_MEASURE_RULES, f"measure {full}: unknown rule {rule!r}")
        elif agg != "count":
            column = _column(tables, table, column, f"measure {full}")
        wnn = mb.get("when_not_null")
        if wnn:
            wnn = _column(tables, table, wnn, f"measure {full} when_not_null")
        latest_per = mb.get("latest_per")
        if agg == "latest_sum":
            _need(additivity == "semi_additive", f"measure {full}: latest_sum must be semi_additive")
            _need(time is not None and time.on is None, f"measure {full}: latest_sum needs a base-table time column")
            latest_per = _column(tables, table, latest_per, f"measure {full} latest_per")
        measures[lid] = Measure(
            id=full,
            model=mid,
            local_id=lid,
            label=str(mb.get("label") or full),
            unit=str(mb.get("unit") or ""),
            agg=agg,
            column=(str(column) if column else None),
            rule=(str(rule) if rule else None),
            when_not_null=wnn or None,
            latest_per=latest_per or None,
            additivity=additivity,
            legacy_key=(str(mb["legacy_key"]) if mb.get("legacy_key") else None),
        )

    return FactModel(
        id=mid,
        label=str(body.get("label") or mid),
        table=table,
        tenant_column=tenant_column,
        tenant_via=tenant_via,
        base_joins=base_joins,
        rules=rules,
        time=time,
        joins=joins,
        local=local,
        measures=measures,
    )


def _parse_calculated(raw: dict[str, Any], measures: dict[str, Measure]) -> dict[str, Calculated]:
    out: dict[str, Calculated] = {}
    # A calculated measure may name another calculated one (difference of a prior): resolve in
    # dependency order, whatever order the file lists them in.
    todo = {str(k): v for k, v in (raw or {}).items()}
    order: list[str] = []
    while todo:
        ready = [
            k
            for k, v in todo.items()
            if all(str(i) in measures or str(i) in order or str(i) not in todo for i in (v.get("inputs") or []))
        ]
        if not ready:
            raise ModelLoadError(f"calculated measures refer to each other in a cycle: {sorted(todo)}")
        for k in ready:
            order.append(k)
            todo.pop(k)
    for cid in order:
        cb = (raw or {})[cid]
        _need(bool(_MEASURE_ID.match(cid)), f"calculated {cid!r}: id must be model.name")
        kind = str(cb.get("kind") or "")
        _need(kind in CALC_KINDS, f"calculated {cid}: kind {kind!r} unknown")
        inputs = tuple(str(x) for x in (cb.get("inputs") or []))
        want = 2 if kind in ("ratio", "difference") else 1
        _need(len(inputs) == want, f"calculated {cid}: {kind} takes {want} input(s)")
        models: set[str] = set()
        units: list[str] = []
        for i in inputs:
            src: Measure | Calculated | None = measures.get(i) or out.get(i)
            _need(src is not None, f"calculated {cid}: unknown input {i!r}")
            assert src is not None
            if isinstance(src, Calculated):
                _need(
                    src.kind in ("prior_period", "prior_year"),
                    f"calculated {cid}: a calculated input must be a prior_period or prior_year",
                )
            else:
                _need(src.additivity != "semi_additive", f"calculated {cid}: {i} is semi-additive")
            models.add(src.model)
            units.append(src.unit)
        _need(len(models) == 1, f"calculated {cid}: inputs must share one model")
        model = models.pop()
        _need(cid.split(".", 1)[0] == model, f"calculated {cid}: id must start with its model {model}")
        if kind == "difference":
            _need(units[0] == units[1], f"calculated {cid}: difference needs the same units")
        additivity = "additive" if kind in ("prior_period", "prior_year", "difference", "running_total") else "non_additive"
        out[cid] = Calculated(
            id=cid,
            model=model,
            kind=kind,
            inputs=inputs,
            label=str(cb.get("label") or cid),
            unit=str(cb.get("unit") or (units[0] if units else "")),
            additivity=additivity,
        )
    return out


def _parse_walls(raw: list[dict[str, Any]], *, check_v1: bool) -> tuple[Wall, ...]:
    v1 = None
    if check_v1:
        from app.semantics.registry import load_catalog

        v1 = load_catalog()
    walls: list[Wall] = []
    seen: set[str] = set()
    for wb in raw or []:
        wid = str(wb.get("id") or "")
        _need(wid.startswith("W-") and wid not in seen, f"wall {wid!r}: id must be unique and start with W-")
        seen.add(wid)
        keeps: list[WallKeep] = []
        for kb in wb.get("keeps") or []:
            keep = WallKeep(
                metric=str(kb.get("metric") or ""),
                grains=frozenset(str(g) for g in (kb.get("grains") or [])),
                text=str(kb.get("text") or ""),
            )
            if v1 is not None:
                metric = v1.metric_by_key(keep.metric)
                _need(metric is not None, f"wall {wid}: keeps unknown v1 metric {keep.metric!r}")
                assert metric is not None
                texts = [ex.reason for ex in metric.refuse_examples if ex.grains == keep.grains]
                _need(
                    keep.text in texts,
                    f"wall {wid}: {keep.metric} {sorted(keep.grains)} text differs from the v1 refuse_example",
                )
            keeps.append(keep)
        walls.append(
            Wall(
                id=wid,
                reason=str(wb.get("reason") or ""),
                trigger=dict(wb.get("trigger") or {}),
                keeps=tuple(keeps),
            )
        )
    return tuple(walls)


def load_model(path: Path | None = None, *, check_v1: bool = True) -> DataModel:
    """Parse and validate a model file; raise ModelLoadError on anything unresolvable."""
    p = path or MODEL_PATH
    raw_text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)
    _need(isinstance(data, dict), f"{p}: not a mapping")
    tables = _tables()

    pb = data.get("period") or {}
    period = PeriodDef(
        label=str(pb.get("label") or "Period"),
        group=str(pb.get("group") or "Time"),
        grains=tuple(str(g) for g in (pb.get("grains") or ["week", "month", "quarter"])),
        default_grain=str(pb.get("default_grain") or "quarter"),
    )
    for g in period.grains:
        _need(g in ("day", "week", "month", "quarter", "year"), f"period grain {g!r} unknown")

    dims = _parse_dimensions(data.get("dimensions") or {}, tables)
    models: dict[str, FactModel] = {}
    for mid, body in (data.get("models") or {}).items():
        mid = _ident(mid, "model")
        models[mid] = _parse_model(mid, body or {}, tables, dims)

    # Breakdown ids are one namespace: a local breakdown may repeat across models only with the
    # same meaning (same id), never collide with a dimension, attribute or reference id.
    global_ids: dict[str, str] = {"period": "period"}
    for dim in dims.values():
        for bid in [dim.id, *dim.attributes, *dim.references]:
            _need(bid not in global_ids, f"breakdown id {bid!r} declared twice")
            global_ids[bid] = f"dimension {dim.id}"
    for model in models.values():
        for lid in model.local:
            _need(
                global_ids.get(lid, "local") == "local",
                f"model {model.id}: local breakdown {lid!r} collides with {global_ids.get(lid)}",
            )
            global_ids[lid] = "local"

    measures: dict[str, Measure] = {}
    for model in models.values():
        for m in model.measures.values():
            measures[m.id] = m
    calculated = _parse_calculated(data.get("calculated") or {}, measures)
    for cid in calculated:
        _need(cid not in measures, f"calculated {cid}: id already a base measure")

    walls = _parse_walls(data.get("walls") or [], check_v1=check_v1)
    pending = tuple(
        {"id": str(p.get("id") or ""), "reason": str(p.get("reason") or "")} for p in (data.get("pending") or [])
    )
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return DataModel(
        version=int(data.get("version") or 1),
        digest=digest,
        source_doc=str(data.get("source_doc") or ""),
        groups=tuple(str(g) for g in (data.get("groups") or [])),
        period=period,
        dimensions=dims,
        models=models,
        calculated=calculated,
        walls=walls,
        pending=pending,
        measures=measures,
    )


@lru_cache(maxsize=1)
def default_model() -> DataModel:
    return load_model()


def clear_model_cache() -> None:
    default_model.cache_clear()
