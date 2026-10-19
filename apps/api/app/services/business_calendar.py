"""Tenant business calendar: how days roll up into weeks, months, quarters and years.

Warren 2026-10-19: the calendar is set once in Settings and every screen that groups by period
follows it. Companies use different calendars, so the setting supports:

- ``gregorian``: calendar months. The financial year starts on the 1st of a chosen month.
- ``retail_445`` / ``retail_454`` / ``retail_544``: years of whole weeks (52, sometimes 53). Each
  quarter is 13 weeks split into three periods of 4-4-5, 4-5-4 or 5-4-4 weeks; a 53rd week joins the
  last period. The year ends on the last day of the week that falls last in the year-end month
  (``year_end_rule = last``) or nearest to the end of that month (``nearest``).
- ``custom``: the tenant lists the first day of each period with its financial year and quarter.

A year is named by the calendar year it ends in (``fiscal_year_named_by = end``, the default) or the
one it starts in. Labels follow the app's ``26Q4`` convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

CALENDAR_TYPES = ("gregorian", "retail_445", "retail_454", "retail_544", "custom")
GRAINS = ("day", "week", "month", "quarter", "year")
_RETAIL_PATTERNS = {"retail_445": (4, 4, 5), "retail_454": (4, 5, 4), "retail_544": (5, 4, 4)}
_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

DEFAULT_CALENDAR: dict[str, Any] = {
    "type": "gregorian",
    "fiscal_year_start_month": 1,
    "week_start_day": 0,  # Monday; matches the imports' Monday-Sunday week
    "year_end_rule": "last",
    "fiscal_year_named_by": "end",
    "custom_periods": [],
}


@dataclass(frozen=True)
class Bucket:
    """One period of the calendar. ``end`` is inclusive."""

    grain: str
    start: date
    end: date
    label: str
    fiscal_year: int | None = None
    quarter: int | None = None

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "grain": self.grain,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "fiscal_year": self.fiscal_year,
            "quarter": self.quarter,
        }


def _iso(raw: object) -> date:
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw).strip()[:10])


def normalize_calendar_config(raw: object, *, strict: bool = True) -> dict[str, Any]:
    """Validate a calendar setting. ``strict`` raises ``ValueError``; otherwise bad parts fall back."""
    cfg = dict(DEFAULT_CALENDAR)
    if raw is None or raw == "" or raw == {}:
        return cfg
    if not isinstance(raw, dict):
        if strict:
            raise ValueError("business_calendar: an object is required")
        return cfg

    def bad(msg: str) -> None:
        if strict:
            raise ValueError(f"business_calendar: {msg}")

    kind = str(raw.get("type") or "gregorian").strip().lower()
    if kind not in CALENDAR_TYPES:
        bad(f"type must be one of {list(CALENDAR_TYPES)}")
        kind = "gregorian"
    cfg["type"] = kind

    try:
        month = int(raw.get("fiscal_year_start_month") or 1)
    except (TypeError, ValueError):
        month = 0
    if not 1 <= month <= 12:
        bad("fiscal_year_start_month must be 1-12")
        month = 1
    cfg["fiscal_year_start_month"] = month

    try:
        wsd = int(raw.get("week_start_day") if raw.get("week_start_day") is not None else 0)
    except (TypeError, ValueError):
        wsd = -1
    if not 0 <= wsd <= 6:
        bad("week_start_day must be 0 (Monday) to 6 (Sunday)")
        wsd = 0
    cfg["week_start_day"] = wsd

    rule = str(raw.get("year_end_rule") or "last").strip().lower()
    if rule not in ("last", "nearest"):
        bad("year_end_rule must be last or nearest")
        rule = "last"
    cfg["year_end_rule"] = rule

    named = str(raw.get("fiscal_year_named_by") or "end").strip().lower()
    if named not in ("start", "end"):
        bad("fiscal_year_named_by must be start or end")
        named = "end"
    cfg["fiscal_year_named_by"] = named

    periods: list[dict[str, Any]] = []
    raw_periods = raw.get("custom_periods") or []
    if not isinstance(raw_periods, list):
        bad("custom_periods must be a list")
        raw_periods = []
    for i, p in enumerate(raw_periods):
        try:
            start = _iso(p.get("start"))
            fy = int(p.get("fiscal_year"))
            q = int(p.get("quarter"))
            if not 1 <= q <= 4:
                raise ValueError("quarter")
            label = str(p.get("label") or "").strip()[:32] or None
        except (AttributeError, TypeError, ValueError):
            bad(f"custom period {i + 1} needs a start date, a financial year and a quarter 1-4")
            continue
        periods.append({"start": start.isoformat(), "fiscal_year": fy, "quarter": q, "label": label})
    periods.sort(key=lambda p: p["start"])
    if len({p["start"] for p in periods}) != len(periods):
        bad("two custom periods start on the same day")
    if kind == "custom" and not periods:
        bad("a custom calendar needs at least one period")
        if not strict:
            cfg["type"] = "gregorian"
    cfg["custom_periods"] = periods
    return cfg


class BusinessCalendar:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = normalize_calendar_config(config or {}, strict=False)
        self.type: str = self.config["type"]
        self.start_month: int = self.config["fiscal_year_start_month"]
        self.week_start_day: int = self.config["week_start_day"]
        self._periods = [
            (_iso(p["start"]), int(p["fiscal_year"]), int(p["quarter"]), p.get("label"))
            for p in self.config["custom_periods"]
        ]

    # ------------------------------------------------------------------ labels
    def _fy_name(self, start: date, end: date) -> int:
        return end.year if self.config["fiscal_year_named_by"] == "end" else start.year

    @staticmethod
    def quarter_label(fy: int, q: int) -> str:
        return f"{fy % 100:02d}Q{q}"

    def year_label(self, fy: int) -> str:
        if self.type == "gregorian" and self.start_month == 1:
            return str(fy)
        return f"FY{fy % 100:02d}"

    # ------------------------------------------------------------------ years
    def _retail_year_end(self, year: int) -> date:
        end_month = self.start_month - 1 or 12
        last_of_month = (date(year, end_month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        week_end_day = (self.week_start_day - 1) % 7
        back = (last_of_month.weekday() - week_end_day) % 7
        last = last_of_month - timedelta(days=back)
        if self.config["year_end_rule"] == "nearest" and back > 3:
            last += timedelta(days=7)
        return last

    def year(self, d: date) -> Bucket:
        if self.type == "gregorian":
            y = d.year if d.month >= self.start_month else d.year - 1
            start = date(y, self.start_month, 1)
            end = date(y + 1, self.start_month, 1) - timedelta(days=1)
        elif self.type in _RETAIL_PATTERNS:
            ends = [self._retail_year_end(y) for y in range(d.year - 2, d.year + 3)]
            i = next(i for i, e in enumerate(ends) if e >= d)
            start = ends[i - 1] + timedelta(days=1)
            end = ends[i]
        else:
            per = self._custom_period(d)
            if per is None:
                return BusinessCalendar({**self.config, "type": "gregorian"}).year(d)
            fy = per[1]
            same = [p for p in self._periods if p[1] == fy]
            start = same[0][0]
            end = self._custom_period_end(same[-1][0])
            return Bucket("year", start, end, self.year_label(fy), fy, None)
        fy = self._fy_name(start, end)
        return Bucket("year", start, end, self.year_label(fy), fy, None)

    # ------------------------------------------------------------------ custom
    def _custom_period(self, d: date) -> tuple[date, int, int, str | None] | None:
        found = None
        for p in self._periods:
            if p[0] <= d:
                found = p
            else:
                break
        if found is None:
            return None
        if found is self._periods[-1] and d > self._custom_period_end(found[0]):
            return None
        return found

    def _custom_period_end(self, start: date) -> date:
        for p in self._periods:
            if p[0] > start:
                return p[0] - timedelta(days=1)
        # Last listed period: assume it runs one calendar month.
        nxt = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        return nxt - timedelta(days=1) if start.day == 1 else start + timedelta(days=30)

    # ------------------------------------------------------------------ buckets
    def week_start(self, d: date) -> date:
        return d - timedelta(days=(d.weekday() - self.week_start_day) % 7)

    def bucket(self, d: date, grain: str) -> Bucket:
        if grain == "day":
            return Bucket("day", d, d, f"{d.day} {_MONTH_ABBR[d.month - 1]}")
        if grain == "week":
            start = self.week_start(d)
            end = start + timedelta(days=6)
            if self.type == "gregorian" and self.start_month == 1 and self.week_start_day == 0:
                iso_y, iso_w, _ = start.isocalendar()
                return Bucket("week", start, end, f"W{iso_w:02d}", iso_y, None)
            yr = self.year(start)
            n = (start - self.week_start(yr.start)).days // 7 + 1
            return Bucket("week", start, end, f"W{n:02d}", yr.fiscal_year, None)
        if grain == "year":
            return self.year(d)
        if self.type == "gregorian":
            if grain == "month":
                start = d.replace(day=1)
                end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                yr = self.year(d)
                q = ((d.month - self.start_month) % 12) // 3 + 1
                return Bucket("month", start, end, f"{_MONTH_ABBR[d.month - 1]} {d.year % 100:02d}", yr.fiscal_year, q)
            yr = self.year(d)
            q = ((d.month - self.start_month) % 12) // 3 + 1
            first_month = (self.start_month - 1 + (q - 1) * 3) % 12 + 1
            qy = d.year if first_month <= d.month else d.year - 1
            start = date(qy, first_month, 1)
            end_m = first_month + 3
            end = (date(qy + (end_m - 1) // 12, (end_m - 1) % 12 + 1, 1)) - timedelta(days=1)
            return Bucket("quarter", start, end, self.quarter_label(yr.fiscal_year or 0, q), yr.fiscal_year, q)
        if self.type in _RETAIL_PATTERNS:
            yr = self.year(d)
            pattern = _RETAIL_PATTERNS[self.type]
            weeks_in_year = ((yr.end - yr.start).days + 1) // 7
            week_idx = (d - yr.start).days // 7
            # Twelve periods of whole weeks; a 53rd week joins period 12.
            bounds: list[tuple[int, int]] = []
            w = 0
            for _q in range(4):
                for n in pattern:
                    bounds.append((w, w + n - 1))
                    w += n
            bounds[-1] = (bounds[-1][0], weeks_in_year - 1)
            p_idx = next(i for i, (a, b) in enumerate(bounds) if a <= week_idx <= b)
            q = p_idx // 3 + 1
            if grain == "month":
                a, b = bounds[p_idx]
                start = yr.start + timedelta(weeks=a)
                end = yr.start + timedelta(weeks=b + 1) - timedelta(days=1)
                return Bucket("month", start, end, f"P{p_idx + 1:02d} {yr.label}", yr.fiscal_year, q)
            a = bounds[(q - 1) * 3][0]
            b = bounds[(q - 1) * 3 + 2][1]
            start = yr.start + timedelta(weeks=a)
            end = yr.start + timedelta(weeks=b + 1) - timedelta(days=1)
            return Bucket("quarter", start, end, self.quarter_label(yr.fiscal_year or 0, q), yr.fiscal_year, q)
        # custom
        per = self._custom_period(d)
        if per is None:
            return BusinessCalendar({**self.config, "type": "gregorian"}).bucket(d, grain)
        p_start, fy, q, label = per
        if grain == "month":
            end = self._custom_period_end(p_start)
            return Bucket("month", p_start, end, label or f"{_MONTH_ABBR[p_start.month - 1]} {p_start.year % 100:02d}", fy, q)
        same_q = [p for p in self._periods if p[1] == fy and p[2] == q]
        start = same_q[0][0]
        end = self._custom_period_end(same_q[-1][0])
        return Bucket("quarter", start, end, self.quarter_label(fy, q), fy, q)

    def buckets(self, start: date, end: date, grain: str) -> list[Bucket]:
        """Every bucket that overlaps [start, end], in order."""
        if grain not in GRAINS:
            raise ValueError(f"grain must be one of {list(GRAINS)}")
        out: list[Bucket] = []
        d = start
        guard = 0
        while d <= end and guard < 5000:
            b = self.bucket(d, grain)
            out.append(b)
            d = b.end + timedelta(days=1)
            guard += 1
        return out

    def same_day_last_year(self, d: date) -> date:
        """The matching day one financial year earlier (same week day for week-based calendars)."""
        if self.type == "gregorian":
            try:
                return d.replace(year=d.year - 1)
            except ValueError:  # 29 February
                return d.replace(year=d.year - 1, day=28)
        yr = self.year(d)
        prior = self.year(yr.start - timedelta(days=1))
        return min(prior.start + (d - yr.start), prior.end)

    def describe_year(self, d: date) -> dict[str, Any]:
        """The year containing ``d`` with its quarters and months, for the Settings preview."""
        yr = self.year(d)
        return {
            "year": yr.as_dict(),
            "quarters": [b.as_dict() for b in self.buckets(yr.start, yr.end, "quarter")],
            "months": [b.as_dict() for b in self.buckets(yr.start, yr.end, "month")],
            "weeks": len(self.buckets(yr.start, yr.end, "week")),
        }


def tenant_calendar(tenant_id: str = "default") -> BusinessCalendar:
    from app.services.commercial_tenant_profile import business_calendar_config

    return BusinessCalendar(business_calendar_config(tenant_id))
