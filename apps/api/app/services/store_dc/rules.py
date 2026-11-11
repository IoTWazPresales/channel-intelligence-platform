"""Pure rules for store and DC replenishment.

No account, distributor, site, or vendor name lives here. Cover fallbacks are the
same 4 and 6 weeks already used at account grain. The lead-time sample floor, the
slow multiple, and the stock-behaviour floor are tenant or customer settings when
stored, and these fallbacks when they are not.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.models.customer_report_config import (
    DEFAULT_REPLEN_MIN_WEEKS_OF_COVER,
    DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER,
)

SITE_LEVELS = ("distributor_stock", "customer_dc", "store", "other")
SITE_OWNERS = ("customer", "distributor")
EVIDENCE_KINDS = ("pattern", "stock_behaviour", "direct_shipment")
CANDIDATE_STATUSES = ("open", "confirmed", "rejected")
SUGGESTIONS = ("promote", "move", "return")


def stock_action_in_notes(notes: str | None) -> str | None:
    """Read a promote, move, or return marker. Anything else is not an action."""
    if not notes:
        return None
    for token in str(notes).replace("\n", ";").split(";"):
        token = token.strip()
        if not token.startswith("stock_action="):
            continue
        action = token.split("=", 1)[1].strip().split()[0]
        if action in SUGGESTIONS:
            return action
    return None


def stock_action_covers_site(evidence: dict | None, site_label: str | None) -> bool:
    """Whether a recorded action includes this site.

    Lines written before a site was stored cover every site. A recorded list
    covers only the sites in that list. An empty label is the account grain.
    """
    if not isinstance(evidence, dict) or "site_labels" not in evidence:
        return True
    wanted = (site_label or "").strip() or None
    for raw in evidence.get("site_labels") or []:
        recorded = None if raw is None or str(raw).strip() == "" else str(raw).strip()
        if recorded == wanted:
            return True
    return False


DEFAULT_LEAD_TIME_MIN_DELIVERIES = 5
DEFAULT_SLOW_COVER_MULTIPLE = 2.0
DEFAULT_STOCK_BEHAVIOUR_MIN_SOH = 1.0

NO_HISTORY = "lead time: no history"
COLLAPSED_NOTE = "Stored units with no site label are a collapsed grain, not a store."
ONWARD_NOTE = "No dispatch and receipt dates are stored, so this leg has no history."


class SiteLevelRejected(ValueError):
    """The database check rejects the same pair. Raised before the write."""


def norm_label(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def owner_may_have_level(owner: str, level: str | None) -> bool:
    if owner not in SITE_OWNERS:
        return False
    if level is not None and level not in SITE_LEVELS:
        return False
    if owner == "distributor" and level == "customer_dc":
        return False
    return True


def assert_owner_level(owner: str, level: str | None) -> None:
    if owner not in SITE_OWNERS or (level is not None and level not in SITE_LEVELS):
        raise SiteLevelRejected("Site level or owner is not one of the allowed values")
    if not owner_may_have_level(owner, level):
        raise SiteLevelRejected("A distributor-owned site cannot be a customer distribution centre")


def pattern_matches(label: str, patterns: list[str]) -> bool:
    """Full-string match against tenant patterns. Not a substring search."""
    text = (label or "").strip()
    if not text:
        return False
    for raw in patterns:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            if re.fullmatch(raw.strip(), text, flags=re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def cover_weeks(cfg: Any) -> dict[str, Any]:
    """Customer cover settings, or the existing 4 and 6 week fallback when empty."""
    min_raw = _as_float(getattr(cfg, "replen_min_weeks_of_cover", None)) if cfg is not None else None
    target_raw = _as_float(getattr(cfg, "replen_target_weeks_of_cover", None)) if cfg is not None else None
    min_set = min_raw is not None and min_raw > 0
    target_set = target_raw is not None and target_raw > 0
    return {
        "min_weeks": min_raw if min_set else DEFAULT_REPLEN_MIN_WEEKS_OF_COVER,
        "target_weeks": target_raw if target_set else DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER,
        "source": "customer" if min_set or target_set else "fallback",
    }


def slow_multiple(cfg: Any) -> float:
    raw = _as_float(getattr(cfg, "slow_cover_multiple", None)) if cfg is not None else None
    if raw is not None and raw > 0:
        return raw
    return DEFAULT_SLOW_COVER_MULTIPLE


def unsold_window_weeks(cfg: Any, min_weeks: float) -> float:
    raw = _as_float(getattr(cfg, "unsold_weeks", None)) if cfg is not None else None
    if raw is not None and raw > 0:
        return raw
    return float(min_weeks)


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("empty")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return float(sorted_values[lo]) * (1 - frac) + float(sorted_values[hi]) * frac


def _histogram(days: list[int]) -> list[dict[str, Any]]:
    labels = ("0-7", "8-14", "15-28", "29-56", "57+")
    counts = [0, 0, 0, 0, 0]
    for day in days:
        if day <= 7:
            counts[0] += 1
        elif day <= 14:
            counts[1] += 1
        elif day <= 28:
            counts[2] += 1
        elif day <= 56:
            counts[3] += 1
        else:
            counts[4] += 1
    return [{"bucket": labels[i], "count": counts[i]} for i in range(5)]


def empty_distribution() -> dict[str, Any]:
    return {
        "history": "no history",
        "sample_count": 0,
        "min_days": None,
        "p25_days": None,
        "median_days": None,
        "p75_days": None,
        "max_days": None,
        "histogram": _histogram([]),
    }


def distribution(days: list[int]) -> dict[str, Any]:
    clean = [int(d) for d in days if d is not None and int(d) >= 0]
    if not clean:
        return empty_distribution()
    ordered = sorted(float(d) for d in clean)
    return {
        "history": "history",
        "sample_count": len(ordered),
        "min_days": ordered[0],
        "p25_days": round(percentile(ordered, 25), 2),
        "median_days": round(percentile(ordered, 50), 2),
        "p75_days": round(percentile(ordered, 75), 2),
        "max_days": ordered[-1],
        "histogram": _histogram(clean),
    }


def lead_for_need(dist: dict[str, Any], min_deliveries: int) -> tuple[float, str]:
    """Median weeks only when the sample meets the tenant floor. Otherwise cover only."""
    count = int(dist.get("sample_count") or 0)
    median = dist.get("median_days")
    if count < int(min_deliveries) or median is None:
        return 0.0, NO_HISTORY
    weeks = float(median) / 7.0
    return weeks, f"lead time: {float(median):g} days"


def inbound_leg(days: list[int], min_deliveries: int) -> dict[str, Any]:
    dist = distribution(days)
    weeks, label = lead_for_need(dist, min_deliveries)
    return {
        "leg": "inbound",
        "title": "Ship confirm to proof of delivery",
        **dist,
        "lead_time_weeks": None if label == NO_HISTORY else round(weeks, 4),
        "lead_time_label": label,
        "used_in_need": label != NO_HISTORY,
        "min_deliveries": int(min_deliveries),
    }


def onward_leg() -> dict[str, Any]:
    """DC dispatch to store receipt. There is no date pair. Never copy inbound days in."""
    dist = empty_distribution()
    return {
        "leg": "onward",
        "title": "Customer distribution centre to store",
        "note": ONWARD_NOTE,
        **dist,
        "lead_time_weeks": None,
        "lead_time_label": NO_HISTORY,
        "used_in_need": False,
    }


def weekly_rate(week_units: list[float]) -> float | None:
    if not week_units:
        return None
    return float(sum(week_units)) / float(len(week_units))


def weeks_of_cover(soh: float | None, rate: float | None) -> float | None:
    if soh is None or rate is None or rate <= 0:
        return None
    return soh / rate


def need_units(*, rate: float | None, soh: float | None, target_weeks: float, lead_weeks: float) -> dict[str, Any]:
    """Cover target, plus lead time only when that leg supplied a median."""
    if soh is None:
        return {"units": None, "reason": "no stock reported"}
    if rate is None or rate <= 0:
        return {"units": 0.0, "reason": "no sales rate"}
    units = max(0.0, rate * (float(target_weeks) + float(lead_weeks)) - float(soh))
    reason = "cover_and_lead_time" if lead_weeks else "cover"
    return {"units": round(units, 2), "reason": reason}


def is_weekly(period_grain: str | None, period_type: str | None) -> bool:
    grain = (period_grain or "").lower()
    kind = (period_type or "").lower()
    return grain == "week" or kind in {"week", "weekly"}


def is_slow(woc: float | None, target_weeks: float, multiple: float) -> bool:
    if woc is None:
        return False
    return woc >= float(multiple) * float(target_weeks)


def is_unsold(soh: float | None, units_in_window: float, observations: int, window_weeks: float) -> bool:
    needed = max(1, int(math.ceil(window_weeks)))
    if observations < needed:
        return False
    return soh is not None and soh > 0 and units_in_window <= 0


def suggestion_labels(*, slow: bool, unsold: bool) -> list[str]:
    if not slow and not unsold:
        return []
    return list(SUGGESTIONS)


def sell_through_ratio(units: float | None, soh: float | None) -> float | None:
    """Last week's units ÷ (last week's units + stock on hand)."""
    if units is None or soh is None:
        return None
    denom = float(units) + float(soh)
    if denom <= 0:
        return None
    return float(units) / denom


def window_count(weeks: float) -> int:
    return max(1, int(math.ceil(weeks)))
