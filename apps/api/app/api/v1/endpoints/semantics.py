"""P3-1 semantic layer API — registry browse + metric×grain validation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import Role, get_current_user, get_optional_current_user, normalize_role, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.query.handlers import fact_family_for, handler_name_for
from app.semantics.registry import SemanticCatalog, catalog_for_tenant_cached, load_catalog, validate_metric_grain
from app.services import commercial_tenant_profile as tenant_profile

router = APIRouter()


class ValidateGrainBody(BaseModel):
    metric: str = Field(..., min_length=1, description="Metric key or id (e.g. weeks_of_cover, A3-02)")
    grains: list[str] = Field(default_factory=list, description="Dimension ids to slice by")
    period_grain: str | None = Field(default=None, description="week | month | quarter for calendar-period metrics")


def _user_is_admin(user: dict | None) -> bool:
    if not user:
        return False
    role = user.get("role")
    if role == Role.ADMIN or role == Role.ADMIN.value:
        return True
    if isinstance(role, str):
        return normalize_role(role) == Role.ADMIN
    return False


def _catalog_payload(catalog: SemanticCatalog, user: dict | None) -> dict:
    """Non-admins omit hidden metrics; admins see them flagged so they can un-hide."""
    payload = catalog.as_dict()
    if _user_is_admin(user):
        return payload
    payload["metrics"] = [m for m in payload["metrics"] if not m.get("hidden")]
    return payload


def _catalog_for_request(user: dict | None):
    return catalog_for_tenant_cached(tenant_id_from_user(user))


@router.get("/catalog")
def get_semantic_catalog(user: dict | None = Depends(get_optional_current_user)) -> dict:
    """Full governed metric + dimension registry (config-driven; tenant overlay merged)."""
    return _catalog_payload(_catalog_for_request(user), user)


@router.get("/metrics")
def list_semantic_metrics(
    status: str | None = Query(default=None, description="Filter: implemented|do_not_build|spec_only|partial"),
    user: dict | None = Depends(get_optional_current_user),
) -> dict:
    cat = _catalog_payload(_catalog_for_request(user), user)
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


class OverlayBody(BaseModel):
    """Admin-authored overlay. formula / source_facts / owner_surface are ignored on save."""

    metrics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    composed: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _overlay_editor_payload(tenant_id: str) -> dict:
    platform = load_catalog()
    overlay = tenant_profile.semantic_overlay_for_tenant(tenant_id)
    merged = catalog_for_tenant_cached(tenant_id)
    base_metrics = []
    for metric in platform.metrics:
        family = fact_family_for(metric.key)
        base_metrics.append(
            {
                "id": metric.id,
                "key": metric.key,
                "label": metric.label,
                "allowed_grains": [sorted(g) for g in metric.allowed_grains],
                "fact_family": family,
                "handler_backed": handler_name_for(metric.key) is not None,
                "locked": {
                    "formula": metric.formula,
                    "source_facts": list(metric.source_facts),
                    "owner_surface": metric.owner_surface,
                },
            }
        )
    return {
        "tenant_id": tenant_id,
        "overlay": overlay,
        "base_metrics": base_metrics,
        "merged_version": merged.version,
        "compose_ops": ["ratio", "alias"],
    }


@router.get("/overlay")
def get_semantic_overlay(user: dict = Depends(get_current_user)) -> dict:
    """Current tenant overlay plus platform base metrics for the Settings editor."""
    return _overlay_editor_payload(tenant_id_from_user(user))


@router.put("/overlay")
def put_semantic_overlay(
    body: OverlayBody,
    admin: dict = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Persist governed overlay (admin only). ValueError from the validator → 400."""
    tid = tenant_id_from_user(admin)
    try:
        tenant_profile.save_tenant_profile_overrides(
            tid, {"semantic_overlay": body.model_dump()}
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _overlay_editor_payload(tid)


@router.post("/validate")
def validate_semantic_grain(
    body: ValidateGrainBody,
    user: dict | None = Depends(get_optional_current_user),
) -> dict:
    """Refuse invalid metric×grain combinations with an explanation (P3-1 exit)."""
    tid = tenant_id_from_user(user)
    result = validate_metric_grain(
        body.metric, body.grains, tenant_id=tid, period_grain=body.period_grain
    )
    payload = result.as_dict()
    if not result.ok and result.metric_id is None:
        raise HTTPException(status_code=404, detail=payload)
    return payload
