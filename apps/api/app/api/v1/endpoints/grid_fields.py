"""Grid field catalog: the optional columns a Tier A fact grid's column picker offers (N-0034)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.grid_fields import get_spec, grid_field_items

router = APIRouter()


@router.get("/{grid_id}")
async def grid_fields(grid_id: str) -> dict[str, Any]:
    """``{items: [{field, label, group: 'fact' | 'reference', default_hidden}]}`` for one grid."""
    spec = get_spec(grid_id)
    if spec is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_grid", "grid_id": grid_id})
    return {"grid_id": grid_id, "items": grid_field_items(spec)}
