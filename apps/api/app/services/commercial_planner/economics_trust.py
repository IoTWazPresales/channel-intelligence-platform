"""Line/plan economics trust tiers (read-only helpers; no DB writes)."""

from __future__ import annotations

from collections import Counter
from typing import Literal

TrustTier = Literal["ok", "warning", "blocked"]

# Flags that mean stored dollar outputs are not decision-grade.
BLOCKING_TRUST_FLAGS: frozenset[str] = frozenset(
    {
        "missing_sku_assumption",
        # Legacy persisted calc_flags (pre-rename migration / old recalculates)
        "missing_or_invalid_landed_cost",
        "invalid_fx_rate_to_usd",
        # Current calculator / trust flags
        "missing_or_invalid_controlled_cost",
        "invalid_fx_plan_currency_per_cost_currency",
        "impossible_economics",
        "non_positive_target_units",
        "non_positive_target_srp",
    }
)

WARNING_TRUST_FLAGS: frozenset[str] = frozenset(
    {
        "missing_customer_term",
        "missing_distributor_term",
        "partial_margin_stack",
        "impossible_margin_stack",
        "margin_floor_breach",
        "reserve_breach",
        "economics_placeholder_fx_without_sku",
        "economics_placeholder_vat_without_sku",
        "economics_placeholder_reserves_without_sku",
        "unassigned_distributor_placeholder",
    }
)


def classify_line_economics_trust(calc_flags: list[str] | None) -> tuple[TrustTier, list[str]]:
    """Return trust tier and reason codes (flag strings) for UI."""
    flags = [str(f) for f in (calc_flags or []) if f]
    fc = set(flags)
    reasons: list[str] = []

    for f in flags:
        if f in BLOCKING_TRUST_FLAGS:
            reasons.append(f)
        elif f in WARNING_TRUST_FLAGS:
            reasons.append(f)

    # Dedupe preserving order
    seen: set[str] = set()
    ordered = [r for r in reasons if not (r in seen or seen.add(r))]

    if fc & BLOCKING_TRUST_FLAGS:
        return "blocked", ordered
    if ordered or (fc & WARNING_TRUST_FLAGS):
        return "warning", ordered
    return "ok", []


def plan_trust_from_line_tiers(tiers: list[TrustTier]) -> TrustTier:
    if any(t == "blocked" for t in tiers):
        return "blocked"
    if any(t == "warning" for t in tiers):
        return "warning"
    return "ok"


def summarize_recalculate_trust(
    line_results: list[tuple[int, list[str], TrustTier]],
) -> dict:
    """Non-breaking aggregate for POST recalculate response."""
    tier_counts: Counter[TrustTier] = Counter(t for _, _, t in line_results)
    blocker_hits: Counter[str] = Counter()
    for _, flags, tier in line_results:
        if tier != "blocked":
            continue
        for f in flags:
            if f in BLOCKING_TRUST_FLAGS:
                blocker_hits[f] += 1
    top = [k for k, _ in blocker_hits.most_common(8)]
    return {
        "lines_trusted_ok": int(tier_counts["ok"]),
        "lines_warning": int(tier_counts["warning"]),
        "lines_blocked": int(tier_counts["blocked"]),
        "top_blocker_flags": top,
    }
