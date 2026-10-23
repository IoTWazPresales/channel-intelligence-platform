"""Explain payload for a v2 query: what was read, how, and under which scope.

Filter VALUES are never shown (names and counts only); the SQL text carries bound parameter
names, never values. Row counts are only the caller's own visible result.
"""

from __future__ import annotations

from typing import Any

from app.query.model.compiler import STATEMENT_TIMEOUT_SQL, Compiled
from app.query.model.graph import Plan
from app.query.model.loader import Calculated, DataModel


def request_scope() -> dict[str, Any]:
    """Scope as the request context holds it (explain-only runs no SQL)."""
    from app.core.product_line_scope import request_product_lines, request_role, scope_csv

    return {
        "product_lines": scope_csv(request_product_lines.get()),
        "role": request_role.get(),
        "source": "request context (bound per transaction by the session listener)",
    }


def build_explain(
    dm: DataModel,
    plan: Plan,
    compiled: Compiled | None,
    *,
    catalog_version: str,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = plan.model
    out: dict[str, Any] = {
        "engine": "model_compiler",
        "catalog_version": catalog_version,
        "models": [model.id] if model else [],
        "model": (
            {"id": model.id, "label": model.label, "table": model.table, "tenant": _tenant_path(model)}
            if model
            else None
        ),
        "measures": [
            {
                "id": m.id,
                "label": m.label,
                "kind": m.kind if isinstance(m, Calculated) else "base",
                **({"inputs": list(m.inputs)} if isinstance(m, Calculated) else {}),
            }
            for m in plan.measures
        ],
        "base_measures": [m.id for m in plan.base_measures],
        "breakdowns": list(plan.breakdowns),
        "walls_checked": sorted(set(plan.walls_checked)),
        "filters": [{"breakdown": f.breakdown, "values": len(f.values)} for f in plan.filters],
        "period": {
            "grain": plan.period_grain,
            "from": plan.period_from.isoformat() if plan.period_from else None,
            "to": plan.period_to.isoformat() if plan.period_to else None,
        },
        "sort": {"by": plan.sort_by, "dir": plan.sort_dir},
        "row_limit": plan.limit,
        "scope": scope or request_scope(),
        "notes": list(plan.notes),
    }
    if compiled is not None:
        out["joins"] = list(compiled.joins)
        out["sql"] = compiled.sql_text()
        out["statement_timeout"] = STATEMENT_TIMEOUT_SQL
        out["notes"].extend(compiled.notes)
    return out


def _tenant_path(model: Any) -> str:
    if model.tenant_via is None:
        return f"{model.table}.{model.tenant_column} = :tenant_id"
    if model.tenant_via == "dim_product":
        return f"INNER JOIN dim_product ON product_id AND dim_product.{model.tenant_column} = :tenant_id"
    return f"{model.base_joins[model.tenant_via].table}.{model.tenant_column} = :tenant_id (inner base join)"
