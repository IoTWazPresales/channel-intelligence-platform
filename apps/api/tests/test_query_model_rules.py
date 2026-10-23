"""N-0115: the CPOR SQL rules agree with the portfolio service's own Python, row by row.

The compiler cannot call ``is_voided_line`` or ``_line_ttl_support_usd`` inside SQL, so
``app/query/model/rules.py`` builds their SQL counterparts. This test evaluates those SQL
expressions over a VALUES list on cip_test (no writes) and compares every row with the Python
functions the portfolio service uses.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import Boolean, Integer, Numeric, Text, column, select, text, values

from app.db.session import AsyncSessionLocal
from app.query.model.rules import (
    cpor_case_is_portfolio,
    cpor_line_not_voided,
    cpor_line_positive_estimate,
    cpor_line_support_usd,
)
from app.services.cpor.pivot import _line_ttl_support_usd, is_voided_line

LINES = [
    # remark, estimate_qty, ttl_support_usd, support_usd
    (None, Decimal("10"), None, Decimal("2.5")),
    ("[voided]", Decimal("10"), None, Decimal("2.5")),
    ("moved [voided] by steward", Decimal("0"), None, None),
    ("[split into layers]", Decimal("3"), Decimal("9"), Decimal("1")),
    ("[split", Decimal("0"), None, Decimal("1")),
    ("[split", Decimal("4"), None, Decimal("1")),
    ("VOIDED", Decimal("4"), None, Decimal("1")),
    ("", Decimal("-2"), None, Decimal("1")),
    ("ok", Decimal("5"), Decimal("0"), Decimal("7")),
    ("ok", Decimal("5"), None, None),
    ("ok", Decimal("0"), None, Decimal("7")),
]


@pytest.mark.anyio
async def test_cpor_line_rules_match_the_portfolio_python():
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        v = values(
            column("i", Integer),
            column("remark", Text),
            column("estimate_qty", Numeric),
            column("ttl_support_usd", Numeric),
            column("support_usd", Numeric),
            name="l",
        ).data([(i, *row) for i, row in enumerate(LINES)])
        aliases = {"__base__": v}
        stmt = select(
            v.c.i,
            cpor_line_not_voided(v).label("kept"),
            cpor_line_positive_estimate(v).label("pos"),
            cpor_line_support_usd(aliases).label("usd"),
        ).order_by(v.c.i)
        rows = (await db.execute(stmt)).all()
        await db.rollback()
    for r in rows:
        remark, est, ttl, usd = LINES[r.i]
        line = SimpleNamespace(remark=remark, estimate_qty=est, ttl_support_usd=ttl, support_usd=usd)
        try:
            portfolio_keeps = not is_voided_line(line) and float(line.estimate_qty or 0) > 0
        except (TypeError, ValueError):
            portfolio_keeps = False
        assert (bool(r.kept) and bool(r.pos)) == portfolio_keeps, LINES[r.i]
        py_usd = _line_ttl_support_usd(line)
        assert (None if r.usd is None else float(r.usd)) == py_usd, LINES[r.i]


@pytest.mark.anyio
async def test_cpor_case_rule_is_the_portfolio_case_filter():
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        cases = [(1, None, False), (2, 9, False), (3, None, True), (4, 9, True)]
        v = values(
            column("i", Integer), column("superseded_by_case_id", Integer), column("intelligence_exclude", Boolean), name="c"
        ).data(cases)
        rows = (await db.execute(select(v.c.i, cpor_case_is_portfolio(v).label("kept")).order_by(v.c.i))).all()
        await db.rollback()
    assert [bool(r.kept) for r in rows] == [True, False, False, False]
