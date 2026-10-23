"""Dashboard widget spec helpers — governed metric + layout, not saved-report pointers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.semantics.registry import validate_metric_grain

# Same set as the ck_dashboard_widget_visual / ck_saved_report_visual checks (migration 0048) and the
# endpoint Visual literals. combo, dual_axis, scatter, pivot added by N-0116 (0048).
WIDGET_VISUAL_ORDER = (
    "kpi", "table", "bar", "hbar", "stacked_bar", "line", "area", "pie", "donut",
    "combo", "dual_axis", "scatter", "pivot",
)
WIDGET_VISUALS = frozenset(WIDGET_VISUAL_ORDER)


def default_layout(index: int) -> dict[str, int]:
    return {"x": (index % 2) * 6, "y": (index // 2) * 8, "w": 6, "h": 8}


def widget_to_dict(row: Any) -> dict[str, Any]:
    layout = dict(row.layout_json) if isinstance(row.layout_json, dict) else None
    return {
        "id": int(row.id),
        "dashboard_id": int(row.dashboard_id),
        "tenant_id": row.tenant_id,
        "title": row.title,
        "visual": row.visual,
        "metric_key": row.metric_key,
        "grains": list(row.grains or []),
        "filters": dict(row.filters or {}),
        "period_grain": row.period_grain,
        "layout_json": layout,
        "saved_report_id": int(row.saved_report_id) if row.saved_report_id is not None else None,
        "sort_order": int(row.sort_order or 0),
        "definition_v2": getattr(row, "definition_v2", None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def validate_widget_query(
    *,
    metric: str,
    grains: list[str],
    period_grain: str | None,
    visual: str,
    tenant_id: str,
) -> Any:
    vis = (visual or "kpi").strip().lower()
    if vis not in WIDGET_VISUALS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid visual {visual!r}. Allowed: {sorted(WIDGET_VISUALS)}.",
        )
    validation = validate_metric_grain(
        metric, grains, tenant_id=tenant_id, period_grain=period_grain
    )
    if not validation.ok:
        raise HTTPException(status_code=400, detail=validation.as_dict())
    return validation
