"""CPOR case lifecycle transitions (spec §2.3).

draft → proposed → approved | rejected → active → ended → settled | cancelled
cancelled retained with zero payable. Illegal transitions → 409 with allowed-next.
"""

from __future__ import annotations

# status → allowed next statuses
LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"proposed", "cancelled"}),
    "proposed": frozenset({"approved", "rejected", "cancelled"}),
    "approved": frozenset({"active", "cancelled"}),
    "rejected": frozenset({"proposed", "cancelled"}),  # proposed via resend
    "active": frozenset({"ended", "cancelled"}),
    "ended": frozenset({"settled", "cancelled"}),
    "settled": frozenset(),
    "cancelled": frozenset(),
}

# Map action name → target status (resend is special: rejected → proposed + version bump)
LIFECYCLE_ACTIONS: dict[str, str] = {
    "propose": "proposed",
    "approve": "approved",
    "reject": "rejected",
    "activate": "active",
    "end": "ended",
    "settle": "settled",
    "cancel": "cancelled",
    "resend": "proposed",
}


def allowed_next(status: str) -> list[str]:
    return sorted(LIFECYCLE_TRANSITIONS.get(status, frozenset()))


def can_transition(current: str, action: str) -> bool:
    target = LIFECYCLE_ACTIONS.get(action)
    if target is None:
        return False
    if action == "resend":
        return current == "rejected"
    return target in LIFECYCLE_TRANSITIONS.get(current, frozenset())


# A move or return draft is a stock action, not a support claim. It never enters
# the support workflow (propose, approve, activate, settle, ...); it can only be
# cancelled. ``origin`` is set at creation and no endpoint edits it.
STOCK_ACTION_ORIGIN = "stock_action"
STOCK_ACTION_ALLOWED_ACTIONS = frozenset({"cancel"})


class StockActionNotASupportClaim(ValueError):
    """A support step was asked of a stock-action case."""

    code = "not_a_support_claim"

    def __init__(self, action: str):
        super().__init__(
            f"not_a_support_claim: a stock action cannot {action}; it can only be cancelled"
        )
        self.action = action


def support_step_refused(origin: str | None, action: str) -> bool:
    return origin == STOCK_ACTION_ORIGIN and action not in STOCK_ACTION_ALLOWED_ACTIONS


def assert_support_step_allowed(case: object, action: str) -> None:
    if support_step_refused(getattr(case, "origin", None), action):
        raise StockActionNotASupportClaim(action)


def target_status(action: str) -> str:
    if action not in LIFECYCLE_ACTIONS:
        raise ValueError(f"Unknown lifecycle action: {action!r}")
    return LIFECYCLE_ACTIONS[action]


# Header edits allowed only in these statuses
EDITABLE_STATUSES = frozenset({"draft", "rejected"})


# BACKLOG-139 / N-0048: ``status`` owns the lifecycle; ``workflow_status`` is a
# projection of it (never an independent machine). Only ``proposed`` keeps the
# promo-export-shaped name; every other status projects to itself.
_WORKFLOW_STATUS_OVERRIDES: dict[str, str] = {"proposed": "pending_approval"}


def workflow_status_for(status: str) -> str:
    """Projection ``status`` → ``cpor_case.workflow_status``. Every writer uses this."""
    return _WORKFLOW_STATUS_OVERRIDES.get(status, status)
