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
from typing import Literal

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
)

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


def load_tenant_profile_overrides(tenant_id: str = "default") -> dict[str, str]:
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
    return {
        k: str(v)
        for k, v in data.items()
        if k in TENANT_PROFILE_OVERRIDE_KEYS and v is not None and str(v).strip()
    }


def save_tenant_profile_overrides(tenant_id: str, overrides: dict[str, object]) -> dict[str, str]:
    """Validate + persist overrides to ``{local_storage_path}/tenant_profiles/{tenant_id}.json``.

    Unknown keys are dropped silently; empty/None values clear that key. Invalid
    values raise ``ValueError`` — the API layer turns this into a 400.
    """
    clean: dict[str, str] = {}
    for key in TENANT_PROFILE_OVERRIDE_KEYS:
        if key not in overrides:
            continue
        raw = overrides[key]
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
        "incremental_baseline": incremental_baseline_config(tenant_id),
        "overrides_present": sorted(overrides.keys()),
        "hard_enforce_budget": _env_bool("HARD_ENFORCE_BUDGET", True),
        "money_ceiling_usd": _env_float("MONEY_CEILING_USD"),
        "support_norms_trailing_quarters": support_norms_trailing_quarters(),
        "protected_lineup_case_ids": sorted(protected_lineup_case_ids()),
    }
