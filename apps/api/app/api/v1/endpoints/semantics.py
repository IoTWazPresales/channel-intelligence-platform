"""P3-1 semantic layer API — registry browse + metric×grain validation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.semantics.registry import default_catalog, validate_metric_grain

router = APIRouter()


class ValidateGrainBody(BaseModel):
    metric: str = Field(..., min_length=1, description="Metric key or id (e.g. weeks_of_cover, A3-02)")
    grains: list[str] = Field(default_factory=list, description="Dimension ids to slice by")


@router.get("/catalog")
def get_semantic_catalog() -> dict:
    """Full governed metric + dimension registry (config-driven)."""
    return default_catalog().as_dict()


@router.get("/metrics")
def list_semantic_metrics(
    status: str | None = Query(default=None, description="Filter: implemented|do_not_build|spec_only"),
) -> dict:
    cat = default_catalog().as_dict()
    metrics = cat["metrics"]
    if status and status.strip():
        needle = status.strip().lower()
        metrics = [m for m in metrics if str(m.get("status", "")).lower() == needle]
    return {"source_doc": cat["source_doc"], "version": cat["version"], "metrics": metrics}


@router.get("/dimensions")
def list_semantic_dimensions() -> dict:
    cat = default_catalog().as_dict()
    return {"source_doc": cat["source_doc"], "version": cat["version"], "dimensions": cat["dimensions"]}


@router.post("/validate")
def validate_semantic_grain(body: ValidateGrainBody) -> dict:
    """Refuse invalid metric×grain combinations with an explanation (P3-1 exit)."""
    result = validate_metric_grain(body.metric, body.grains)
    payload = result.as_dict()
    if not result.ok and result.metric_id is None:
        raise HTTPException(status_code=404, detail=payload)
    return payload
