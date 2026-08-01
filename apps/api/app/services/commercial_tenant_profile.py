"""Commercial tenant profile — TENANT-VARIABLE commercial policy.

Defaults encode the current tenant (ASUS SA answers from Q-001/002/009).
Other tenants / onboarding must override these — never treat ASUS values as
application law. Persistence via settings/onboarding is a follow-on BACKLOG.
"""

from __future__ import annotations

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

# Optional absolute money ceiling (USD). When set and portfolio committed support
# exceeds it, cases are flagged needs_reapproval and approve/export are gated.
# None = flag-only enforcement (needs_reapproval must already be True).
MONEY_CEILING_USD: float | None = None

# Hard enforce on when reapproval gates ship (BACKLOG-095).
HARD_ENFORCE_BUDGET: bool = True


def profile_snapshot() -> dict[str, object]:
    """Read-only dict for API payloads / explainability."""
    return {
        "constraint_axis": CONSTRAINT_AXIS,
        "over_budget_action": OVER_BUDGET_ACTION,
        "reservation_source": RESERVATION_SOURCE,
        "pm_attribution_mode": PM_ATTRIBUTION_MODE,
        "hard_enforce_budget": HARD_ENFORCE_BUDGET,
        "money_ceiling_usd": MONEY_CEILING_USD,
    }
