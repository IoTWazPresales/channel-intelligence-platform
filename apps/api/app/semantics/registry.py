"""P3-1 governed semantic layer — metric/dimension registry + grain validity.

Config-driven (YAML). Does not compose SQL — that is P3-2.
Tenant overlays: ``tenant_profiles/{tenant_id}.json`` key ``semantic_overlay``
(no-deploy). Package YAML ``catalog/tenants/{tenant_id}.yaml`` is back-compat
only and runs through the same field-whitelist merge — it cannot rewrite
``formula`` / ``source_facts`` / ``owner_surface`` or invent metrics.
"""

from __future__ import annotations

import hashlib
import json
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
class ComposeDef:
    """Tenant-composed metric: ratio or alias over handler-backed inputs."""

    op: str
    inputs: tuple[str, ...]
    grain: frozenset[str]


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
    hidden: bool = False
    compose: ComposeDef | None = None


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
                    "hidden": m.hidden,
                    **(
                        {
                            "compose": {
                                "op": m.compose.op,
                                "inputs": list(m.compose.inputs),
                                "grain": sorted(m.compose.grain),
                            }
                        }
                        if m.compose is not None
                        else {}
                    ),
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
    compose_def: ComposeDef | None = None
    raw_compose = raw.get("compose")
    if isinstance(raw_compose, dict) and raw_compose.get("op") and raw_compose.get("inputs"):
        compose_def = ComposeDef(
            op=str(raw_compose["op"]).strip().lower(),
            inputs=tuple(str(x).strip().lower() for x in (raw_compose.get("inputs") or []) if str(x).strip()),
            grain=_grain_frozenset(raw_compose.get("grain")),
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
        hidden=bool(raw.get("hidden")),
        compose=compose_def,
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


def _grain_frozenset(items: object) -> frozenset[str]:
    if not isinstance(items, (list, tuple, set, frozenset)):
        return frozenset()
    out: set[str] = set()
    for item in items:
        token = str(item).strip().lower().replace(" ", "_")
        if token:
            out.add(token)
    return frozenset(out)


def _patches_from_overlay_doc(overlay: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract governed patches from YAML-list or profile-dict overlay documents."""
    if not isinstance(overlay, dict):
        return {}
    raw = overlay.get("metrics")
    patches: dict[str, dict[str, Any]] = {}

    def _take(ident: str, body: dict[str, Any]) -> None:
        if body.get("compose"):
            return
        patch: dict[str, Any] = {}
        if "label" in body and str(body.get("label") or "").strip():
            patch["label"] = str(body["label"]).strip()
        if "hidden" in body:
            patch["hidden"] = bool(body.get("hidden"))
        if "allowed_grains" in body and isinstance(body.get("allowed_grains"), list):
            patch["allowed_grains"] = body["allowed_grains"]
        if ident and patch:
            patches[ident] = patch

    if isinstance(raw, dict):
        for ident, body in raw.items():
            if isinstance(body, dict):
                _take(str(ident).strip(), body)
    elif isinstance(raw, list):
        for body in raw:
            if not isinstance(body, dict):
                continue
            ident = str(body.get("id") or body.get("key") or "").strip()
            _take(ident, body)
    return patches


def _fold_overlay_version(base_version: int, overlay_state: dict[str, Any]) -> int:
    """Fold overlay revision into catalog.version so query cache cannot serve stale labels."""
    if not overlay_state:
        return int(base_version)
    payload = json.dumps(overlay_state, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    fold = int.from_bytes(digest[:8], "big") % 100_000_000
    return int(base_version) * 100_000_000 + fold


def _governed_merge(
    base: dict[str, Any], patches: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Apply field-whitelist patches. Never invents metrics or rewrites formula/source_facts/owner_surface.

    Invalid grain restricts drop that patch (FLAG != BLOCK). Returns (merged, applied_patches).
    Overlay dimensions are ignored — tenants cannot add unbacked dimensions.
    """
    out = dict(base)
    met_by_id: dict[str, dict[str, Any]] = {}
    lookup: dict[str, str] = {}
    for metric in base.get("metrics") or []:
        if not isinstance(metric, dict) or not metric.get("id"):
            continue
        mid = str(metric["id"])
        met_by_id[mid] = dict(metric)
        lookup[mid.lower()] = mid
        key = str(metric.get("key") or "").strip().lower()
        if key:
            lookup[key] = mid

    applied: dict[str, dict[str, Any]] = {}
    for ident, patch in patches.items():
        mid = lookup.get(str(ident).strip().lower())
        if not mid:
            continue
        base_metric = met_by_id[mid]
        merged = dict(base_metric)
        if "allowed_grains" in patch:
            base_sets = {
                _grain_frozenset(grain_list) for grain_list in (base_metric.get("allowed_grains") or [])
            }
            requested = [_grain_frozenset(grain_list) for grain_list in (patch.get("allowed_grains") or [])]
            requested = [g for g in requested if g]
            if not requested or any(g not in base_sets for g in requested):
                continue
            merged["allowed_grains"] = [sorted(g) for g in requested]
        if "label" in patch and str(patch.get("label") or "").strip():
            merged["label"] = str(patch["label"]).strip()
        if "hidden" in patch:
            merged["hidden"] = bool(patch.get("hidden"))
        # Explicitly never copy formula / source_facts / owner_surface / id / key / dimensions.
        met_by_id[mid] = merged
        applied[ident] = patch
    out["metrics"] = list(met_by_id.values())
    return out, applied


def _merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Governed merge (field whitelist). Overlay version/source_doc/dimensions are ignored."""
    merged, _applied = _governed_merge(base, _patches_from_overlay_doc(overlay))
    return merged


def _composed_metric_dicts(overlay: dict[str, Any], platform_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn validated overlay.composed entries into catalog metric dicts (FLAG != BLOCK)."""
    by_ident: dict[str, dict[str, Any]] = {}
    for metric in platform_metrics:
        if not isinstance(metric, dict):
            continue
        mid = str(metric.get("id") or "").strip().lower()
        key = str(metric.get("key") or "").strip().lower()
        if mid:
            by_ident[mid] = metric
        if key:
            by_ident[key] = metric
    raw = overlay.get("composed")
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for ident, body in raw.items():
        if not isinstance(body, dict):
            continue
        compose = body.get("compose")
        if not isinstance(compose, dict):
            continue
        op = str(compose.get("op") or "").strip().lower()
        inputs = [str(x).strip().lower() for x in (compose.get("inputs") or []) if str(x).strip()]
        grain_list = compose.get("grain")
        if op not in {"ratio", "alias"} or not inputs or not isinstance(grain_list, list):
            continue
        sources = [by_ident.get(k) for k in inputs]
        if any(src is None for src in sources):
            continue
        key = str(body.get("key") or ident).strip().lower()
        if not key or key in by_ident or key in seen_keys:
            continue
        facts: list[str] = []
        for src in sources:
            for fact in src.get("source_facts") or []:
                token = str(fact)
                if token not in facts:
                    facts.append(token)
        formula = f"{inputs[0]} / {inputs[1]}" if op == "ratio" else f"alias of {inputs[0]}"
        mid = str(body.get("id") or f"T-{key.upper()}").strip()
        grain_sorted = [str(x).strip().lower() for x in grain_list if str(x).strip()]
        out.append(
            {
                "id": mid,
                "key": key,
                "label": str(body.get("label") or key).strip(),
                "status": "implemented",
                "owner_surface": str(sources[0].get("owner_surface") or "composed"),
                "formula": formula,
                "source_facts": facts,
                "allowed_grains": [grain_sorted],
                "calendar_period": any(bool(src.get("calendar_period")) for src in sources),
                "hidden": bool(body.get("hidden")),
                "compose": {"op": op, "inputs": inputs, "grain": grain_sorted},
            }
        )
        seen_keys.add(key)
    return out


def catalog_for_tenant(tenant_id: str | None = None) -> SemanticCatalog:
    """Load default catalog merged with tenant-profile overlay (YAML overlay is back-compat only)."""
    tid = (tenant_id or "default").strip() or "default"
    base = _load_yaml(_CATALOG_PATH)
    patches: dict[str, dict[str, Any]] = {}
    profile_overlay: dict[str, Any] = {}

    overlay_path = _tenant_overlay_path(tid)
    if overlay_path.is_file() and overlay_path.name != "_example.yaml":
        try:
            yaml_overlay = _load_yaml(overlay_path)
            patches.update(_patches_from_overlay_doc(yaml_overlay))
        except (OSError, ValueError, yaml.YAMLError):
            pass

    try:
        from app.services.commercial_tenant_profile import semantic_overlay_for_tenant

        profile_overlay = semantic_overlay_for_tenant(tid)
        patches.update(_patches_from_overlay_doc(profile_overlay))
    except Exception:
        profile_overlay = {}

    merged, applied = _governed_merge(base, patches)
    composed_dicts = _composed_metric_dicts(profile_overlay, list(merged.get("metrics") or []))
    if composed_dicts:
        merged["metrics"] = list(merged.get("metrics") or []) + composed_dicts
    overlay_state = {"patches": applied, "composed": composed_dicts}
    overlay_applied = bool(applied or composed_dicts)
    merged["version"] = _fold_overlay_version(int(base.get("version") or 1), overlay_state if overlay_applied else {})
    return _catalog_from_data(merged, tenant_id=tid, overlay_applied=overlay_applied)


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

    if metric.hidden:
        return ValidationResult(
            ok=False,
            metric_id=metric.id,
            metric_key=metric.key,
            requested_grains=requested,
            message=(
                f"Metric {metric.label} ({metric.key}) is hidden for this tenant "
                "and cannot be queried."
            ),
            allowed_grains=[sorted(g) for g in metric.allowed_grains],
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
