"""Commercial tenant profile — TENANT-VARIABLE commercial policy.

Defaults encode the current tenant (ASUS SA answers from Q-001/002/009).
Other tenants / onboarding must override these — never treat ASUS values as
application law. Persistence via settings/onboarding is a follow-on BACKLOG.
"""

from __future__ import annotations

import os
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


def profile_snapshot() -> dict[str, object]:
    """Read-only dict for API payloads / explainability. Re-reads env each call."""
    return {
        "constraint_axis": CONSTRAINT_AXIS,
        "over_budget_action": OVER_BUDGET_ACTION,
        "reservation_source": RESERVATION_SOURCE,
        "pm_attribution_mode": PM_ATTRIBUTION_MODE,
        "hard_enforce_budget": _env_bool("HARD_ENFORCE_BUDGET", True),
        "money_ceiling_usd": _env_float("MONEY_CEILING_USD"),
    }
