"""Period buckets as SQL expressions that match ``BusinessCalendar``.

A non-default calendar used to be a ``CASE`` with one arm per bucket from 2016 through
2036. At week grain that is about a thousand arms and was about seven times slower than
``date_trunc``. Weeks are a weekday shift. Gregorian months, quarters and years are date
arithmetic. Retail 4-4-5 / 4-5-4 / 5-4-4 years are the same year-end rule as
``BusinessCalendar``, then a week index. A custom calendar is a short ``CASE`` over the
periods the tenant listed, and any day outside that list uses the gregorian fallback the
Python calendar uses.

``tests/test_e10_calendar_values_db.py`` runs these expressions on Postgres and compares
them with ``BusinessCalendar.bucket``.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import count
from typing import Any

from sqlalchemy import Date, Integer, and_, bindparam, case, cast, func, literal_column
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.expression import FunctionElement

from app.services.business_calendar import _RETAIL_PATTERNS, BusinessCalendar

_BINDS = count()


def _date_bind(prefix: str, value: date) -> ColumnElement[Any]:
    return bindparam(f"{prefix}_{next(_BINDS)}", value=value, type_=Date)


def _as_date(expr: Any) -> ColumnElement[Any]:
    return cast(expr, Date)


def _add_days(expr: Any, days: int) -> ColumnElement[Any]:
    sign = "-" if days < 0 else ""
    return _as_date(expr + literal_column(f"interval '{sign}{abs(days)} days'"))


def _add_day_count(expr: Any, n_days: Any) -> ColumnElement[Any]:
    """``expr`` plus ``n_days`` days. ``n_days`` is an integer SQL expression."""
    return _as_date(_as_date(expr) + n_days * literal_column("interval '1 day'"))


def _days_between(later: Any, earlier: Any) -> ColumnElement[Any]:
    return _as_date(later) - _as_date(earlier)


def _week_start(col: Any, week_start_day: int) -> ColumnElement[Any]:
    """Week starting on ``week_start_day`` (0 Monday … 6 Sunday), matching ``BusinessCalendar.week_start``."""
    weekday = cast(func.extract("isodow", col), Integer) - 1
    back = cast(func.mod(weekday - week_start_day + 7, 7), Integer)
    return _add_day_count(col, -back)


def _pattern_bounds(pattern: tuple[int, ...]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    w = 0
    for _q in range(4):
        for n in pattern:
            out.append((w, w + n - 1))
            w += n
    return out


def _year_end_sql(year_sql: str, end_month: int, week_end: int, nearest: int) -> str:
    """One retail year-end. ``date - int`` and ``date + int`` are PostgreSQL day shifts."""
    return (
        "(SELECT CASE WHEN "
        f"{int(nearest)} = 1 AND s.back > 3 THEN (s.ended + 7) ELSE s.ended END "
        "FROM (SELECT (s2.last_day - s2.back) AS ended, s2.back FROM ("
        "SELECT last_day, mod((EXTRACT(isodow FROM last_day)::int - 1) - "
        f"{int(week_end)} + 7, 7) AS back FROM ("
        f"SELECT (make_date({year_sql}, {int(end_month)}, 1) + interval '1 month' "
        "- interval '1 day')::date AS last_day) ld) s2) s)"
    )


def _year_bounds_sql(date_sql: str, end_month: int, week_end: int, nearest: int) -> str:
    y = f"EXTRACT(year FROM ({date_sql})::date)::int"
    aliases = [("em3", -3), ("em2", -2), ("em1", -1), ("e0", 0), ("e1", 1), ("e2", 2)]
    cols = ", ".join(
        f"{_year_end_sql(f'({y})+({k})', end_month, week_end, nearest)} AS {name}"
        for name, k in aliases
    )
    return (
        "SELECT "
        "CASE WHEN d <= em2 THEN em3 + 1 WHEN d <= em1 THEN em2 + 1 "
        "WHEN d <= e0 THEN em1 + 1 WHEN d <= e1 THEN e0 + 1 ELSE e1 + 1 END AS ys, "
        "CASE WHEN d <= em2 THEN em2 WHEN d <= em1 THEN em1 "
        "WHEN d <= e0 THEN e0 WHEN d <= e1 THEN e1 ELSE e2 END AS ye, "
        f"({date_sql})::date AS d "
        f"FROM (SELECT ({date_sql})::date AS d, {cols}) ends"
    )


def _retail_sql(col_sql: str, kind: str, grain: str, calendar: BusinessCalendar) -> str:
    end_month = calendar.start_month - 1 or 12
    week_end = (calendar.week_start_day - 1) % 7
    nearest = 1 if calendar.config["year_end_rule"] == "nearest" else 0
    bounds = _pattern_bounds(_RETAIL_PATTERNS[calendar.type])
    if kind == "prior":
        cur = _year_bounds_sql(col_sql, end_month, week_end, nearest)
        prev = _year_bounds_sql("(cur.ys - 1)", end_month, week_end, nearest)
        shifted = "LEAST(prev.ys + (cur.d - cur.ys), prev.ye)"
        # A 53rd week clamps to the prior year-end, which is a week-ending day. The prior
        # bucket is the week that contains that day. Other grains are already aligned.
        if grain == "week":
            chosen = (
                "s.shifted - mod((EXTRACT(isodow FROM s.shifted)::int - 1) - "
                f"{int(calendar.week_start_day)} + 7, 7)"
            )
        else:
            chosen = "s.shifted"
        return (
            f"(SELECT {chosen} FROM (SELECT {shifted} AS shifted FROM ("
            f"{cur}) cur JOIN LATERAL ({prev}) prev ON true) s)"
        )
    body = _year_bounds_sql(col_sql, end_month, week_end, nearest)
    week_idx = "((b.d - b.ys) / 7)"
    whens = " ".join(
        f"WHEN {week_idx} BETWEEN {a} AND {b} THEN {i}" for i, (a, b) in enumerate(bounds[:-1])
    )
    pidx = f"(CASE {whens} ELSE {len(bounds) - 1} END)"
    week_of = " ".join(f"WHEN {i} THEN {a}" for i, (a, _b) in enumerate(bounds))
    if kind == "end":
        nxt = " ".join(f"WHEN {i} THEN {bounds[i + 1][0]}" for i in range(len(bounds) - 1))
        q_nxt = (
            f"WHEN 0 THEN {bounds[3][0]} WHEN 1 THEN {bounds[6][0]} "
            f"WHEN 2 THEN {bounds[9][0]} ELSE {bounds[9][0]}"
        )
        if grain == "year":
            chosen = "(b.ye + 1)"
        elif grain == "quarter":
            chosen = (
                f"CASE WHEN ({pidx} / 3) < 3 THEN b.ys + (CASE ({pidx} / 3) {q_nxt} END) * 7 "
                "ELSE b.ye + 1 END"
            )
        else:
            chosen = (
                f"CASE WHEN {pidx} < {len(bounds) - 1} THEN b.ys + (CASE {pidx} {nxt} END) * 7 "
                "ELSE b.ye + 1 END"
            )
    elif grain == "year":
        chosen = "b.ys"
    elif grain == "month":
        chosen = f"b.ys + (CASE {pidx} {week_of} END) * 7"
    else:
        q_of = (
            f"WHEN 0 THEN {bounds[0][0]} WHEN 1 THEN {bounds[3][0]} "
            f"WHEN 2 THEN {bounds[6][0]} ELSE {bounds[9][0]}"
        )
        chosen = f"b.ys + (CASE ({pidx} / 3) {q_of} END) * 7"
    return f"(SELECT {chosen} FROM ({body}) b)"


class _RetailExpr(FunctionElement):
    """Retail calendar math as one SQL string. A clause tree clones itself until the statement is megabytes."""

    inherit_cache = False
    name = "retail_cal"
    type = Date()

    def __init__(self, col: Any, kind: str, grain: str, calendar: BusinessCalendar):
        self.kind = kind
        self.grain = grain
        self.calendar = calendar
        super().__init__(col)


@compiles(_RetailExpr, "postgresql")
def _compile_retail_expr(element: _RetailExpr, compiler: Any, **kw: Any) -> str:
    col_sql = compiler.process(element.clauses.clauses[0], **kw)
    return _retail_sql(col_sql, element.kind, element.grain, element.calendar)


def _gregorian_year_bounds(col: Any, calendar: BusinessCalendar) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    d = _as_date(col)
    y = cast(func.extract("year", d), Integer)
    m = cast(func.extract("month", d), Integer)
    start_year = case((m >= calendar.start_month, y), else_=y - 1)
    start = func.make_date(start_year, calendar.start_month, 1)
    end = _as_date(start + literal_column("interval '1 year'") - literal_column("interval '1 day'"))
    return start, end


def _custom_span(calendar: BusinessCalendar) -> tuple[date, date]:
    periods = calendar.config["custom_periods"]
    first = date.fromisoformat(periods[0]["start"])
    last = date.fromisoformat(periods[-1]["start"])
    return first, calendar.bucket(last, "month").end


def _span_case(col: Any, buckets: list[Any], else_expr: Any, prefix: str, *, value: str) -> ColumnElement[Any]:
    """``value`` is ``start`` or ``end``: the date returned when ``col`` falls in the bucket."""
    d = _as_date(col)
    whens = []
    for b in buckets:
        inside = and_(d >= _date_bind(prefix, b.start), d <= _date_bind(prefix, b.end))
        chosen = b.start if value == "start" else b.end
        whens.append((inside, _date_bind(prefix, chosen)))
    return case(*whens, else_=else_expr)


def _year_bounds(col: Any, calendar: BusinessCalendar) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    if calendar.type == "gregorian":
        return _gregorian_year_bounds(col, calendar)
    greg = BusinessCalendar({**calendar.config, "type": "gregorian", "custom_periods": []})
    g_start, g_end = _gregorian_year_bounds(col, greg)
    first, last_end = _custom_span(calendar)
    years = calendar.buckets(first, last_end, "year")
    return (
        _span_case(col, years, g_start, "cyst", value="start"),
        _span_case(col, years, g_end, "cyen", value="end"),
    )


def _same_day_last_year(col: Any, calendar: BusinessCalendar) -> ColumnElement[Any]:
    if calendar.type == "gregorian":
        return _as_date(_as_date(col) - literal_column("interval '1 year'"))
    ys, _ye = _year_bounds(col, calendar)
    ps, pe = _year_bounds(_add_days(ys, -1), calendar)
    offset = _days_between(col, ys)
    return _as_date(func.least(_add_day_count(ps, offset), pe))


def _gregorian_quarter_start(col: Any, calendar: BusinessCalendar) -> ColumnElement[Any]:
    if calendar.start_month == 1:
        return _as_date(func.date_trunc(literal_column("'quarter'"), col))
    d = _as_date(col)
    y = cast(func.extract("year", d), Integer)
    m = cast(func.extract("month", d), Integer)
    shifted = func.mod(m - calendar.start_month + 12, 12)
    q_index = cast(func.floor(shifted / 3), Integer)
    first_month = cast(func.mod(calendar.start_month - 1 + q_index * 3, 12) + 1, Integer)
    qy = case((first_month <= m, y), else_=y - 1)
    return func.make_date(qy, first_month, 1)


def _custom_bucket_start(col: Any, grain: str, calendar: BusinessCalendar) -> ColumnElement[Any]:
    greg = BusinessCalendar({**calendar.config, "type": "gregorian", "custom_periods": []})
    first, last_end = _custom_span(calendar)
    buckets = calendar.buckets(first, last_end, grain)
    return _span_case(col, buckets, bucket_start_expr(col, grain, greg), f"cu{grain}", value="start")


def _custom_end_exclusive(start_col: Any, grain: str, calendar: BusinessCalendar) -> ColumnElement[Any]:
    greg = BusinessCalendar({**calendar.config, "type": "gregorian", "custom_periods": []})
    first, last_end = _custom_span(calendar)
    buckets = calendar.buckets(first, last_end, grain)
    d = _as_date(start_col)
    whens = [
        (d == _date_bind(f"cue{grain}", b.start), _date_bind(f"cue{grain}", b.end + timedelta(days=1)))
        for b in buckets
    ]
    return case(*whens, else_=bucket_end_exclusive(start_col, grain, greg))


def bucket_start_expr(col: Any, grain: str, calendar: BusinessCalendar) -> ColumnElement[Any]:
    """Bucket start for a non-platform calendar. ``calendar`` is a ``BusinessCalendar``."""
    if grain == "day":
        return _as_date(col)
    if grain == "week":
        return _week_start(col, calendar.week_start_day)
    if calendar.type == "gregorian":
        if grain == "month":
            return _as_date(func.date_trunc(literal_column("'month'"), col))
        if grain == "quarter":
            return _gregorian_quarter_start(col, calendar)
        return _gregorian_year_bounds(col, calendar)[0]
    if calendar.type in _RETAIL_PATTERNS:
        return _RetailExpr(col, "start", grain, calendar)
    return _custom_bucket_start(col, grain, calendar)


def bucket_end_exclusive(start_col: Any, grain: str, calendar: BusinessCalendar) -> ColumnElement[Any]:
    """Exclusive end of the bucket whose start is ``start_col``."""
    if grain == "day":
        return _add_days(start_col, 1)
    if grain == "week":
        return _add_days(start_col, 7)
    if calendar.type == "gregorian":
        step = {"month": "1 month", "quarter": "3 months", "year": "1 year"}[grain]
        return _as_date(_as_date(start_col) + literal_column(f"interval '{step}'"))
    if calendar.type in _RETAIL_PATTERNS:
        return _RetailExpr(start_col, "end", grain, calendar)
    return _custom_end_exclusive(start_col, grain, calendar)


def prior_year_bucket_expr(col: Any, grain: str, calendar: BusinessCalendar) -> ColumnElement[Any]:
    """Bucket start of the same bucket one financial year earlier.

    A retail period or week starts a whole number of weeks after its year start, so the
    prior bucket is that same offset in the previous year. The shift is one SQL subquery,
    not the year-end expression pasted into itself.
    """
    if calendar.type in _RETAIL_PATTERNS:
        return _RetailExpr(col, "prior", grain, calendar)
    return bucket_start_expr(_same_day_last_year(col, calendar), grain, calendar)
