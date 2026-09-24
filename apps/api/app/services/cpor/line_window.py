"""CPOR line effective windows (BACKLOG-137 / D-058 / CPOR_SETTLEMENT_SPEC §3).

Week convention: Monday–Sunday (SPEC_CPOR_V1 U4.5 "Week convention Mon–Sun";
same as ``iso_week_start`` in ``services/imports/dsi_coverage.py``). A window is
week-aligned when it starts on a Monday and ends on a Sunday.

Case windows are "usually but not always Mon–Sun", so a line window that is not
week-aligned is stored as-is and FLAGGED (``window_week_straddle``): the week
that contains a mid-week boundary is never snapped and never pro-rated.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine

FLAG_WINDOW_WEEK_STRADDLE = "window_week_straddle"


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def is_week_aligned(start: date, end: date) -> bool:
    return start.weekday() == 0 and end.weekday() == 6


def straddle_weeks(start: date, end: date) -> list[date]:
    """Mondays of the weeks cut by a mid-week window boundary (0, 1 or 2 weeks)."""
    weeks: list[date] = []
    if start.weekday() != 0:
        weeks.append(week_monday(start))
    if end.weekday() != 6:
        wk = week_monday(end)
        if wk not in weeks:
            weeks.append(wk)
    return weeks


def default_line_window(case: CporCase) -> tuple[date, date]:
    """Creation default: the line runs for the whole case window."""
    return case.window_start, case.window_end


def effective_line_window(line: CporCaseLine, case: CporCase) -> tuple[date | None, date | None]:
    """Line window when present, else the case window."""
    ws = getattr(line, "window_start", None) or case.window_start
    we = getattr(line, "window_end", None) or case.window_end
    return ws, we


def line_window_info(line: CporCaseLine, case: CporCase) -> dict[str, Any]:
    ws, we = effective_line_window(line, case)
    if ws is None or we is None:
        return {"window_start": None, "window_end": None, "week_aligned": None, "straddle_weeks": []}
    return {
        "window_start": ws.isoformat(),
        "window_end": we.isoformat(),
        "week_aligned": is_week_aligned(ws, we),
        "straddle_weeks": [w.isoformat() for w in straddle_weeks(ws, we)],
    }


def follow_case_window(
    session: Session,
    case_id: int,
    *,
    old_start: date | None,
    old_end: date | None,
    new_start: date,
    new_end: date,
) -> int:
    """Move lines still on the old case window to the new case window.

    Lines with their own (superseded / narrower) window are left alone.
    Callers only use this on pre-approval edits and historical re-import.
    """
    if old_start is None or old_end is None:
        return 0
    if (old_start, old_end) == (new_start, new_end):
        return 0
    res = session.execute(
        update(CporCaseLine)
        .where(
            CporCaseLine.case_id == case_id,
            CporCaseLine.window_start == old_start,
            CporCaseLine.window_end == old_end,
        )
        .values(window_start=new_start, window_end=new_end)
        .execution_options(synchronize_session="fetch")
    )
    return int(res.rowcount or 0)
