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


def target_status(action: str) -> str:
    if action not in LIFECYCLE_ACTIONS:
        raise ValueError(f"Unknown lifecycle action: {action!r}")
    return LIFECYCLE_ACTIONS[action]


# Header edits allowed only in these statuses
EDITABLE_STATUSES = frozenset({"draft", "rejected"})
