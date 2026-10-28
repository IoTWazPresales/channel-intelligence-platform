"""SQL for the few model rules that a column name cannot express.

The model file only names these; they are built here, in code, mirroring the owning service so
the compiler never reads an expression from configuration.

CPOR (``services/cpor/portfolio_intelligence.py`` and ``services/cpor/pivot.py``):

- cases: ``superseded_by_case_id IS NULL`` and ``where_commercial_intelligence()``
  (``intelligence_exclude IS false``), the portfolio service's own case filter, reused as is;
- lines: ``is_voided_line`` leaves out a line whose remark carries ``[voided]`` or
  ``[split into layers]`` (its second clause is implied by the first and by the next rule), and
  the portfolio service leaves out a line whose ``float(estimate_qty or 0) <= 0``;
- support USD per line: ``_line_ttl_support_usd`` = stored ``ttl_support_usd``, else
  ``support_usd * estimate_qty`` when the estimate is not zero, else nothing.

``tests/test_query_model_rules.py`` checks the SQL against those Python functions row by row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, func, literal_column
from sqlalchemy.sql import ColumnElement

# The remark markers is_voided_line looks for (services/cpor/pivot.py).
VOIDED_REMARK_MARKERS = ("[voided]", "[split into layers]")


def cpor_case_is_portfolio(case_t: Any) -> ColumnElement[bool]:
    """Non-superseded commercial case: the portfolio service's own case filter."""
    from app.services.cpor.intelligence_scope import where_commercial_intelligence

    # where_commercial_intelligence() is written against the mapped CporCase; rebind it to the
    # aliased table the compiler uses by reading its column name and comparison.
    crit = where_commercial_intelligence()
    col_name = crit.left.key  # intelligence_exclude
    return and_(case_t.c.superseded_by_case_id.is_(None), case_t.c[col_name].is_(False))


def cpor_line_not_voided(line_t: Any) -> ColumnElement[bool]:
    remark = func.coalesce(line_t.c.remark, literal_column("''"))
    conds = [func.strpos(remark, literal_column(f"'{m}'")) == 0 for m in VOIDED_REMARK_MARKERS]
    return and_(*conds)


def cpor_line_positive_estimate(line_t: Any) -> ColumnElement[bool]:
    return func.coalesce(line_t.c.estimate_qty, literal_column("0")) > 0


def cpor_portfolio_lines(aliases: dict[str, Any]) -> list[ColumnElement[bool]]:
    line_t = aliases["__base__"]
    case_t = aliases["case"]
    return [
        cpor_case_is_portfolio(case_t),
        cpor_line_not_voided(line_t),
        cpor_line_positive_estimate(line_t),
    ]


def cpor_line_support_usd(aliases: dict[str, Any]) -> ColumnElement[Any]:
    line_t = aliases["__base__"]
    return func.coalesce(
        line_t.c.ttl_support_usd,
        case(
            (line_t.c.estimate_qty != 0, line_t.c.support_usd * line_t.c.estimate_qty),
            else_=None,
        ),
    )


def lineup_current_cases(aliases: dict[str, Any]) -> list[ColumnElement[bool]]:
    """Current lineup cases, matching lineup_period_canonical: not cancelled or superseded."""
    case_t = aliases["case"]
    return [
        case_t.c.superseded_by_case_id.is_(None),
        case_t.c.commercial_status.notin_(("cancelled", "superseded")),
    ]


MODEL_RULES = {
    "cpor_portfolio_lines": cpor_portfolio_lines,
    "lineup_current_cases": lineup_current_cases,
}
MEASURE_RULES = {"cpor_line_support_usd": cpor_line_support_usd}
