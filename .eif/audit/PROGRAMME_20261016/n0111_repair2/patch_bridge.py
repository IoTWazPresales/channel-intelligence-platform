"""One-off patch for customer_stock_gap.py (N-0111 repair 2 bridge rule). Exact-match replaces; fails loudly."""

import pathlib

p = pathlib.Path("apps/api/app/services/channel_intelligence/customer_stock_gap.py")
s = p.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


sub(
    '''A Monday-Sunday week with no reported on-hand does not break the chain (N-0111, Warren
2026-10-16): that week is stored as its own row (status ``no_on_hand``, no on-hand, no gap) and
the chain restarts at the next reported on-hand (status ``chain_restart``, nothing compared). The unit gap is shown on every compared row;
a row is highlighted when ``|gap| >= stock_gap_highlight_units`` (tenant setting,
absolute units). The distributor 10 percent variance is not used here.
''',
    '''A Monday-Sunday week with no reported on-hand does not break the chain (N-0111, Warren
2026-10-16, correcting D-0105): the chain BRIDGES it. When on-hand is missing for some weeks but
sales are reported for every one of them, the next reported on-hand is compared with the last
reported on-hand plus matched deliveries minus all sales in between. Each such week is stored as
its own row (status ``no_on_hand``, its units kept, no on-hand, no gap) and is not compared itself.
The chain starts fresh only when sales are ALSO missing for a week in between: the next reported
on-hand is stored as ``chain_restart`` (shown as "Unreported weeks", a data gap; nothing compared).
A week with neither on-hand nor sales stores no row of its own. The unit gap is shown on every
compared row; a row is highlighted when ``|gap| >= stock_gap_highlight_units`` (tenant setting,
absolute units). The distributor 10 percent variance is not used here.
''',
)

sub(
    '''# N-0111: a Monday-Sunday week with no reported on-hand, and the report the chain restarts at.
STATUS_NO_ON_HAND = "no_on_hand"
STATUS_RESTART = "chain_restart"
''',
    '''# N-0111: a Monday-Sunday week with no reported on-hand (sales reported), and the report the chain
# starts fresh at because sales were also missing in between. ``chain_restart`` is the stored value
# (a CHECK constraint names it); the screens call it "Unreported weeks".
STATUS_NO_ON_HAND = "no_on_hand"
STATUS_RESTART = "chain_restart"
''',
)

sub(
    '''    period_year: int | None = None
    import_job_id: int | None = None


@dataclass
class Receipt:''',
    '''    period_year: int | None = None
    import_job_id: int | None = None
    # False when the stored rows of this period carry no units figure at all (stock-only rows).
    sales_reported: bool = True


@dataclass
class Receipt:''',
)

sub(
    '''def compute_positions(periods: Iterable[ReportPeriod], receipts: Iterable[Receipt]) -> list[Position]:
    """Pure: one position per report period that carries on-hand, in end-date order.

    Units sold count when a period ends after the previous report and by this one, so
    a sales-only period between two stock reports still reduces the expected position.

    N-0111: when a whole Monday-Sunday week between two on-hand reports has no on-hand, each such
    week gets a ``no_on_hand`` position and the later report restarts the chain
    (``chain_restart``): it is not compared with the report before the gap.
    """''',
    '''def _sales_cover(plist: list[ReportPeriod], monday: date) -> bool:
    """True when a period that reports units overlaps the Monday-Sunday week of ``monday``."""
    sunday = monday + timedelta(days=6)
    return any(p.sales_reported and p.start <= sunday and p.end >= monday for p in plist)


def compute_positions(periods: Iterable[ReportPeriod], receipts: Iterable[Receipt]) -> list[Position]:
    """Pure: one position per report period that carries on-hand, in end-date order.

    Units sold count when a period ends after the previous report and by this one, so
    a sales-only period between two stock reports still reduces the expected position.

    N-0111: whole Monday-Sunday weeks between two on-hand reports that have no on-hand are not
    compared themselves. If sales are reported for every one of them the chain bridges: each such
    week gets a ``no_on_hand`` position and the later report is compared with the last reported
    on-hand (plus matched deliveries, minus all sales in between). If sales are missing for any of
    those weeks the sum of sales is incomplete, so the later report starts a fresh chain
    (``chain_restart``, shown as "Unreported weeks") and is not compared.
    """''',
)

start = s.index("            missing = weeks_without_on_hand(prev.end, point.start)\n")
end = s.index("            sold = sum(\n                (p.units_sold for p in plist if prev.end < p.end <= point.end),")
s = (
    s[:start]
    + '''            missing = weeks_without_on_hand(prev.end, point.start)
            unreported = [m for m in missing if not _sales_cover(plist, m)]
            bridged = [m for m in missing if m not in unreported]
            for monday in bridged:
                sunday = monday + timedelta(days=6)
                in_week = [p for p in plist if monday <= p.end <= sunday]
                iso = monday.isocalendar()
                jobs = [p.import_job_id for p in in_week if p.import_job_id is not None]
                week = ReportPeriod(
                    product_id=product_id,
                    grain="week",
                    start=monday,
                    end=sunday,
                    units_sold=sum((p.units_sold for p in in_week), ZERO),
                    period_week=iso[1],
                    period_year=iso[0],
                    import_job_id=max(jobs) if jobs else None,
                )
                out.append(Position(period=week, status=STATUS_NO_ON_HAND))
            if unreported:
                out.append(
                    Position(
                        period=point,
                        status=STATUS_RESTART,
                        previous_end=prev.end,
                        previous_on_hand=prev.on_hand,
                        notes=[
                            f"no sales or on-hand reported for {len(unreported)} week(s) from {unreported[0].isoformat()}"
                        ],
                    )
                )
                prev = point
                continue
'''
    + s[end:]
)

sub(
    '''                    expected=expected,
                    gap=gap,
                )
            )
            prev = point
    return out''',
    '''                    expected=expected,
                    gap=gap,
                    notes=(
                        [f"bridged {len(bridged)} week(s) with no on-hand reported from {bridged[0].isoformat()}"]
                        if bridged
                        else []
                    ),
                )
            )
            prev = point
    return out''',
)

sub(
    '''    if status == STATUS_NO_ON_HAND:
        return "No on-hand reported for this week. The stock chain restarts at the next reported on-hand."
    if status == STATUS_RESTART:
        return "The stock chain restarts here: the week before had no on-hand reported. Nothing to compare."''',
    '''    if status == STATUS_NO_ON_HAND:
        return "No on-hand reported for this week. It is not compared; the next reported on-hand is compared across it."
    if status == STATUS_RESTART:
        return (
            "Unreported weeks: no on-hand and no sales were reported for some weeks since the previous "
            "on-hand report, so nothing is compared here. A data gap; the stock chain starts fresh."
        )''',
)

sub(
    '''                period_week=row.period_week,
                period_year=row.period_year,
            )
            grouped[key] = rp
        rp.units_sold += Decimal(str(row.units_sold or 0))''',
    '''                period_week=row.period_week,
                period_year=row.period_year,
                sales_reported=False,
            )
            grouped[key] = rp
        if row.units_sold is not None:
            rp.sales_reported = True
        rp.units_sold += Decimal(str(row.units_sold or 0))''',
)

p.write_text(s, encoding="utf-8")
print("patched")
