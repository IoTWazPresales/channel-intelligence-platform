"""P3-1 semantic layer API — registry browse + metric×grain validation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.semantics.registry import catalog_for_tenant_cached, validate_metric_grain

router = APIRouter()


class ValidateGrainBody(BaseModel):
    metric: str = Field(..., min_length=1, description="Metric key or id (e.g. weeks_of_cover, A3-02)")
    grains: list[str] = Field(default_factory=list, description="Dimension ids to slice by")


def _catalog_for_request(user: dict | None):
    return catalog_for_tenant_cached(tenant_id_from_user(user))


@router.get("/catalog")
def get_semantic_catalog(user: dict | None = Depends(get_optional_current_user)) -> dict:
    """Full governed metric + dimension registry (config-driven; tenant overlay merged)."""
    return _catalog_for_request(user).as_dict()


@router.get("/metrics")
def list_semantic_metrics(
    status: str | None = Query(default=None, description="Filter: implemented|do_not_build|spec_only|partial"),
    user: dict | None = Depends(get_optional_current_user),
) -> dict:
    cat = _catalog_for_request(user).as_dict()
    metrics = cat["metrics"]
    if status and status.strip():
        needle = status.strip().lower()
        metrics = [m for m in metrics if str(m.get("status", "")).lower() == needle]
    return {
        "source_doc": cat["source_doc"],
        "version": cat["version"],
        "tenant_id": cat.get("tenant_id"),
        "overlay_applied": cat.get("overlay_applied"),
        "metrics": metrics,
    }


@router.get("/dimensions")
def list_semantic_dimensions(user: dict | None = Depends(get_optional_current_user)) -> dict:
    cat = _catalog_for_request(user).as_dict()
    return {
        "source_doc": cat["source_doc"],
        "version": cat["version"],
        "tenant_id": cat.get("tenant_id"),
        "dimensions": cat["dimensions"],
    }


@router.post("/validate")
def validate_semantic_grain(
    body: ValidateGrainBody,
    user: dict | None = Depends(get_optional_current_user),
) -> dict:
    """Refuse invalid metric×grain combinations with an explanation (P3-1 exit)."""
    tid = tenant_id_from_user(user)
    result = validate_metric_grain(body.metric, body.grains, tenant_id=tid)
    payload = result.as_dict()
    if not result.ok and result.metric_id is None:
        raise HTTPException(status_code=404, detail=payload)
    return payload
