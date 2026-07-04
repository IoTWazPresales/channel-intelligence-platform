"""Tenant-configurable fiscal calendar for lineup 1H quarter allocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.config import get_settings


@dataclass(frozen=True)
class FiscalCalendarConfig:
    """Fiscal year anchor month (1=January … 12=December). Drives month→quarter and 1H split."""

    fiscal_year_start_month: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.fiscal_year_start_month <= 12:
            raise ValueError(f"fiscal_year_start_month must be 1-12, got {self.fiscal_year_start_month!r}")


def get_lineup_fiscal_calendar_config() -> FiscalCalendarConfig:
    month = int(get_settings().lineup_fiscal_year_start_month)
    return FiscalCalendarConfig(fiscal_year_start_month=month)


def fiscal_quarter_for_calendar_month(month: int, config: FiscalCalendarConfig) -> int:
    """Map calendar month (1-12) to fiscal quarter 1-4."""
    if not 1 <= month <= 12:
        raise ValueError(f"calendar month must be 1-12, got {month}")
    offset = (month - config.fiscal_year_start_month) % 12
    return offset // 3 + 1


def calendar_months_in_fiscal_quarter(fiscal_quarter: int, config: FiscalCalendarConfig) -> frozenset[int]:
    """Calendar months belonging to a fiscal quarter (1-4)."""
    if fiscal_quarter not in (1, 2, 3, 4):
        raise ValueError(f"fiscal_quarter must be 1-4, got {fiscal_quarter}")
    return frozenset(
        m for m in range(1, 13) if fiscal_quarter_for_calendar_month(m, config) == fiscal_quarter
    )


def first_half_fiscal_quarters(config: FiscalCalendarConfig) -> tuple[int, int]:
    """1H always spans the first two fiscal quarters."""
    _ = config
    return 1, 2


def calendar_months_in_first_half(config: FiscalCalendarConfig) -> frozenset[int]:
    q1, q2 = first_half_fiscal_quarters(config)
    return calendar_months_in_fiscal_quarter(q1, config) | calendar_months_in_fiscal_quarter(q2, config)


def half_year_period_starts(calendar_year: int, config: FiscalCalendarConfig) -> tuple[date, date]:
    """Period-start dates for the two quarters in a 1H split."""
    q1_months = calendar_months_in_fiscal_quarter(1, config)
    q2_months = calendar_months_in_fiscal_quarter(2, config)
    q1_start = date(calendar_year, min(q1_months), 1)
    q2_start = date(calendar_year, min(q2_months), 1)
    if q2_start < q1_start:
        q2_start = date(calendar_year + 1, min(q2_months), 1)
    return q1_start, q2_start
