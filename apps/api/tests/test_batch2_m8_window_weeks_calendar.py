"""GOV-008 M8: a per-week total agrees with its own rows on a non-platform calendar when no window is set.

The review's numbers: Sunday week, units 7 + 7 in one week: row 14 per week, total 7 per week (weeks counted on the Monday
Gregorian week). Retail 4-4-5 month of five weeks: row 2.8, total 3.16 (weeks counted on the Gregorian month).
cip_test only; every test rolls back.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactSalesSellout
from app.query.model.calc import window_weeks
from app.query.model.execute import run_v2
from app.query.model.graph import V2Request
from app.services.business_calendar import BusinessCalendar

TAG = secrets.token_hex(4)
TENANT = f"m8-{TAG}"
PER_WEEK = "dsi_sellout.units_per_week"


def test_window_weeks_uses_the_calendar_buckets_when_given():
    sunday = BusinessCalendar({"week_start_day": 6})
    # 1 Mar 2026 is a Sunday: the Sunday week is 1-7 Mar = exactly one week.
    assert float(window_weeks(period_from=None, period_to=None, grain="week", vintage_min=date(2026, 3, 1),
                              vintage_max=date(2026, 3, 7), calendar=sunday)) == 1.0
    # Without the calendar the Monday week is used (two Gregorian weeks): the old, platform behaviour.
    assert float(window_weeks(period_from=None, period_to=None, grain="week", vintage_min=date(2026, 3, 1),
                              vintage_max=date(2026, 3, 7))) == 2.0
    retail = BusinessCalendar({"type": "retail_445"})
    month = retail.bucket(date(2026, 3, 10), "month")
    assert float(window_weeks(period_from=None, period_to=None, grain="month", vintage_min=date(2026, 3, 10),
                              vintage_max=date(2026, 3, 10), calendar=retail)) == (month.end - month.start).days / 7 + 1 / 7


@pytest.fixture
async def world(monkeypatch):
    db = AsyncSessionLocal()
    assert (await db.execute(text("select current_database()"))).scalar_one() == "cip_test"
    product = DimProduct(sku=f"m8{TAG}"[-32:], name=f"M8 {TAG}", tenant_id=TENANT)
    customer = DimCustomer(code=f"m8c{TAG}"[-32:], name=f"M8C {TAG}", tenant_id=TENANT)
    db.add_all([product, customer])
    await db.flush()

    def use(cal):
        monkeypatch.setattr("app.services.business_calendar.tenant_calendar", lambda tid: cal)

    n = {"i": 0}

    async def sell(day, units):
        n["i"] += 1
        db.add(FactSalesSellout(source_key=f"m8-{TAG}-{n['i']}", tenant_id=TENANT, product_id=product.id,
                                customer_id=customer.id, period_start=day, transaction_date=day, units=units, revenue=0))
        await db.flush()

    try:
        yield db, customer, use, sell
    finally:
        await db.rollback()
        await db.close()


async def _per_week(db, customer, grain):
    req = V2Request(measures=["dsi_sellout.units", PER_WEEK], breakdowns=["period"], period_grain=grain,
                    filters={"customer": customer.id})
    res = await run_v2(db, req, tenant_id=TENANT, skip_cache=True)
    assert res["ok"], res
    return res


@pytest.mark.anyio
async def test_sunday_week_total_equals_its_only_row(world):
    db, customer, use, sell = world
    use(BusinessCalendar({"week_start_day": 6}))
    await sell(date(2026, 3, 1), 7)
    await sell(date(2026, 3, 7), 7)
    res = await _per_week(db, customer, "week")
    assert len(res["rows"]) == 1
    row = res["rows"][0][PER_WEEK]
    assert row == 14.0 and res["totals"][PER_WEEK] == 14.0, (row, res["totals"])


@pytest.mark.anyio
async def test_retail_month_total_equals_its_only_row(world):
    db, customer, use, sell = world
    cal = BusinessCalendar({"type": "retail_445"})
    use(cal)
    month = cal.bucket(date(2026, 3, 10), "month")
    await sell(month.start, 7)
    await sell(month.end, 7)
    res = await _per_week(db, customer, "month")
    assert len(res["rows"]) == 1
    weeks = ((month.end - month.start).days + 1) / 7
    assert res["rows"][0][PER_WEEK] == pytest.approx(14 / weeks)
    assert res["totals"][PER_WEEK] == pytest.approx(res["rows"][0][PER_WEEK])


@pytest.mark.anyio
async def test_platform_calendar_total_is_unchanged(world):
    db, customer, use, sell = world
    use(BusinessCalendar({}))
    await sell(date(2026, 3, 2), 7)  # Monday week 2-8 Mar
    await sell(date(2026, 3, 8), 7)
    res = await _per_week(db, customer, "week")
    assert res["rows"][0][PER_WEEK] == 14.0 and res["totals"][PER_WEEK] == 14.0
