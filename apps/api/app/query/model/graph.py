"""Derived breakdowns, walls and request validation for v2 queries.

A model measure allows: period (when the model has a time column), every join, every attribute
and reference of a joined dimension, and every local breakdown, in any combination of up to 3,
minus walls. One model per query. Governed measures (today's v1 handlers) allow exactly their v1
``allowed_grains`` and are validated by ``registry.validate_metric_grain`` itself, so their
refusal texts are the v1 texts.

Nothing here touches the database. Every id in a request is resolved by dictionary lookup in the
loaded model (or the v1 catalog for governed measures); an id that is not found is refused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.query.calendar_grain import is_daily_grain, normalize_period_grain, parse_period_bound
from app.query.model.loader import Calculated, DataModel, FactModel, Measure

MAX_BREAKDOWNS = 3
MAX_MEASURES = 20
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
MAX_FILTER_VALUES = 1000
MAX_FILTER_TEXT = 256

# Same text as registry._validate_period_grain (v1): day stays refused until decision 1 is taken.
DAILY_REFUSAL = "Lowest calendar grain is week; daily is not this unit (transaction_date stays storage-only)."

ENTITY_BREAKDOWNS = frozenset({"product", "customer", "distributor", "case"})


@dataclass
class V2Request:
    measures: list[str]
    breakdowns: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    period_grain: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    sort_by: str | None = None
    sort_dir: str | None = None
    limit: int | None = None

    def canonical(self) -> dict[str, Any]:
        """Everything that changes the answer, in a stable form (cache key, explain)."""
        filters: dict[str, Any] = {}
        for k in sorted(self.filters or {}):
            v = self.filters[k]
            filters[str(k)] = sorted((str(x) for x in v), key=str) if isinstance(v, (list, tuple, set)) else v
        return {
            "measures": [str(m) for m in self.measures],
            "breakdowns": [str(b) for b in self.breakdowns],
            "filters": filters,
            "period": {"grain": self.period_grain, "from": self.period_from, "to": self.period_to},
            "sort": {"by": self.sort_by, "dir": self.sort_dir},
            "limit": self.limit,
        }


@dataclass
class Refusal:
    measure: str | None
    reason: str
    wall: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"measure": self.measure, "reason": self.reason, "wall": self.wall}


@dataclass
class ResolvedFilter:
    breakdown: str
    values: list[Any]
    is_list: bool


@dataclass
class Plan:
    model: FactModel | None = None
    measures: list[Measure | Calculated] = field(default_factory=list)
    base_measures: list[Measure] = field(default_factory=list)
    breakdowns: list[str] = field(default_factory=list)
    filters: list[ResolvedFilter] = field(default_factory=list)
    period_grain: str | None = None
    period_from: date | None = None
    period_to: date | None = None
    sort_by: str | None = None
    sort_dir: str = "desc"
    limit: int = DEFAULT_LIMIT
    needs_prev: bool = False
    walls_checked: list[str] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    governed: Any = None  # v1 MetricDef when the single measure is a governed metric
    governed_filters: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.governed is not None or bool(self.measures)


# ----------------------------------------------------------------------------- derivation


def _wall_blocks(dm: DataModel, model_id: str, breakdown: str) -> Any:
    for w in dm.walls:
        t = w.trigger
        if t.get("breakdown") == breakdown:
            models = t.get("models")
            if not models or model_id in models:
                return w
    return None


def derived_breakdowns(dm: DataModel, model: FactModel) -> list[str]:
    """Breakdowns a model allows, in display order, walls removed."""
    out: list[str] = []
    if model.time is not None:
        out.append("period")
    for did in model.joins:
        dim = dm.dimensions[did]
        out.append(did)
        out.extend(dim.attributes)
        out.extend(dim.references)
    out.extend(model.local)
    seen: set[str] = set()
    result: list[str] = []
    for b in out:
        if b in seen:
            continue
        seen.add(b)
        # A wall naming this model removes the breakdown even where a join would allow it; a wall
        # naming no model only explains why other models lack it (see _breakdown_refusal).
        wall = _wall_blocks(dm, model.id, b)
        if wall is not None and wall.trigger.get("models"):
            continue
        result.append(b)
    return result


def measure_breakdowns(dm: DataModel, m: Measure | Calculated) -> list[str]:
    allowed = derived_breakdowns(dm, dm.models[m.model])
    if isinstance(m, Measure) and m.additivity == "semi_additive":
        allowed = [b for b in allowed if b != "period"]
    return allowed


def needs_period(dm: DataModel, m: Measure | Calculated) -> bool:
    """prior_period / pct_change (and a difference over a prior) need a period breakdown."""
    if not isinstance(m, Calculated):
        return False
    if m.kind in ("prior_period", "pct_change"):
        return True
    return any(needs_period(dm, dm.measure(i)) for i in m.inputs if dm.measure(i) is not None)  # type: ignore[arg-type]


def base_inputs(dm: DataModel, m: Measure | Calculated) -> list[Measure]:
    if isinstance(m, Measure):
        return [m]
    out: list[Measure] = []
    for i in m.inputs:
        src = dm.measure(i)
        if src is not None:
            for b in base_inputs(dm, src):
                if b not in out:
                    out.append(b)
    return out


# ----------------------------------------------------------------------------- validation


def _norm_id(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _coerce_values(bid: str, raw: Any) -> tuple[list[Any] | None, str | None]:
    is_list = isinstance(raw, (list, tuple))
    values = list(raw) if is_list else [raw]
    if not values:
        return None, f"Filter {bid!r} has an empty list."
    if len(values) > MAX_FILTER_VALUES:
        return None, f"Filter {bid!r} has {len(values)} values; at most {MAX_FILTER_VALUES}."
    out: list[Any] = []
    for v in values:
        if bid in ENTITY_BREAKDOWNS or bid in ("region", "channel"):
            if isinstance(v, bool) or v is None:
                return None, f"Filter {bid!r} takes ids (whole numbers)."
            try:
                iv = int(str(v).strip())
            except (TypeError, ValueError):
                return None, f"Filter {bid!r} takes ids (whole numbers); {v!r} is not one."
            if not (-(2**31) <= iv < 2**31):
                return None, f"Filter {bid!r}: id {iv} is out of range."
            out.append(iv)
        else:
            if v is None:
                out.append(None)
                continue
            if isinstance(v, (dict, list, tuple)) or (isinstance(v, float) and not math.isfinite(v)):
                return None, f"Filter {bid!r} takes plain values."
            s = str(v)
            if len(s) > MAX_FILTER_TEXT:
                return None, f"Filter {bid!r}: value longer than {MAX_FILTER_TEXT} characters."
            out.append(s)
    return out, None


def _legacy_exact(dm: DataModel, m: Measure | Calculated, req_set: frozenset[str]) -> Refusal | None:
    legacy = m.legacy_key if isinstance(m, Measure) else None
    if not legacy:
        return None
    for w in dm.walls:
        for keep in w.keeps:
            if keep.metric == legacy and keep.grains == req_set:
                return Refusal(measure=m.id, reason=keep.text, wall=w.id)
    return None


def _breakdown_refusal(dm: DataModel, model: FactModel, b: str, allowed: list[str]) -> Refusal | None:
    if b in allowed:
        return None
    wall = _wall_blocks(dm, model.id, b)
    if wall is not None:
        return Refusal(measure=None, reason=wall.reason, wall=wall.id)
    if b not in dm.breakdown_ids():
        return Refusal(measure=None, reason=f"Unknown breakdown {b!r}. Use the breakdowns in the v2 catalog.")
    return Refusal(measure=None, reason=f"{dm.breakdown_label(b)[0]} is not a breakdown of {model.label}.")


def plan_request(dm: DataModel, req: V2Request, *, v1_catalog: Any) -> Plan:
    """Validate a v2 request into a compile plan (or refusals). No database access."""
    plan = Plan()
    raw_measures = [str(m).strip() for m in (req.measures or []) if str(m).strip()]
    if not raw_measures:
        plan.refusals.append(Refusal(measure=None, reason="Name at least one measure."))
        return plan
    if len(raw_measures) > MAX_MEASURES:
        plan.refusals.append(Refusal(measure=None, reason=f"At most {MAX_MEASURES} measures in one query."))
        return plan
    measure_ids: list[str] = []
    for mid in raw_measures:
        if mid not in measure_ids:
            measure_ids.append(mid)

    breakdowns: list[str] = []
    for b in req.breakdowns or []:
        nb = _norm_id(b)
        if nb and nb not in breakdowns:
            breakdowns.append(nb)
    req_set = frozenset(breakdowns)

    # Resolve measures: model measure, calculated, governed (v1 key not answered by a model measure).
    legacy_keys = {m.legacy_key for m in dm.measures.values() if m.legacy_key}
    resolved: list[Measure | Calculated] = []
    governed: list[Any] = []
    for mid in measure_ids:
        m = dm.measure(mid)
        if m is not None:
            resolved.append(m)
            continue
        metric = v1_catalog.metric_by_key(mid) if v1_catalog is not None else None
        if metric is not None and metric.key not in legacy_keys:
            governed.append(metric)
            continue
        if metric is not None and metric.key in legacy_keys:
            target = next(m.id for m in dm.measures.values() if m.legacy_key == metric.key)
            plan.refusals.append(Refusal(measure=mid, reason=f"Use {target} for {metric.key} in v2 queries."))
            continue
        plan.refusals.append(
            Refusal(measure=mid, reason=f"Unknown measure {mid!r}. Only measures in the v2 catalog can be queried.")
        )

    if governed:
        if len(governed) > 1 or resolved:
            plan.refusals.append(
                Refusal(
                    measure=None,
                    reason="A governed metric is answered on its own: send one query per governed metric.",
                )
            )
            return plan
        return _plan_governed(dm, req, plan, governed[0], breakdowns, v1_catalog)

    if not resolved:
        return plan

    models = {m.model for m in resolved}
    if len(models) > 1:
        roles = {dm.models[x].joins["customer"].role for x in models if "customer" in dm.models[x].joins}
        wall = dm.wall("W-CUSTOMER-ROLE")
        plan.walls_checked.append("W-CUSTOMER-ROLE")
        reason = f"One query reads one model ({', '.join(sorted(models))}): send one query per model."
        if len(roles) > 1 and wall is not None:
            reason = f"{reason} {wall.reason}"
        plan.refusals.append(Refusal(measure=None, reason=reason, wall="W-CUSTOMER-ROLE" if len(roles) > 1 else None))
        return plan
    model = dm.models[models.pop()]
    plan.model = model
    plan.walls_checked.extend(
        w.id for w in dm.walls if w.trigger.get("breakdown") or w.trigger.get("semi_additive_with")
    )
    plan.walls_checked.append("W-CUSTOMER-ROLE")

    if len(breakdowns) > MAX_BREAKDOWNS:
        plan.refusals.append(Refusal(measure=None, reason=f"At most {MAX_BREAKDOWNS} breakdowns at once."))
        return plan

    allowed = derived_breakdowns(dm, model)
    request_refusal: Refusal | None = None
    for b in breakdowns:
        request_refusal = _breakdown_refusal(dm, model, b, allowed)
        if request_refusal is not None:
            break

    # Period: grain and window.
    period_in = "period" in req_set
    grain = normalize_period_grain(req.period_grain)
    if period_in:
        if grain is None:
            grain = dm.period.default_grain
        if is_daily_grain(grain):
            plan.refusals.append(Refusal(measure=None, reason=DAILY_REFUSAL))
            return plan
        if grain not in dm.period.grains:
            plan.refusals.append(
                Refusal(
                    measure=None,
                    reason=f"Invalid period grain {grain!r}. Allowed: {', '.join(dm.period.grains)}.",
                )
            )
            return plan
        plan.period_grain = grain
    elif grain is not None:
        plan.notes.append("period.grain ignored: period is not a breakdown.")
    for attr, raw in (("from", req.period_from), ("to", req.period_to)):
        if raw in (None, ""):
            continue
        d = parse_period_bound(raw, end=(attr == "to"))
        if d is None:
            plan.refusals.append(Refusal(measure=None, reason=f"period.{attr} {raw!r} is not a date (YYYY-MM-DD or 26Q2)."))
            return plan
        setattr(plan, "period_from" if attr == "from" else "period_to", d)
    if plan.period_from and plan.period_to and plan.period_from > plan.period_to:
        plan.refusals.append(Refusal(measure=None, reason="period.from is after period.to."))
        return plan
    if (plan.period_from or plan.period_to) and model.time is None:
        plan.refusals.append(Refusal(measure=None, reason=f"{model.label} has no date to filter on."))
        return plan

    # Per measure: v1 exact text first (same order as registry.validate_metric_grain), then walls.
    for m in resolved:
        exact = _legacy_exact(dm, m, req_set)
        if exact is not None:
            plan.refusals.append(exact)
            continue
        if request_refusal is not None:
            plan.refusals.append(Refusal(measure=m.id, reason=request_refusal.reason, wall=request_refusal.wall))
            continue
        if isinstance(m, Measure) and m.additivity == "semi_additive" and period_in:
            wall = dm.wall("W-SNAPSHOT-NOT-SUMMED")
            plan.refusals.append(
                Refusal(measure=m.id, reason=wall.reason if wall else "Stock is never summed across dates.", wall="W-SNAPSHOT-NOT-SUMMED")
            )
            continue
        if needs_period(dm, m) and not period_in:
            plan.refusals.append(Refusal(measure=m.id, reason=f"{m.label} needs period as a breakdown."))
            continue
        if isinstance(m, Calculated) and m.kind == "per_week_rate" and not period_in and not (
            plan.period_from and plan.period_to
        ):
            plan.refusals.append(
                Refusal(measure=m.id, reason=f"{m.label} needs period as a breakdown or both period.from and period.to.")
            )
            continue
        plan.measures.append(m)

    if not plan.measures:
        return plan

    # Filters: only breakdowns this model allows; walls apply to filters as to breakdowns.
    for raw_key, raw_val in (req.filters or {}).items():
        bid = _norm_id(raw_key)
        if bid == "period":
            plan.refusals.append(Refusal(measure=None, reason="Filter dates with period.from / period.to."))
            plan.measures = []
            return plan
        r = _breakdown_refusal(dm, model, bid, allowed)
        if r is not None:
            plan.refusals.append(Refusal(measure=None, reason=f"Filter {bid!r}: {r.reason}", wall=r.wall))
            plan.measures = []
            return plan
        values, err = _coerce_values(bid, raw_val)
        if err is not None:
            plan.refusals.append(Refusal(measure=None, reason=err))
            plan.measures = []
            return plan
        plan.filters.append(ResolvedFilter(breakdown=bid, values=values or [], is_list=isinstance(raw_val, (list, tuple))))

    # Sort: an id from this request only.
    valid_ids = [m.id for m in plan.measures]
    if req.sort_by not in (None, ""):
        by = str(req.sort_by).strip()
        if by not in valid_ids and _norm_id(by) not in breakdowns:
            plan.refusals.append(Refusal(measure=None, reason=f"Sort by {by!r}: sort by one of the requested measures or breakdowns."))
            plan.measures = []
            return plan
        plan.sort_by = by if by in valid_ids else _norm_id(by)
    default_asc = plan.sort_by in breakdowns or (plan.sort_by is None and "period" in breakdowns)
    direction = _norm_id(req.sort_dir) or ("asc" if default_asc else "desc")
    if direction not in ("asc", "desc"):
        plan.refusals.append(Refusal(measure=None, reason="sort.dir is asc or desc."))
        plan.measures = []
        return plan
    plan.sort_dir = direction

    # Limit: refused above the maximum, never clamped.
    if req.limit is None:
        plan.limit = DEFAULT_LIMIT
    else:
        try:
            lim = int(req.limit)
        except (TypeError, ValueError):
            lim = -1
        if lim < 1:
            plan.refusals.append(Refusal(measure=None, reason="limit must be a whole number of at least 1."))
            plan.measures = []
            return plan
        if lim > MAX_LIMIT:
            plan.refusals.append(
                Refusal(
                    measure=None,
                    reason=f"limit {lim} is above the maximum of {MAX_LIMIT} rows; narrow the query (refused, not clamped).",
                )
            )
            plan.measures = []
            return plan
        plan.limit = lim

    plan.breakdowns = breakdowns
    base: list[Measure] = []
    for m in plan.measures:
        for b in base_inputs(dm, m):
            if b not in base:
                base.append(b)
    plan.base_measures = base
    plan.needs_prev = any(needs_period(dm, m) for m in plan.measures)
    if model.time is not None and model.time.floor == "stored_period_type" and period_in:
        plan.walls_checked.append("W-ONE-STORED-PERIOD")
    return plan


_GOVERNED_FILTER_MAP = {
    "customer": "customer_id",
    "product": "product_id",
    "distributor": "distributor_id",
    "bu": "bu",
    "site_label": "site_label",
}

# The filters each v1 handler actually reads (handlers/a1_pve.py, a2_cpor.py, a3_stock.py,
# volume_series.py). Any other filter is refused, never accepted and silently ignored, so a figure
# never looks filtered when it is not. ``dates``: whether period.from / period.to reach the handler.
_GOVERNED_HANDLER_FILTERS: dict[str, tuple[frozenset[str], bool]] = {
    "a1_pve": (frozenset({"bu"}), True),
    "a2_cpor": (frozenset({"customer", "bu"}), True),  # the handler itself refuses a period (all-time)
    "a3_stock": (frozenset({"distributor", "product"}), False),
    "volume_series": (frozenset({"customer", "product", "distributor", "site_label"}), True),
}
_FAMILY_HANDLER = {"a1": "a1_pve", "a2": "a2_cpor", "a3": "a3_stock", "volume": "volume_series"}
# Handlers whose dates reach them but who refuse any period themselves (a2_cpor.py: all-time
# portfolio). The dates pass through (so the handler's own text is the refusal); the catalog says so
# with ``honours.all_time_only`` so a builder does not send a date range it knows will be refused.
_GOVERNED_ALL_TIME = frozenset({"a2_cpor"})


def governed_honours(metric: Any, v1_catalog: Any) -> dict[str, Any]:
    """What a governed measure is filtered by, from the same table ``_plan_governed`` enforces.

    ``filters``: the v2 filter ids the handler reads (one value each); ``dates``: whether
    period.from / period.to reach the handler; ``all_time_only``: the handler refuses any period.
    """
    handler = _governed_handler(metric, v1_catalog)
    reads, reads_dates = _GOVERNED_HANDLER_FILTERS.get(handler or "", (frozenset(), False))
    return {
        "handler": handler,
        "filters": sorted(b for b in reads if b in _GOVERNED_FILTER_MAP),
        "dates": bool(reads_dates),
        "all_time_only": handler in _GOVERNED_ALL_TIME,
        "one_value_per_filter": True,
    }


def filter_refusals(dm: DataModel, model: FactModel) -> dict[str, str]:
    """{breakdown id: reason} for every breakdown a filter on this model would be refused for.

    Built with the planner's own ``_breakdown_refusal``; the planner's filter refusal reads
    ``Filter '<id>': <reason>`` with exactly this reason. ``period`` is not a filter (dates use
    period.from / period.to), so it is never listed.
    """
    allowed = derived_breakdowns(dm, model)
    out: dict[str, str] = {}
    for bid in sorted(dm.breakdown_ids()):
        if bid == "period":
            continue
        r = _breakdown_refusal(dm, model, bid, allowed)
        if r is not None:
            out[bid] = r.reason
    return out


def _governed_handler(metric: Any, v1_catalog: Any) -> str | None:
    from app.query.handlers import fact_family_for, handler_name_for

    name = handler_name_for(metric.key, v1_catalog)
    if name == "composed" and getattr(metric, "compose", None) is not None and metric.compose.inputs:
        return _FAMILY_HANDLER.get(fact_family_for(metric.compose.inputs[0]) or "")
    return name


def _limit_refusal(req: V2Request, plan: Plan) -> Refusal | None:
    """Limit: refused above the maximum, never clamped (model and governed measures alike)."""
    if req.limit is None:
        plan.limit = DEFAULT_LIMIT
        return None
    try:
        lim = int(req.limit)
    except (TypeError, ValueError):
        lim = -1
    if lim < 1:
        return Refusal(measure=None, reason="limit must be a whole number of at least 1.")
    if lim > MAX_LIMIT:
        return Refusal(
            measure=None,
            reason=f"limit {lim} is above the maximum of {MAX_LIMIT} rows; narrow the query (refused, not clamped).",
        )
    plan.limit = lim
    return None


def _plan_governed(
    dm: DataModel, req: V2Request, plan: Plan, metric: Any, breakdowns: list[str], v1_catalog: Any
) -> Plan:
    """A v1 governed metric: v1 validation and v1 handler, unchanged; v2 only reshapes."""
    from app.semantics.registry import validate_metric_grain

    plan.walls_checked.extend(
        w.id for w in dm.walls if w.trigger.get("governed") or w.trigger.get("governed_refuse_all") or w.keeps
    )
    grain = req.period_grain if "period" in breakdowns else None
    v = validate_metric_grain(metric.key, breakdowns, catalog=v1_catalog, period_grain=grain)
    if not v.ok:
        wall = None
        for w in dm.walls:
            for keep in w.keeps:
                if keep.metric == metric.key and keep.text == v.message:
                    wall = w.id
                    break
            if wall:
                break
        if wall is None and metric.refuse_all:
            wall = "W-NOT-COMPUTABLE"
        plan.refusals.append(Refusal(measure=metric.key, reason=v.message, wall=wall))
        return plan
    handler = _governed_handler(metric, v1_catalog)
    reads, reads_dates = _GOVERNED_HANDLER_FILTERS.get(handler or "", (frozenset(), False))
    filters: dict[str, Any] = {}
    for raw_key, raw_val in (req.filters or {}).items():
        bid = _norm_id(raw_key)
        target = _GOVERNED_FILTER_MAP.get(bid)
        if target is None or bid not in reads:
            plan.refusals.append(
                Refusal(measure=metric.key, reason=f"{metric.label} cannot be filtered by {bid}: the figure is worked out without it.")
            )
            return plan
        if isinstance(raw_val, (list, tuple, dict)):
            plan.refusals.append(
                Refusal(measure=metric.key, reason=f"{metric.label} takes one {bid} at a time.")
            )
            return plan
        filters[target] = raw_val
    if (req.period_from or req.period_to) and not reads_dates:
        plan.refusals.append(
            Refusal(measure=metric.key, reason=f"{metric.label} is the latest position, not a period figure; it cannot be filtered by dates.")
        )
        return plan
    if req.period_from:
        filters["period_from"] = req.period_from
    if req.period_to:
        filters["period_to"] = req.period_to
    # Sort and limit apply to governed rows too (execute._run_governed).
    if req.sort_by not in (None, ""):
        by = str(req.sort_by).strip()
        if by != metric.key and _norm_id(by) not in breakdowns:
            plan.refusals.append(Refusal(measure=None, reason=f"Sort by {by!r}: sort by one of the requested measures or breakdowns."))
            return plan
        plan.sort_by = by if by == metric.key else _norm_id(by)
    default_asc = plan.sort_by in breakdowns or (plan.sort_by is None and "period" in breakdowns)
    direction = _norm_id(req.sort_dir) or ("asc" if default_asc else "desc")
    if direction not in ("asc", "desc"):
        plan.refusals.append(Refusal(measure=None, reason="sort.dir is asc or desc."))
        return plan
    plan.sort_dir = direction
    limit_refusal = _limit_refusal(req, plan)
    if limit_refusal is not None:
        plan.refusals.append(limit_refusal)
        return plan
    plan.governed = metric
    plan.governed_filters = filters
    plan.breakdowns = breakdowns
    plan.period_grain = v.period_grain
    return plan
