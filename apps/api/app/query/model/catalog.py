"""Catalog v2 payload (``GET /api/v1/semantics/v2/catalog``).

Measures (base, calculated, governed), breakdowns with labels and groups, the derived breakdowns
each measure allows, walls with their reasons and the v1 texts they keep, and what is pending a
decision. Governed measures are today's v1 catalog metrics at their v1 grains.
"""

from __future__ import annotations

from typing import Any

from app.query.model.graph import (
    MAX_BREAKDOWNS,
    derived_breakdowns,
    filter_refusals,
    governed_honours,
    measure_breakdowns,
    needs_period,
)
from app.query.model.loader import Calculated, DataModel
from app.query.model.tenant_restrictions import (
    counterpart_policy,
    narrowed_breakdowns,
    spec_breakdown_ids,
    spec_keys_of,
)

COMBINATION_RULE = (
    f"Any up to {MAX_BREAKDOWNS} of a measure's breakdowns, one model per query, unless a wall applies; "
    "governed measures allow exactly their listed grain sets. POST /query/v2/explain validates one."
)


def _visible_breakdowns(dm: DataModel, model_id: str, allowed: list[str], catalog: Any, policy: Any) -> list[str]:
    if policy is not None and policy.grains is not None:
        return narrowed_breakdowns(allowed, policy.grains)
    if "product" not in dm.models[model_id].joins:
        return allowed
    out = list(allowed)
    for spec_id in spec_breakdown_ids(catalog):
        if spec_id not in out:
            out.append(spec_id)
    return out


def _breakdowns(dm: DataModel, spec_keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"id": "period", "label": dm.period.label, "group": dm.period.group, "kind": "period", "grains": list(dm.period.grains)}
    ]
    for dim in dm.dimensions.values():
        out.append({"id": dim.id, "label": dim.label, "group": dim.group, "kind": "entity"})
        for a in dim.attributes.values():
            out.append({"id": a.id, "label": a.label, "group": a.group, "kind": "attribute", "of": dim.id})
        for r in dim.references.values():
            out.append({"id": r.id, "label": r.label, "group": r.group, "kind": "entity", "of": dim.id})
    seen = {b["id"] for b in out}
    for model in dm.models.values():
        for loc in model.local.values():
            if loc.id not in seen:
                seen.add(loc.id)
                out.append({"id": loc.id, "label": loc.label, "group": loc.group, "kind": "local", "models": []})
    for b in out:
        if b.get("kind") == "local":
            b["models"] = [m.id for m in dm.models.values() if b["id"] in m.local]
    for key in spec_keys:
        out.append(
            {
                "id": f"spec_{key}",
                "label": f"Spec: {key}",
                "group": "Product",
                "kind": "spec",
                "of": "product",
            }
        )
    return out


def catalog_v2(dm: DataModel, v1_catalog: Any, *, is_admin: bool) -> dict[str, Any]:
    from app.query.handlers import handler_name_for
    from app.query.model.execute import catalog_version_for

    measures: list[dict[str, Any]] = []
    for model in dm.models.values():
        for m in model.measures.values():
            policy = counterpart_policy(dm, m, v1_catalog)
            if policy is not None and policy.hidden and not is_admin:
                continue
            allowed = _visible_breakdowns(dm, m.model, measure_breakdowns(dm, m), v1_catalog, policy)
            entry: dict[str, Any] = {
                "id": m.id,
                "label": policy.label if policy is not None else m.label,
                "unit": m.unit,
                "model": m.model,
                "kind": "base",
                "additivity": m.additivity,
                "breakdowns": allowed,
                "period_grains": list(dm.period.grains) if "period" in allowed else [],
                "requires": [],
                "legacy_key": m.legacy_key,
            }
            if policy is not None and policy.hidden:
                entry["hidden"] = True
            measures.append(entry)
    for c in dm.calculated.values():
        policy = counterpart_policy(dm, c, v1_catalog)
        if policy is not None and policy.hidden and not is_admin:
            continue
        allowed = measure_breakdowns(dm, c)
        for i in c.inputs:
            src = dm.measure(i)
            if src is not None and not isinstance(src, Calculated):
                allowed = [b for b in allowed if b in measure_breakdowns(dm, src)]
        allowed = _visible_breakdowns(dm, c.model, allowed, v1_catalog, policy)
        requires = ["period"] if needs_period(dm, c) else (["period or period.from+to"] if c.kind == "per_week_rate" else [])
        entry = {
            "id": c.id,
            "label": c.label,
            "unit": c.unit,
            "model": c.model,
            "kind": "calculated",
            "calc": c.kind,
            "inputs": list(c.inputs),
            "additivity": c.additivity,
            "breakdowns": allowed,
            "period_grains": list(dm.period.grains) if "period" in allowed else [],
            "requires": requires,
            "legacy_key": None,
        }
        if policy is not None and policy.hidden:
            entry["hidden"] = True
        measures.append(entry)

    legacy = {m.legacy_key for m in dm.measures.values() if m.legacy_key}
    for metric in v1_catalog.metrics:
        if metric.key in legacy:
            continue
        if metric.hidden and not is_admin:
            continue
        measures.append(
            {
                "id": metric.key,
                "label": metric.label,
                "unit": None,
                "model": None,
                "kind": "governed",
                "additivity": None,
                "breakdowns": sorted({g for gs in metric.allowed_grains for g in gs}),
                "grain_sets": [sorted(g) for g in metric.allowed_grains],
                "period_grains": ["week", "month", "quarter"] if metric.calendar_period else [],
                "requires": [],
                "legacy_key": metric.key,
                "metric_id": metric.id,
                "status": metric.status,
                "handler_backed": handler_name_for(metric.key, v1_catalog) is not None,
                "refuse_all": metric.refuse_all,
                "refuse_reason": metric.refuse_reason,
                "hidden": metric.hidden,
                # N-0116 S5: the filters the handler reads (anything else is refused, not ignored).
                "honours": governed_honours(metric, v1_catalog),
            }
        )

    return {
        "version": catalog_version_for(dm, v1_catalog),
        "model_version": dm.version,
        "source_doc": dm.source_doc,
        "groups": list(dm.groups),
        "breakdowns": _breakdowns(dm, spec_keys_of(v1_catalog)),
        "models": [
            {
                "id": m.id,
                "label": m.label,
                "customer_role": m.joins["customer"].role if "customer" in m.joins else None,
                "breakdowns": derived_breakdowns(dm, m),
                # N-0116 S5: why a filter on any other breakdown is refused (the planner's own text).
                "filter_refusals": filter_refusals(dm, m),
            }
            for m in dm.models.values()
        ],
        "measures": measures,
        "walls": [
            {
                "id": w.id,
                "reason": w.reason,
                "keeps": [{"metric": k.metric, "grains": sorted(k.grains), "text": k.text} for k in w.keeps],
            }
            for w in dm.walls
        ],
        "combination_rule": COMBINATION_RULE,
        "limits": {"max_breakdowns": MAX_BREAKDOWNS, "default_limit": 500, "max_limit": 5000},
        "pending": [dict(p) for p in dm.pending],
    }
