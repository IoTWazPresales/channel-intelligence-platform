"""Commercial tenant profile — TENANT-VARIABLE commercial policy.

Defaults encode the current tenant (ASUS SA answers from Q-001/002/009).
Other tenants / onboarding must override these — never treat ASUS values as
application law. BACKLOG-096 (P6): per-tenant overrides persist as JSON files
under ``{local_storage_path}/tenant_profiles/{tenant_id}.json`` — no migration,
no new table. `profile_snapshot()` merges the file over the module defaults.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

# Q-001 — binding budget axis
ConstraintAxis = Literal["money", "support_pct", "dual", "none"]
OverBudgetAction = Literal["require_reapproval", "warn", "block"]

# Q-002 — where planned reservation comes from
ReservationSource = Literal["derived_from_profit", "explicit_column", "hybrid"]

# Q-009 — how PM attribution is resolved for volume bias
PmAttributionMode = Literal["business_line", "person_field", "none"]

# Current-tenant defaults (Warren 2026-08-01). Override later via onboarding.
CONSTRAINT_AXIS: ConstraintAxis = "money"
OVER_BUDGET_ACTION: OverBudgetAction = "require_reapproval"
RESERVATION_SOURCE: ReservationSource = "derived_from_profit"
PM_ATTRIBUTION_MODE: PmAttributionMode = "business_line"


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        # Fall back to pydantic Settings (.env loaded there even when not in os.environ).
        try:
            from app.core.config import get_settings

            settings = get_settings()
            attr = name.lower()
            if hasattr(settings, attr):
                raw = getattr(settings, attr)
        except Exception:
            raw = None
    if raw is None or str(raw).strip() == "":
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        try:
            from app.core.config import get_settings

            settings = get_settings()
            attr = name.lower()
            if hasattr(settings, attr):
                return bool(getattr(settings, attr))
        except Exception:
            return default
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Optional absolute money ceiling (USD). Env MONEY_CEILING_USD overrides.
# None = flag-only enforcement (needs_reapproval must already be True).
# Module-level values are initial; prefer profile_snapshot() / money_ceiling helpers for live env.
MONEY_CEILING_USD: float | None = _env_float("MONEY_CEILING_USD")

# Hard enforce on when reapproval gates ship (BACKLOG-095). Env HARD_ENFORCE_BUDGET.
HARD_ENFORCE_BUDGET: bool = _env_bool("HARD_ENFORCE_BUDGET", True)


def _env_int(name: str, default: int, *, lo: int = 1, hi: int = 16) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        try:
            from app.core.config import get_settings

            settings = get_settings()
            attr = name.lower()
            if hasattr(settings, attr):
                raw = getattr(settings, attr)
        except Exception:
            raw = None
    if raw is None or str(raw).strip() == "":
        return default
    try:
        val = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, val))


# A2-04 — trailing support-norms window (tenant config; default 4 quarters).
# Env SUPPORT_NORMS_TRAILING_QUARTERS overrides.
SUPPORT_NORMS_TRAILING_QUARTERS: int = _env_int("SUPPORT_NORMS_TRAILING_QUARTERS", 4)


def support_norms_trailing_quarters() -> int:
    """Live read of A2-04 window (env / settings may change after import)."""
    return _env_int("SUPPORT_NORMS_TRAILING_QUARTERS", SUPPORT_NORMS_TRAILING_QUARTERS)


def protected_lineup_case_ids() -> frozenset[int]:
    """Optional bulk-automation exception ids (env CIP_LINEUP_PROTECTED_CASE_IDS)."""
    from app.services.commercial_planner.lineup_case_bulk_protection import (
        protected_lineup_case_ids_from_config,
    )

    return protected_lineup_case_ids_from_config()


# BACKLOG-096 (P6) — onboarding-editable subset. Everything else on this module
# (money ceiling, support-norms window, protected case ids) stays env-only.
# Lineup export sheet/column maps are also tenant-editable (Lane B) — never OEM-hardcoded law.
TENANT_PROFILE_OVERRIDE_KEYS: tuple[str, ...] = (
    "constraint_axis",
    "over_budget_action",
    "reservation_source",
    "pm_attribution_mode",
    "lineup_export_net_requirement_sheet",
    "lineup_export_draft_sheet",
    "lineup_export_columns",
    "semantic_overlay",
)

# Governed metric overlay (P3-1). Only label / hidden / allowed_grains persist;
# formula / source_facts / owner_surface / new metric ids are never stored.
# Composition (`compose`) is U2.
_SEMANTIC_OVERLAY_LABEL_MAX = 128

_TENANT_PROFILE_VALID_VALUES: dict[str, frozenset[str]] = {
    "constraint_axis": frozenset({"money", "support_pct", "dual", "none"}),
    "over_budget_action": frozenset({"require_reapproval", "warn", "block"}),
    "reservation_source": frozenset({"derived_from_profit", "explicit_column", "hybrid"}),
    "pm_attribution_mode": frozenset({"business_line", "person_field", "none"}),
}

# Free-text export sheet names (validated as non-empty safe sheet titles).
_TENANT_PROFILE_FREE_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "lineup_export_net_requirement_sheet",
        "lineup_export_draft_sheet",
    }
)

# Default on-ramp sheet titles (generic — not OEM-branded).
DEFAULT_LINEUP_EXPORT_NET_REQUIREMENT_SHEET = "NetRequirement"
DEFAULT_LINEUP_EXPORT_DRAFT_SHEET = "DraftLineup"

# Canonical draft-lineup export fields (D-056). Headers are tenant-remapable; field ids are CIP.
DEFAULT_LINEUP_EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("customer_code", "Customer Code"),
    ("customer_name", "Customer Name"),
    ("sku", "SKU"),
    ("product_name", "Product Name"),
    ("period_label", "Period Label"),
    ("period_start", "Period Start"),
    ("planned_qty", "Planned Qty"),
    ("distributor_id", "Distributor ID"),
    ("product_id", "Product ID"),
    ("business_unit", "Business Unit"),
    ("forecast_demand", "Forecast Demand"),
    ("bias_adjusted_forecast", "Bias Adjusted Forecast"),
    ("channel_stock", "Channel Stock"),
    ("in_transit", "In Transit"),
    ("target_cover", "Target Cover"),
    ("net_requirement", "Net Requirement"),
    ("notes", "Notes"),
)
LINEUP_EXPORT_CANONICAL_FIELDS: frozenset[str] = frozenset(f for f, _ in DEFAULT_LINEUP_EXPORT_COLUMNS)
DEFAULT_LINEUP_EXPORT_HEADER_BY_FIELD: dict[str, str] = {f: h for f, h in DEFAULT_LINEUP_EXPORT_COLUMNS}

# Incremental promo cost baseline knobs (BACKLOG-089) — tenant-overridable via env/profile later.
BaselineMethod = Literal[
    "prior_window_same_sku_customer",
    "comparable_median",
    "velocity_extrapolate",
]
DEFAULT_BASELINE_METHOD: BaselineMethod = "prior_window_same_sku_customer"
DEFAULT_BASELINE_LOOKBACK_DAYS = 84
DEFAULT_MIN_BASELINE_OBS = 3


def lineup_export_sheet_names(tenant_id: str = "default") -> dict[str, str]:
    """Tenant-configurable workbook sheet titles for lineup export on-ramp."""
    overrides = load_tenant_profile_overrides(tenant_id)
    return {
        "net_requirement": (
            overrides.get("lineup_export_net_requirement_sheet")
            or DEFAULT_LINEUP_EXPORT_NET_REQUIREMENT_SHEET
        ).strip()
        or DEFAULT_LINEUP_EXPORT_NET_REQUIREMENT_SHEET,
        "draft_lineup": (
            overrides.get("lineup_export_draft_sheet") or DEFAULT_LINEUP_EXPORT_DRAFT_SHEET
        ).strip()
        or DEFAULT_LINEUP_EXPORT_DRAFT_SHEET,
    }


def default_lineup_export_columns() -> list[dict[str, str]]:
    return [{"field": field, "header": header} for field, header in DEFAULT_LINEUP_EXPORT_COLUMNS]


def _normalize_lineup_export_columns(raw: object) -> list[dict[str, str]]:
    parsed: object = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("lineup_export_columns: invalid JSON") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("lineup_export_columns: non-empty list required")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"lineup_export_columns[{i}]: expected object {{field, header}}")
        field = str(item.get("field") or "").strip()
        header = str(item.get("header") or "").strip()
        if field not in LINEUP_EXPORT_CANONICAL_FIELDS:
            raise ValueError(f"lineup_export_columns[{i}].field: unknown {field!r}")
        if not header:
            raise ValueError(f"lineup_export_columns[{i}].header: required")
        if field in seen:
            raise ValueError(f"lineup_export_columns: duplicate field {field}")
        seen.add(field)
        safe_header = re.sub(r"[\r\n\t]", " ", header)[:128].strip()
        out.append({"field": field, "header": safe_header})
    return out


def _grain_frozenset(items: object) -> frozenset[str]:
    if not isinstance(items, (list, tuple, set, frozenset)):
        return frozenset()
    out: set[str] = set()
    for item in items:
        token = str(item).strip().lower().replace(" ", "_")
        if token:
            out.add(token)
    return frozenset(out)


def _platform_metric_grain_index() -> dict[str, tuple[frozenset[str], ...]]:
    """Platform catalog grains (YAML default, no tenant overlay) — avoids catalog recursion."""
    from app.semantics.registry import load_catalog

    cat = load_catalog()
    index: dict[str, tuple[frozenset[str], ...]] = {}
    for metric in cat.metrics:
        grains = metric.allowed_grains
        index[metric.id.lower()] = grains
        index[metric.key.lower()] = grains
    return index


def _normalize_metric_overlay_patch(
    ident: str,
    patch: dict[str, Any],
    *,
    grain_index: dict[str, tuple[frozenset[str], ...]] | None,
    strict: bool,
) -> dict[str, Any] | None:
    """Keep label / hidden / allowed_grains only. Unknown metrics and widened grains fail closed."""
    cleaned: dict[str, Any] = {}
    if "label" in patch:
        label = re.sub(r"[\r\n\t]", " ", str(patch.get("label") or "")).strip()[:_SEMANTIC_OVERLAY_LABEL_MAX]
        if label:
            cleaned["label"] = label
        elif strict:
            raise ValueError(f"semantic_overlay.metrics[{ident!r}].label: non-empty string required")
    if "hidden" in patch:
        hidden = patch.get("hidden")
        if isinstance(hidden, bool):
            cleaned["hidden"] = hidden
        elif isinstance(hidden, str) and hidden.strip().lower() in {"true", "false", "1", "0", "yes", "no"}:
            cleaned["hidden"] = hidden.strip().lower() in {"true", "1", "yes"}
        elif strict:
            raise ValueError(f"semantic_overlay.metrics[{ident!r}].hidden: boolean required")
        else:
            cleaned["hidden"] = bool(hidden)
    if "allowed_grains" in patch:
        raw_grains = patch.get("allowed_grains")
        if not isinstance(raw_grains, list) or not raw_grains:
            if strict:
                raise ValueError(
                    f"semantic_overlay.metrics[{ident!r}].allowed_grains: non-empty list of grain sets required"
                )
            return None
        requested: list[frozenset[str]] = []
        for i, grain_list in enumerate(raw_grains):
            grain_set = _grain_frozenset(grain_list)
            if not grain_set:
                if strict:
                    raise ValueError(
                        f"semantic_overlay.metrics[{ident!r}].allowed_grains[{i}]: non-empty grain set required"
                    )
                continue
            requested.append(grain_set)
        if not requested:
            if strict:
                raise ValueError(f"semantic_overlay.metrics[{ident!r}].allowed_grains: no valid grain sets")
            return None
        if grain_index is None:
            if strict:
                raise ValueError(f"semantic_overlay.metrics[{ident!r}].allowed_grains: catalog unavailable")
            return None
        base_grains = grain_index.get(ident.strip().lower())
        if base_grains is None:
            if strict:
                raise ValueError(
                    f"semantic_overlay.metrics[{ident!r}]: unknown metric (overlay cannot invent ids)"
                )
            return None
        base_set = set(base_grains)
        for grain_set in requested:
            if grain_set not in base_set:
                if strict:
                    pretty = "{" + ", ".join(sorted(grain_set)) + "}"
                    raise ValueError(
                        f"semantic_overlay.metrics[{ident!r}].allowed_grains: {pretty} is not an "
                        f"existing grain set for this metric (restrict only; never widen)"
                    )
                return None
        cleaned["allowed_grains"] = [sorted(g) for g in requested]
    if not cleaned:
        return None
    if grain_index is not None and ident.strip().lower() not in grain_index:
        if strict:
            raise ValueError(f"semantic_overlay.metrics[{ident!r}]: unknown metric (overlay cannot invent ids)")
        return None
    return cleaned


def _normalize_semantic_overlay(raw: object, *, strict: bool = False) -> dict[str, Any]:
    """Shape: ``{ "metrics": { "<id-or-key>": { label?, hidden?, allowed_grains? } } }``."""
    parsed: object = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            if strict:
                raise ValueError("semantic_overlay: invalid JSON") from exc
            return {"metrics": {}}
    if not isinstance(parsed, dict):
        if strict:
            raise ValueError("semantic_overlay: object required")
        return {"metrics": {}}
    metrics_raw = parsed.get("metrics")
    if metrics_raw is None:
        return {"metrics": {}}
    if not isinstance(metrics_raw, dict):
        if strict:
            raise ValueError("semantic_overlay.metrics: object required")
        return {"metrics": {}}

    try:
        grain_index: dict[str, tuple[frozenset[str], ...]] | None = _platform_metric_grain_index()
    except Exception:
        if strict:
            raise
        grain_index = None

    out_metrics: dict[str, Any] = {}
    for ident_raw, patch in metrics_raw.items():
        ident = str(ident_raw).strip()
        if not ident:
            if strict:
                raise ValueError("semantic_overlay.metrics: empty metric key")
            continue
        if not isinstance(patch, dict):
            if strict:
                raise ValueError(f"semantic_overlay.metrics[{ident!r}]: object required")
            continue
        try:
            cleaned = _normalize_metric_overlay_patch(
                ident, patch, grain_index=grain_index, strict=strict
            )
        except ValueError:
            if strict:
                raise
            continue
        if cleaned:
            out_metrics[ident] = cleaned
    return {"metrics": out_metrics}


def semantic_overlay_for_tenant(tenant_id: str = "default") -> dict[str, Any]:
    """Governed overlay document for ``tenant_id``. Missing/invalid → empty metrics (FLAG != BLOCK)."""
    raw = load_tenant_profile_overrides(tenant_id).get("semantic_overlay")
    if isinstance(raw, dict) and isinstance(raw.get("metrics"), dict):
        return raw
    return {"metrics": {}}


def lineup_export_columns(tenant_id: str = "default") -> list[dict[str, str]]:
    """Resolved draft-lineup column map (override or CIP default). Never OEM-branded."""
    overrides = load_tenant_profile_overrides(tenant_id)
    raw = overrides.get("lineup_export_columns")
    if raw:
        try:
            return _normalize_lineup_export_columns(raw)
        except ValueError:
            return default_lineup_export_columns()
    return default_lineup_export_columns()


def incremental_baseline_config(tenant_id: str = "default") -> dict[str, object]:
    """BACKLOG-089 baseline knobs — env overrides for lookback/min obs; method fixed default for v1."""
    lookback = _env_int("CIP_INCREMENTAL_BASELINE_LOOKBACK_DAYS", DEFAULT_BASELINE_LOOKBACK_DAYS, lo=7, hi=730)
    min_obs = _env_int("CIP_INCREMENTAL_MIN_BASELINE_OBS", DEFAULT_MIN_BASELINE_OBS, lo=1, hi=100)
    return {
        "tenant_id": tenant_id,
        "baseline_method": DEFAULT_BASELINE_METHOD,
        "baseline_lookback_days": lookback,
        "min_baseline_obs": min_obs,
    }

_TENANT_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _tenant_profiles_dir() -> Path:
    from app.core.config import get_settings

    settings = get_settings()
    d = Path(settings.local_storage_path) / "tenant_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tenant_profile_override_path(tenant_id: str) -> Path:
    safe = _TENANT_ID_SAFE_RE.sub("", str(tenant_id or "").strip()) or "default"
    return _tenant_profiles_dir() / f"{safe}.json"


def load_tenant_profile_overrides(tenant_id: str = "default") -> dict[str, Any]:
    """Read persisted overrides for ``tenant_id``. Missing/unreadable file → ``{}`` (FLAG != BLOCK)."""
    path = _tenant_profile_override_path(tenant_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in TENANT_PROFILE_OVERRIDE_KEYS or value is None:
            continue
        if key == "lineup_export_columns":
            try:
                out[key] = _normalize_lineup_export_columns(value)
            except ValueError:
                continue
            continue
        if key == "semantic_overlay":
            try:
                normalized = _normalize_semantic_overlay(value, strict=False)
            except (TypeError, ValueError):
                continue
            if normalized.get("metrics"):
                out[key] = normalized
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out


def save_tenant_profile_overrides(tenant_id: str, overrides: dict[str, object]) -> dict[str, Any]:
    """Validate + persist overrides to ``{local_storage_path}/tenant_profiles/{tenant_id}.json``.

    Keys omitted from ``overrides`` are kept from the existing file (merge) so a
    semantic-overlay save cannot wipe commercial policy. Empty/None values clear
    that key. Unknown keys are dropped. Invalid values raise ``ValueError`` (400).
    """
    existing = load_tenant_profile_overrides(tenant_id)
    clean: dict[str, Any] = {}
    for key in TENANT_PROFILE_OVERRIDE_KEYS:
        incoming = key in overrides
        if not incoming:
            if key in existing:
                clean[key] = existing[key]
            continue
        raw = overrides[key]
        if key == "semantic_overlay":
            if raw is None or raw == "" or raw == {}:
                continue
            normalized = _normalize_semantic_overlay(raw, strict=True)
            if normalized.get("metrics"):
                clean[key] = normalized
            continue
        if key == "lineup_export_columns":
            if raw is None or raw == "" or raw == []:
                continue
            clean[key] = _normalize_lineup_export_columns(raw)
            continue
        if raw is None or str(raw).strip() == "":
            continue
        val = str(raw).strip()
        if key in _TENANT_PROFILE_FREE_TEXT_KEYS:
            # Excel sheet title limit 31; keep alphanumeric + space/_/-
            safe = re.sub(r"[^\w\s\-]", "", val)[:31].strip()
            if not safe:
                raise ValueError(f"{key}: sheet name required")
            clean[key] = safe
            continue
        if val not in _TENANT_PROFILE_VALID_VALUES[key]:
            raise ValueError(
                f"{key}: invalid value {val!r}; expected one of "
                f"{sorted(_TENANT_PROFILE_VALID_VALUES[key])}"
            )
        clean[key] = val
    path = _tenant_profile_override_path(tenant_id)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    from app.semantics.registry import clear_catalog_cache

    clear_catalog_cache()
    return clean


def profile_snapshot(tenant_id: str = "default") -> dict[str, object]:
    """Read-only dict for API payloads / explainability.

    Re-reads env each call; merges persisted ``tenant_id`` file overrides
    (BACKLOG-096) over the module defaults for the four onboarding-editable keys.
    """
    overrides = load_tenant_profile_overrides(tenant_id)
    sheets = lineup_export_sheet_names(tenant_id)
    return {
        "tenant_id": tenant_id,
        "constraint_axis": overrides.get("constraint_axis", CONSTRAINT_AXIS),
        "over_budget_action": overrides.get("over_budget_action", OVER_BUDGET_ACTION),
        "reservation_source": overrides.get("reservation_source", RESERVATION_SOURCE),
        "pm_attribution_mode": overrides.get("pm_attribution_mode", PM_ATTRIBUTION_MODE),
        "lineup_export_sheets": sheets,
        "lineup_export_columns": lineup_export_columns(tenant_id),
        "incremental_baseline": incremental_baseline_config(tenant_id),
        "overrides_present": sorted(overrides.keys()),
        "hard_enforce_budget": _env_bool("HARD_ENFORCE_BUDGET", True),
        "money_ceiling_usd": _env_float("MONEY_CEILING_USD"),
        "support_norms_trailing_quarters": support_norms_trailing_quarters(),
        "protected_lineup_case_ids": sorted(protected_lineup_case_ids()),
    }
