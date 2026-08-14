"""P3-1 governed semantic layer — metric/dimension registry + grain validity.

Config-driven (YAML). Does not compose SQL — that is P3-2.
Tenant overlays: ``catalog/tenants/{tenant_id}.yaml`` merge metrics by id/key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
_CATALOG_PATH = _CATALOG_DIR / "default.yaml"
_TENANT_DIR = _CATALOG_DIR / "tenants"


@dataclass(frozen=True)
class DimensionDef:
    id: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class RefuseExample:
    grains: frozenset[str]
    reason: str


@dataclass(frozen=True)
class MetricDef:
    id: str
    key: str
    label: str
    status: str
    owner_surface: str
    formula: str
    source_facts: tuple[str, ...]
    allowed_grains: tuple[frozenset[str], ...]
    refuse_all: bool = False
    refuse_reason: str | None = None
    refuse_examples: tuple[RefuseExample, ...] = ()
    notes: str | None = None
    calendar_period: bool = False


@dataclass
class ValidationResult:
    ok: bool
    metric_id: str | None
    metric_key: str | None
    requested_grains: list[str]
    message: str
    allowed_grains: list[list[str]] = field(default_factory=list)
    period_grain: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "metric_id": self.metric_id,
            "metric_key": self.metric_key,
            "requested_grains": self.requested_grains,
            "message": self.message,
            "allowed_grains": self.allowed_grains,
            "period_grain": self.period_grain,
        }


@dataclass(frozen=True)
class SemanticCatalog:
    version: int
    source_doc: str
    dimensions: tuple[DimensionDef, ...]
    metrics: tuple[MetricDef, ...]
    tenant_id: str = "default"
    overlay_applied: bool = False

    def dimension_ids(self) -> frozenset[str]:
        return frozenset(d.id for d in self.dimensions)

    def metric_by_key(self, key: str) -> MetricDef | None:
        k = (key or "").strip().lower()
        for m in self.metrics:
            if m.key.lower() == k or m.id.lower() == k:
                return m
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_doc": self.source_doc,
            "tenant_id": self.tenant_id,
            "overlay_applied": self.overlay_applied,
            "dimensions": [
                {"id": d.id, "label": d.label, "description": d.description} for d in self.dimensions
            ],
            "metrics": [
                {
                    "id": m.id,
                    "key": m.key,
                    "label": m.label,
                    "status": m.status,
                    "owner_surface": m.owner_surface,
                    "formula": m.formula,
                    "source_facts": list(m.source_facts),
                    "allowed_grains": [sorted(g) for g in m.allowed_grains],
                    "refuse_all": m.refuse_all,
                    "refuse_reason": m.refuse_reason,
                    "notes": m.notes,
                    "calendar_period": m.calendar_period,
                }
                for m in self.metrics
            ],
        }


def _parse_metric(raw: dict[str, Any]) -> MetricDef:
    examples: list[RefuseExample] = []
    for ex in raw.get("refuse_examples") or []:
        examples.append(
            RefuseExample(
                grains=frozenset(str(x) for x in (ex.get("grains") or [])),
                reason=str(ex.get("reason") or "Invalid grain combination"),
            )
        )
    grains = tuple(
        frozenset(str(x) for x in grain_list) for grain_list in (raw.get("allowed_grains") or [])
    )
    return MetricDef(
        id=str(raw["id"]),
        key=str(raw["key"]),
        label=str(raw["label"]),
        status=str(raw.get("status") or "spec_only"),
        owner_surface=str(raw.get("owner_surface") or ""),
        formula=str(raw.get("formula") or ""),
        source_facts=tuple(str(x) for x in (raw.get("source_facts") or [])),
        allowed_grains=grains,
        refuse_all=bool(raw.get("refuse_all")),
        refuse_reason=(str(raw["refuse_reason"]) if raw.get("refuse_reason") else None),
        refuse_examples=tuple(examples),
        notes=(str(raw["notes"]) if raw.get("notes") else None),
        calendar_period=bool(raw.get("calendar_period")),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid semantic catalog at {path}")
    return data


def _catalog_from_data(
    data: dict[str, Any],
    *,
    tenant_id: str = "default",
    overlay_applied: bool = False,
) -> SemanticCatalog:
    dims = tuple(
        DimensionDef(
            id=str(d["id"]),
            label=str(d.get("label") or d["id"]),
            description=str(d.get("description") or ""),
        )
        for d in (data.get("dimensions") or [])
    )
    metrics = tuple(_parse_metric(m) for m in (data.get("metrics") or []))
    return SemanticCatalog(
        version=int(data.get("version") or 1),
        source_doc=str(data.get("source_doc") or ""),
        dimensions=dims,
        metrics=metrics,
        tenant_id=tenant_id,
        overlay_applied=overlay_applied,
    )


def load_catalog(path: Path | None = None) -> SemanticCatalog:
    return _catalog_from_data(_load_yaml(path or _CATALOG_PATH))


def _tenant_overlay_path(tenant_id: str) -> Path:
    safe = "".join(c for c in (tenant_id or "default").strip() if c.isalnum() or c in ("-", "_"))
    if not safe or safe.startswith("_"):
        safe = "default"
    return _TENANT_DIR / f"{safe}.yaml"


def _merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge tenant overlay into base: metrics replace by id then key; dimensions append/replace by id."""
    out = dict(base)
    out["version"] = int(overlay.get("version") or base.get("version") or 1)
    if overlay.get("source_doc"):
        out["source_doc"] = overlay["source_doc"]

    dim_by_id: dict[str, dict[str, Any]] = {
        str(d["id"]): dict(d) for d in (base.get("dimensions") or []) if d.get("id")
    }
    for d in overlay.get("dimensions") or []:
        if d.get("id"):
            dim_by_id[str(d["id"])] = dict(d)
    out["dimensions"] = list(dim_by_id.values())

    met_by_id: dict[str, dict[str, Any]] = {}
    met_by_key: dict[str, str] = {}
    for m in base.get("metrics") or []:
        mid = str(m["id"])
        met_by_id[mid] = dict(m)
        met_by_key[str(m.get("key") or "").lower()] = mid
    for m in overlay.get("metrics") or []:
        mid = str(m.get("id") or "")
        key = str(m.get("key") or "").lower()
        if mid and mid in met_by_id:
            met_by_id[mid] = {**met_by_id[mid], **dict(m)}
        elif key and key in met_by_key:
            existing_id = met_by_key[key]
            met_by_id[existing_id] = {**met_by_id[existing_id], **dict(m), "id": existing_id}
        elif mid:
            met_by_id[mid] = dict(m)
            if key:
                met_by_key[key] = mid
        elif key:
            # new metric without id — invent id from key
            mid = key.upper().replace(" ", "_")
            met_by_id[mid] = {**dict(m), "id": mid, "key": m.get("key") or key}
            met_by_key[key] = mid
    out["metrics"] = list(met_by_id.values())
    return out


def catalog_for_tenant(tenant_id: str | None = None) -> SemanticCatalog:
    """Load default catalog merged with optional ``tenants/{tenant_id}.yaml`` overlay."""
    tid = (tenant_id or "default").strip() or "default"
    base = _load_yaml(_CATALOG_PATH)
    overlay_path = _tenant_overlay_path(tid)
    if tid != "default" and overlay_path.is_file():
        overlay = _load_yaml(overlay_path)
        merged = _merge_overlay(base, overlay)
        return _catalog_from_data(merged, tenant_id=tid, overlay_applied=True)
    # Also allow default tenant overlay file named default.yaml
    if overlay_path.is_file() and overlay_path.name != "_example.yaml":
        overlay = _load_yaml(overlay_path)
        if overlay.get("metrics") or overlay.get("dimensions"):
            merged = _merge_overlay(base, overlay)
            return _catalog_from_data(merged, tenant_id=tid, overlay_applied=True)
    return _catalog_from_data(base, tenant_id=tid, overlay_applied=False)


@lru_cache(maxsize=1)
def default_catalog() -> SemanticCatalog:
    return load_catalog()


def clear_catalog_cache() -> None:
    default_catalog.cache_clear()
    catalog_for_tenant_cached.cache_clear()


@lru_cache(maxsize=32)
def catalog_for_tenant_cached(tenant_id: str) -> SemanticCatalog:
    return catalog_for_tenant(tenant_id)


def normalize_grains(grains: list[str] | tuple[str, ...] | set[str] | None) -> frozenset[str]:
    if not grains:
        return frozenset()
    out: set[str] = set()
    for g in grains:
        s = str(g).strip().lower().replace(" ", "_")
        if s:
            out.add(s)
    return frozenset(out)


def validate_metric_grain(
    metric_key: str,
    grains: list[str] | tuple[str, ...] | set[str] | None,
    *,
    catalog: SemanticCatalog | None = None,
    tenant_id: str | None = None,
    period_grain: str | None = None,
) -> ValidationResult:
    """Refuse invalid metric×grain combinations with an explanation (P3-1 exit bar)."""
    cat = catalog or (catalog_for_tenant_cached(tenant_id or "default") if tenant_id else default_catalog())
    requested = sorted(normalize_grains(grains))
    req_set = frozenset(requested)
    raw_key = (metric_key or "").strip()
    if any(sep in raw_key for sep in (",", "+", "|", ";")):
        return ValidationResult(
            ok=False,
            metric_id=None,
            metric_key=metric_key,
            requested_grains=requested,
            message=(
                "One query is one governed metric; sellout_units (DSI) and "
                "cst_sellthrough_units (CST) cannot share a widget."
            ),
        )

    metric = cat.metric_by_key(metric_key)
    if metric is None:
        return ValidationResult(
            ok=False,
            metric_id=None,
            metric_key=metric_key,
            requested_grains=requested,
            message=(
                f"Unknown metric {metric_key!r}. Only metrics in the governed catalog "
                f"({cat.source_doc}) are available — this is not an ad-hoc BI column picker."
            ),
        )

    allowed_sorted = [sorted(g) for g in metric.allowed_grains]
    pg_result = _validate_period_grain(metric, req_set, period_grain)
    if pg_result is not None:
        return ValidationResult(
            ok=False,
            metric_id=metric.id,
            metric_key=metric.key,
            requested_grains=requested,
            message=pg_result,
            allowed_grains=allowed_sorted,
            period_grain=period_grain,
        )
    effective_pg = _effective_period_grain_for_metric(metric, req_set, period_grain)

    if metric.refuse_all:
        return ValidationResult(
            ok=False,
            metric_id=metric.id,
            metric_key=metric.key,
            requested_grains=requested,
            message=metric.refuse_reason
            or f"Metric {metric.key} is not queryable (status={metric.status}).",
            allowed_grains=allowed_sorted,
            period_grain=effective_pg,
        )

    known_dims = cat.dimension_ids() | {"lineup_quarter"}
    unknown = sorted(g for g in req_set if g not in known_dims)
    if unknown:
        return ValidationResult(
            ok=False,
            metric_id=metric.id,
            metric_key=metric.key,
            requested_grains=requested,
            message=f"Unknown dimension(s): {', '.join(unknown)}. Use the dimension registry.",
            allowed_grains=allowed_sorted,
            period_grain=effective_pg,
        )

    for ex in metric.refuse_examples:
        if req_set == ex.grains:
            return ValidationResult(
                ok=False,
                metric_id=metric.id,
                metric_key=metric.key,
                requested_grains=requested,
                message=ex.reason,
                allowed_grains=allowed_sorted,
                period_grain=effective_pg,
            )

    if req_set in metric.allowed_grains:
        return ValidationResult(
            ok=True,
            metric_id=metric.id,
            metric_key=metric.key,
            requested_grains=requested,
            message=f"Valid: {metric.label} at grain {{{', '.join(requested) or '∅'}}}.",
            allowed_grains=allowed_sorted,
            period_grain=effective_pg,
        )

    for ex in metric.refuse_examples:
        if ex.grains <= req_set or req_set <= ex.grains:
            return ValidationResult(
                ok=False,
                metric_id=metric.id,
                metric_key=metric.key,
                requested_grains=requested,
                message=ex.reason,
                allowed_grains=allowed_sorted,
                period_grain=effective_pg,
            )

    allowed_fmt = "; ".join("{" + ", ".join(g) + "}" for g in allowed_sorted) or "(none)"
    return ValidationResult(
        ok=False,
        metric_id=metric.id,
        metric_key=metric.key,
        requested_grains=requested,
        message=(
            f"Invalid grain for {metric.label} ({metric.id}): "
            f"{{{', '.join(requested) or '∅'}}} is not allowed. "
            f"Allowed grains: {allowed_fmt}."
        ),
        allowed_grains=allowed_sorted,
        period_grain=effective_pg,
    )


def _effective_period_grain_for_metric(
    metric: MetricDef, req_set: frozenset[str], period_grain: str | None
) -> str | None:
    from app.query.calendar_grain import effective_period_grain, normalize_period_grain

    if not metric.calendar_period:
        return None
    return effective_period_grain(period_grain, period_in_grains="period" in req_set) or (
        normalize_period_grain(period_grain)
    )


def _validate_period_grain(
    metric: MetricDef, req_set: frozenset[str], period_grain: str | None
) -> str | None:
    from app.query.calendar_grain import (
        PERIOD_GRAINS,
        is_daily_grain,
        normalize_period_grain,
    )

    n = normalize_period_grain(period_grain)
    period_in = "period" in req_set
    if n is None and not period_in:
        return None
    if not metric.calendar_period:
        if n is None:
            return None
        return (
            f"period_grain is only valid for calendar-period metrics (sellout_units, "
            f"cst_sellthrough_units). {metric.key} uses a different period concept "
            f"(A1 lineup quarter stays untouched)."
        )
    if n is not None and not period_in:
        return "period_grain requires period in the grain set."
    if n is None:
        n = "quarter"
    if is_daily_grain(n):
        return "Lowest calendar grain is week; daily is not this unit (transaction_date stays storage-only)."
    if n not in PERIOD_GRAINS:
        return (
            f"Invalid period_grain {n!r}. Allowed: week, month, quarter "
            f"(default quarter when period is in the grain set)."
        )
    return None
