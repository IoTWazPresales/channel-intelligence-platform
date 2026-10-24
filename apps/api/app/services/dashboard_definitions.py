"""N-0116: stored v2 definitions for dashboard widgets and saved reports (``definition_v2``).

A definition is the v2 query a widget or report runs plus its display options (spec s.2.2):

    {"v": 1, "kind": "model" | "governed",
     "query": {"measures": [...], "breakdowns": [...], "period": {"grain": "week"},
               "filters": {"bu": ["Notebook"]}, "sort": {"by": ..., "dir": ...}, "limit": 500},
     "display": {...optional...},
     "v1_equivalent": bool,            # set by the server, never trusted from the client
     "migrated_from": {...}}           # only on rows the migration script wrote

Checks run the v2 planner (``plan_request``, no SQL), the same code ``/query/v2/explain`` uses. Any
refusal refuses the whole write (400 with the refusal texts). Query dates come from the dashboard
or an explicit S17 fixed window. Otherwise a model definition is planned against a nominal window
(a units-per-week figure is valid on a dashboard, which always supplies from / to, except "all time").

The v1 columns are mirrored (spec s.2.1) so old readers (report builder, exports, v1 delivery) keep
working: when the definition can be expressed in v1, ``metric_key`` is the v1 key and grains /
period_grain / filters are the v1 values; otherwise ``metric_key`` is the first measure id and
grains = [], period_grain = NULL, filters = {}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import HTTPException

from app.query.model.graph import (
    _GOVERNED_FILTER_MAP,
    _GOVERNED_HANDLER_FILTERS,
    MAX_LIMIT,
    Plan,
    Refusal,
    V2Request,
    plan_request,
)
from app.query.model.loader import DataModel, Measure, default_model

DEFINITION_VERSION = 1
_TOP_KEYS = frozenset({"v", "kind", "query", "display", "dashboard", "v1_equivalent", "migrated_from"})
_QUERY_KEYS = frozenset({"measures", "breakdowns", "period", "filters", "sort", "limit"})
_MAX_DISPLAY_BYTES = 8192
_MAX_MIGRATED_BYTES = 4096
_V1_GRAINS = ("week", "month", "quarter")
# Nominal planning window when the widget has no explicit fixed window.
_NOMINAL_FROM = "2000-01-01"


@dataclass
class V1Mirror:
    metric_key: str
    grains: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    period_grain: str | None = None


@dataclass
class CheckedDefinition:
    definition: dict[str, Any]
    plan: Plan
    v1: V1Mirror
    needs_date_range: bool = False

    @property
    def v1_equivalent(self) -> bool:
        return bool(self.definition.get("v1_equivalent"))


class DefinitionRefused(Exception):
    def __init__(self, refusals: list[Refusal]):
        super().__init__(refusals[0].reason if refusals else "definition_v2 refused")
        self.refusals = refusals

    def detail(self) -> dict[str, Any]:
        return {
            "message": self.refusals[0].reason if self.refusals else "definition_v2 refused",
            "refusals": [r.as_dict() for r in self.refusals],
        }

    def http(self) -> HTTPException:
        return HTTPException(status_code=400, detail=self.detail())


def _refuse(reason: str, measure: str | None = None) -> DefinitionRefused:
    return DefinitionRefused([Refusal(measure=measure, reason=reason)])


def _str_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise _refuse(f"definition_v2.query.{name} is a list of ids.")
    return [x.strip() for x in value if x.strip()]


def _json_size(value: Any) -> int:
    return len(json.dumps(value, default=str, separators=(",", ":")))


def _shape(raw: Any) -> tuple[dict[str, Any], V2Request]:
    """Check the JSON shape and build the planner request. Nothing about meaning is decided here."""
    if not isinstance(raw, dict):
        raise _refuse("definition_v2 is an object.")
    unknown = sorted(set(raw) - _TOP_KEYS)
    if unknown:
        raise _refuse(f"Unknown key in definition_v2: {', '.join(unknown)}.")
    if raw.get("v", DEFINITION_VERSION) != DEFINITION_VERSION:
        raise _refuse(f"definition_v2.v must be {DEFINITION_VERSION}.")
    kind = raw.get("kind")
    if kind is not None and kind not in ("model", "governed"):
        raise _refuse("definition_v2.kind is model or governed.")
    q = raw.get("query")
    if not isinstance(q, dict):
        raise _refuse("definition_v2.query is an object.")
    unknown = sorted(set(q) - _QUERY_KEYS)
    if unknown:
        raise _refuse(f"Unknown key in definition_v2.query: {', '.join(unknown)}.")
    measures = _str_list(q.get("measures"), "measures")
    breakdowns = _str_list(q.get("breakdowns"), "breakdowns")
    period = q.get("period") or {}
    if not isinstance(period, dict):
        raise _refuse("definition_v2.query.period is an object.")
    if set(period) - {"grain"}:
        raise _refuse(
            "definition_v2.query.period holds only grain: dates come from the dashboard, a definition never stores period.from / period.to."
        )
    grain = period.get("grain")
    if grain is not None and not isinstance(grain, str):
        raise _refuse("definition_v2.query.period.grain is week, month, quarter or year.")
    filters = q.get("filters") or {}
    if not isinstance(filters, dict):
        raise _refuse("definition_v2.query.filters is an object {breakdown id: value | [values]}.")
    sort = q.get("sort") or {}
    if not isinstance(sort, dict) or set(sort) - {"by", "dir"}:
        raise _refuse("definition_v2.query.sort is {by, dir}.")
    limit = q.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise _refuse("definition_v2.query.limit is a whole number.")
    display = raw.get("display")
    if display is not None:
        if not isinstance(display, dict):
            raise _refuse("definition_v2.display is an object.")
        if _json_size(display) > _MAX_DISPLAY_BYTES:
            raise _refuse(f"definition_v2.display is larger than {_MAX_DISPLAY_BYTES} bytes.")
        if display.get("compare") is not None and not isinstance(display["compare"], bool):
            raise _refuse("definition_v2.display.compare is true or false.")
        top_n = display.get("top_n")
        if top_n is not None and (isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= MAX_LIMIT):
            raise _refuse(f"definition_v2.display.top_n is a whole number from 1 to {MAX_LIMIT}.")
        table = display.get("table")
        if table is not None:
            rules = table.get("rules") if isinstance(table, dict) else None
            if not isinstance(table, dict) or (rules is not None and (not isinstance(rules, list) or len(rules) > 3)):
                raise _refuse("definition_v2.display.table.rules is a list of at most 3 rules.")
    migrated = raw.get("migrated_from")
    if migrated is not None and (not isinstance(migrated, dict) or _json_size(migrated) > _MAX_MIGRATED_BYTES):
        raise _refuse("definition_v2.migrated_from is a small object.")
    req = V2Request(
        measures=measures,
        breakdowns=breakdowns,
        filters=dict(filters),
        period_grain=grain,
        sort_by=sort.get("by"),
        sort_dir=sort.get("dir"),
        limit=limit,
    )
    return raw, req


def _clean(plan: Plan) -> bool:
    return plan.ok and not plan.refusals


def _dashboard_options(raw: Any, dm: DataModel) -> dict[str, Any]:
    """S17 explicit exceptions; they never alter the widget's own query filters or tenant scope."""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or set(raw) - {"ignore_filters", "fixed_window"}:
        raise _refuse("definition_v2.dashboard is {ignore_filters, fixed_window}.")
    out: dict[str, Any] = {}
    ignore = raw.get("ignore_filters", [])
    allowed = (dm.breakdown_ids() - {"period"}) | {"date"}
    if not isinstance(ignore, list) or len(ignore) > len(allowed) or any(not isinstance(k, str) or k not in allowed for k in ignore):
        raise _refuse("definition_v2.dashboard.ignore_filters is a list of catalog filter ids or date.")
    if ignore:
        out["ignore_filters"] = list(dict.fromkeys(ignore))
    fixed = raw.get("fixed_window")
    if fixed is not None:
        if not isinstance(fixed, dict) or set(fixed) != {"from", "to"}:
            raise _refuse("definition_v2.dashboard.fixed_window needs from and to ISO dates.")
        try:
            for value in fixed.values():
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError
        except (ValueError, TypeError):
            raise _refuse("definition_v2.dashboard.fixed_window needs valid ISO dates.") from None
        if fixed["from"] > fixed["to"]:
            raise _refuse("definition_v2.dashboard.fixed_window.from is after to.")
        out["fixed_window"] = dict(fixed)
    return out


def _v1_mirror(dm: DataModel, plan: Plan, req: V2Request, v1_catalog: Any) -> tuple[V1Mirror, bool]:
    """v1 columns for this definition and whether the v1 path answers the same question."""
    from app.semantics.registry import validate_metric_grain

    if plan.governed is not None:
        # v2 runs the v1 handler with the same grains and mapped filters; v1 is the same query.
        return (
            V1Mirror(
                metric_key=plan.governed.key,
                grains=list(plan.breakdowns),
                filters=dict(plan.governed_filters),
                period_grain=plan.period_grain,
            ),
            True,
        )
    first = plan.measures[0].id
    fallback = V1Mirror(metric_key=first)
    if len(plan.measures) != 1:
        return fallback, False
    m = plan.measures[0]
    legacy = m.legacy_key if isinstance(m, Measure) else None
    if not legacy:
        return fallback, False
    grain = plan.period_grain if "period" in plan.breakdowns else None
    if grain is not None and grain not in _V1_GRAINS:
        return fallback, False
    v = validate_metric_grain(legacy, list(plan.breakdowns), catalog=v1_catalog, period_grain=grain)
    if not v.ok or (grain is not None and v.period_grain != grain):
        return fallback, False
    # v1 volume_series reads one value per filter, for these filters only.
    reads, _dates = _GOVERNED_HANDLER_FILTERS["volume_series"]
    v1_filters: dict[str, Any] = {}
    for f in plan.filters:
        if f.breakdown not in reads or len(f.values) != 1 or f.values[0] is None:
            return fallback, False
        v1_filters[_GOVERNED_FILTER_MAP[f.breakdown]] = f.values[0]
    return (
        V1Mirror(metric_key=legacy, grains=list(plan.breakdowns), filters=v1_filters, period_grain=v.period_grain),
        True,
    )


def check_definition(
    raw: Any,
    *,
    tenant_id: str,
    dm: DataModel | None = None,
    v1_catalog: Any = None,
    today: date | None = None,
) -> CheckedDefinition:
    """Validate a definition with the v2 planner; raise ``DefinitionRefused`` on any refusal."""
    from app.semantics.registry import catalog_for_tenant_cached

    dm = dm or default_model()
    v1_catalog = v1_catalog or catalog_for_tenant_cached((tenant_id or "default").strip() or "default")
    raw, req = _shape(raw)
    dashboard = _dashboard_options(raw.get("dashboard"), dm)
    fixed = dashboard.get("fixed_window")
    if fixed:
        req.period_from, req.period_to = fixed["from"], fixed["to"]
    plan = plan_request(dm, req, v1_catalog=v1_catalog)
    needs_dates = False
    if not fixed and not _clean(plan) and plan.governed is None and plan.model is not None:
        # A model definition runs with the dashboard's dates; plan it the way it will run.
        dated = V2Request(**{**req.__dict__, "period_from": _NOMINAL_FROM, "period_to": (today or date.today()).isoformat()})
        dated_plan = plan_request(dm, dated, v1_catalog=v1_catalog)
        if _clean(dated_plan):
            needs_dates = True
        plan = dated_plan
    if not _clean(plan):
        raise DefinitionRefused(plan.refusals or [Refusal(measure=None, reason="definition_v2 refused by the v2 planner.")])

    mirror, v1_equivalent = _v1_mirror(dm, plan, req, v1_catalog)
    if fixed:
        v1_equivalent = False  # v1 delivery cannot carry a stored fixed date window.
    query: dict[str, Any] = {"measures": list(req.measures), "breakdowns": list(plan.breakdowns)}
    if "period" in plan.breakdowns and plan.period_grain:
        query["period"] = {"grain": plan.period_grain}
    elif "period" not in plan.breakdowns and req.period_grain:
        query["period"] = {"grain": req.period_grain}
    if req.filters:
        query["filters"] = dict(req.filters)
    if req.sort_by or req.sort_dir:
        query["sort"] = {k: v for k, v in (("by", req.sort_by), ("dir", req.sort_dir)) if v}
    if req.limit is not None:
        query["limit"] = req.limit
    definition: dict[str, Any] = {
        "v": DEFINITION_VERSION,
        "kind": "governed" if plan.governed is not None else "model",
        "query": query,
    }
    if raw.get("display") is not None:
        definition["display"] = raw["display"]
    if dashboard:
        definition["dashboard"] = dashboard
    definition["v1_equivalent"] = v1_equivalent
    if raw.get("migrated_from") is not None:
        definition["migrated_from"] = raw["migrated_from"]
    return CheckedDefinition(definition=definition, plan=plan, v1=mirror, needs_date_range=needs_dates)


def request_from_definition(
    definition: dict[str, Any], *, period_from: str | None = None, period_to: str | None = None
) -> V2Request:
    """The v2 request, using the caller's dates unless this widget explicitly overrides them."""
    q = definition.get("query") or {}
    period = q.get("period") or {}
    sort = q.get("sort") or {}
    settings = definition.get("dashboard") or {}
    fixed = settings.get("fixed_window")
    if fixed:
        period_from, period_to = fixed["from"], fixed["to"]
    elif "date" in settings.get("ignore_filters", []):
        period_from = period_to = None
    return V2Request(
        measures=list(q.get("measures") or []),
        breakdowns=list(q.get("breakdowns") or []),
        filters=dict(q.get("filters") or {}),
        period_grain=period.get("grain"),
        period_from=period_from,
        period_to=period_to,
        sort_by=sort.get("by"),
        sort_dir=sort.get("dir"),
        limit=q.get("limit"),
    )


def runs_v1(definition: dict[str, Any] | None) -> bool:
    """Spec s.2.5: the v1 path runs when there is no definition or it is v1-equivalent."""
    return definition is None or bool(definition.get("v1_equivalent"))


# ----------------------------------------------------------------------------- dashboard filters

DATE_PRESETS = ("last_13_weeks", "last_26_weeks", "last_52_weeks", "this_year", "last_quarter", "all_time", "custom")
COMPARE = ("none", "previous_period", "previous_year")
_FILTER_TOP_KEYS = frozenset({"date", "compare", "required"})
_MAX_FILTERS_BYTES = 65536


def check_dashboard_filters(raw: Any, *, dm: DataModel | None = None) -> dict[str, Any]:
    """Validate ``dashboard.filters_json`` (spec s.2.3). Values are ids / plain values, lists only."""
    from app.query.calendar_grain import parse_period_bound
    from app.query.model.graph import MAX_FILTER_VALUES

    dm = dm or default_model()
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="filters_json is an object.")
    if _json_size(raw) > _MAX_FILTERS_BYTES:
        raise HTTPException(status_code=400, detail=f"filters_json is larger than {_MAX_FILTERS_BYTES} bytes.")
    breakdowns = set(dm.breakdown_ids()) - {"period"}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "date":
            if not isinstance(value, dict) or set(value) - {"preset", "from", "to"}:
                raise HTTPException(status_code=400, detail="filters_json.date is {preset, from, to}.")
            preset = value.get("preset")
            if preset is not None and preset not in DATE_PRESETS:
                raise HTTPException(status_code=400, detail=f"filters_json.date.preset is one of {', '.join(DATE_PRESETS)}.")
            for b in ("from", "to"):
                v = value.get(b)
                if v not in (None, "") and (not isinstance(v, str) or parse_period_bound(v, end=(b == "to")) is None):
                    raise HTTPException(status_code=400, detail=f"filters_json.date.{b} is a date (YYYY-MM-DD) or null.")
            out["date"] = {"preset": preset, "from": value.get("from") or None, "to": value.get("to") or None}
        elif key == "compare":
            if value not in COMPARE:
                raise HTTPException(status_code=400, detail=f"filters_json.compare is one of {', '.join(COMPARE)}.")
            out["compare"] = value
        elif key == "required":
            if not isinstance(value, list) or any(v not in breakdowns for v in value):
                raise HTTPException(status_code=400, detail="filters_json.required is a list of breakdown ids.")
            out["required"] = list(dict.fromkeys(value))
        elif key in breakdowns:
            if not isinstance(value, list) or len(value) > MAX_FILTER_VALUES:
                raise HTTPException(
                    status_code=400, detail=f"filters_json.{key} is a list of at most {MAX_FILTER_VALUES} values."
                )
            if any(isinstance(v, (dict, list, bool)) for v in value):
                raise HTTPException(status_code=400, detail=f"filters_json.{key} holds ids or plain values.")
            out[key] = list(value)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown filter {key!r} in filters_json; use v2 catalog breakdown ids.")
    return out


# ----------------------------------------------------------------------------- v1 -> v2 (migration)

V1_FILTER_TO_V2 = {"customer_id": "customer", "product_id": "product", "distributor_id": "distributor", "bu": "bu", "site_label": "site_label"}
# Port of apps/web widgetModel.ts visualsFor / effectiveVisual (what a saved v1 widget renders as).
_CATEGORY_GRAINS = frozenset({"customer", "distributor", "product", "bu", "sales_model", "channel", "region", "site_label", "promo_type"})


def visuals_for_v1(grains: list[str]) -> list[str]:
    g = [str(x).strip().lower() for x in grains if str(x).strip()]
    has_period = "period" in g
    cats = [x for x in g if x in _CATEGORY_GRAINS]
    if not g:
        return ["kpi", "table"]
    if has_period and not cats:
        return ["line", "area", "bar", "table", "kpi"]
    if has_period and len(cats) == 1:
        return ["line", "stacked_bar", "area", "table", "kpi"]
    if has_period:
        return ["table", "line", "stacked_bar", "kpi"]
    if len(cats) == 1:
        return ["hbar", "bar", "donut", "pie", "table", "kpi"]
    return ["hbar", "table", "kpi"]


def effective_visual_v1(saved: str, grains: list[str]) -> str:
    ok = visuals_for_v1(grains)
    return saved if saved in ok else ok[0]


class Unmapped(Exception):
    pass


def definition_from_v1(
    *,
    metric_key: str,
    grains: list[str],
    filters: dict[str, Any],
    period_grain: str | None,
    visual: str,
    tenant_id: str,
    at: str,
    script: str = "n0116_migrate_definitions",
    dm: DataModel | None = None,
) -> tuple[CheckedDefinition, str]:
    """Spec s.2.4: the v2 definition of a stored v1 widget / report, and the visual it renders as.

    ``legacy_key`` maps a v1 key to its model measure; every other v1 key is governed with the same
    grains. v1 filter keys map customer_id -> customer, product_id -> product, distributor_id ->
    distributor. The result must be planner-clean AND v1-equivalent with the same v1 columns, or
    ``Unmapped`` is raised (the row then stays on v1, untouched).
    """
    from app.semantics.registry import catalog_for_tenant_cached, validate_metric_grain

    dm = dm or default_model()
    v1_catalog = catalog_for_tenant_cached((tenant_id or "default").strip() or "default")
    legacy = {m.legacy_key: m.id for m in dm.measures.values() if m.legacy_key}
    model_id = legacy.get(metric_key)
    grains = [str(g) for g in (grains or [])]
    v2_filters: dict[str, Any] = {}
    for k, v in (filters or {}).items():
        target = V1_FILTER_TO_V2.get(k)
        if target is None:
            raise Unmapped(f"filter {k!r} has no v2 equivalent (dates are never stored on a definition)")
        v2_filters[target] = [v] if model_id else v
    grain = period_grain if "period" in grains else None
    if model_id and "period" in grains and grain is None:
        v = validate_metric_grain(metric_key, grains, catalog=v1_catalog, period_grain=None)
        grain = v.period_grain
    query: dict[str, Any] = {"measures": [model_id or metric_key], "breakdowns": grains}
    if grain:
        query["period"] = {"grain": grain}
    if v2_filters:
        query["filters"] = v2_filters
    visual_after = effective_visual_v1(visual, grains)
    raw = {
        "v": DEFINITION_VERSION,
        "kind": "model" if model_id else "governed",
        "query": query,
        "migrated_from": {
            "metric_key": metric_key,
            "grains": grains,
            "period_grain": period_grain,
            "visual": visual,
            "filters": dict(filters or {}),
            "at": at,
            "script": script,
        },
    }
    try:
        checked = check_definition(raw, tenant_id=tenant_id, dm=dm, v1_catalog=v1_catalog)
    except DefinitionRefused as exc:
        raise Unmapped(f"v2 planner refused: {exc.refusals[0].reason}") from exc
    if not checked.v1_equivalent:
        raise Unmapped("no v1 equivalent")
    mirror = checked.v1
    if (
        mirror.metric_key != metric_key
        or sorted(mirror.grains) != sorted(grains)
        or (mirror.period_grain or None) != (period_grain or None)
        or dict(mirror.filters) != dict(filters or {})
    ):
        raise Unmapped(f"v1 mirror {mirror} differs from the stored v1 columns")
    return checked, visual_after
