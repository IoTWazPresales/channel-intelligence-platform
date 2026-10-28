"""Value-level calendar and shipment checks (cip_test only, one rolled-back transaction).

The committed E8 tests compare SQL text. These execute the compiled statements and
compare bucket starts, previous period, prior year, and the other calculated kinds
with BusinessCalendar. Shipment quantity uses the strict-pair remainder and
resolved_customer_id.
"""

from __future__ import annotations

import secrets
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Date, column, select, text, values

from app.db.session import AsyncSessionLocal
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInboundShipment, FactSalesSellout
from app.query.model.calendar_sql import prior_year_bucket_expr
from app.query.model.compiler import bucket_expr, compile_plan, platform_calendar
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.semantics.registry import load_catalog
from app.services.business_calendar import BusinessCalendar

TAG = secrets.token_hex(4)
TENANT = f"e10-{TAG}"
_seq = 0

CALC = [
    "dsi_sellout.units",
    "dsi_sellout.units_prior_period",
    "dsi_sellout.units_change",
    "dsi_sellout.units_pct_change",
    "dsi_sellout.units_per_week",
    "dsi_sellout.units_prior_year",
    "dsi_sellout.units_running_total",
    "dsi_sellout.units_share",
]


def _custom() -> BusinessCalendar:
    """Periods on the 5th, from 2024 through 2027, so a year has a previous and a next year."""
    periods = []
    cursor = date(2024, 1, 5)
    for _ in range(48):
        periods.append({
            "start": cursor.isoformat(),
            "fiscal_year": cursor.year,
            "quarter": (cursor.month - 1) // 3 + 1,
        })
        month = cursor.month + 1
        year = cursor.year + (1 if month > 12 else 0)
        cursor = date(year, 1 if month > 12 else month, 5)
    return BusinessCalendar({"type": "custom", "custom_periods": periods})


CALENDARS = [
    BusinessCalendar(),
    BusinessCalendar({"week_start_day": 6}),
    BusinessCalendar({"fiscal_year_start_month": 4}),
    BusinessCalendar({"type": "retail_445"}),
    BusinessCalendar({"type": "retail_445", "week_start_day": 6, "year_end_rule": "nearest"}),
    BusinessCalendar({"type": "retail_454"}),
    BusinessCalendar({"type": "retail_544"}),
    _custom(),
]


def _key(prefix: str) -> str:
    global _seq
    _seq += 1
    return f"e10-{TAG}-{prefix}-{_seq}"


def _dates(start: date, stop: date):
    d = start
    while d <= stop:
        yield d
        d += timedelta(days=1)


def _as_date(value):
    if value is None:
        return None
    if type(value) is date:
        return value
    return value.date()


async def _db():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        pytest.skip("cip_test only")
    return db


def _prev_expr(col, grain: str, cal: BusinessCalendar):
    from sqlalchemy import literal_column

    if platform_calendar(cal):
        step = {"day": "1 day", "week": "1 week", "month": "1 month", "quarter": "3 months", "year": "1 year"}[grain]
        from sqlalchemy import Date as DateType, cast
        return cast(col - literal_column(f"interval '{step}'"), DateType)
    from sqlalchemy import literal_column as lit
    return bucket_expr(col - lit("interval '1 day'"), grain, cal)


def _prior_expr(col, grain: str, cal: BusinessCalendar):
    from sqlalchemy import literal_column

    if platform_calendar(cal):
        return bucket_expr(col - literal_column("interval '1 year'"), grain, None)
    return prior_year_bucket_expr(col, grain, cal)


async def _compare_buckets(db, cal: BusinessCalendar, grain: str) -> None:
    start, stop = date(2023, 1, 1), date(2026, 12, 31)
    day = column("day", Date)
    listed = list(_dates(start, stop))
    src = values(day).data([(d,) for d in listed]).alias("days")
    stmt = select(
        src.c.day,
        bucket_expr(src.c.day, grain, cal).label("bucket"),
        _prev_expr(src.c.day, grain, cal).label("prev"),
        _prior_expr(src.c.day, grain, cal).label("py"),
    )
    rows = (await db.execute(stmt)).all()
    assert len(rows) == len(listed)
    by_day = {_as_date(r.day): r for r in rows}
    mismatches = []
    for d in listed:
        got = by_day[d]
        bucket = _as_date(got.bucket)
        expect = cal.bucket(d, grain).start
        if bucket != expect:
            mismatches.append((str(cal.type), grain, d, bucket, expect))
            if len(mismatches) >= 5:
                break
    assert not mismatches, mismatches

    for b in cal.buckets(start, stop, grain):
        got = by_day.get(b.start)
        if got is None:
            continue
        prev = _as_date(got.prev)
        py = _as_date(got.py)
        assert prev == cal.bucket(b.start - timedelta(days=1), grain).start, (cal.type, grain, b.start, prev)
        assert py == cal.bucket(cal.same_day_last_year(b.start), grain).start, (cal.type, grain, b.start, py)


@pytest.mark.anyio
async def test_bucket_sql_matches_the_business_calendar():
    db = await _db()
    try:
        for cal in CALENDARS:
            for grain in ("day", "week", "month", "quarter", "year"):
                await _compare_buckets(db, cal, grain)
    finally:
        await db.rollback()
        await db.close()


def _scenario(cal: BusinessCalendar, grain: str):
    for b in cal.buckets(date(2024, 6, 1), date(2026, 12, 31), grain):
        if b.start < date(2026, 1, 1):
            continue
        prev = cal.bucket(b.start - timedelta(days=1), grain)
        py = cal.bucket(cal.same_day_last_year(b.start), grain)
        nxt = cal.bucket(b.end + timedelta(days=1), grain)
        if py.end < b.start and prev.end < b.start and nxt.start > b.end:
            return b, prev, py, nxt
    raise AssertionError(f"no usable bucket for {cal.type} {grain}")


async def _run(db, measures, breakdowns, grain, cal, *, tenant, period_from, period_to, filters=None):
    clear_model_cache()
    dm = default_model()
    req = V2Request(
        measures=list(measures),
        breakdowns=list(breakdowns),
        period_grain=grain,
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        filters=dict(filters or {}),
    )
    plan = plan_request(dm, req, v1_catalog=load_catalog())
    assert plan.ok, plan.refusals
    compiled = compile_plan(dm, plan, tenant_id=tenant, calendar=cal)
    rows = (await db.execute(compiled.rows)).mappings().all()
    return rows, compiled


def _num(v):
    if v is None:
        return None
    return float(v)


@pytest.mark.anyio
async def test_calculated_kinds_match_the_calendar_on_every_type():
    db = await _db()
    try:
        product = DimProduct(sku=_key("sku")[-32:], name=f"E10 {TAG}", sales_model_name=f"E10 {TAG}", tenant_id=TENANT)
        distributor = DimDistributor(code=_key("dist")[-32:], name=f"Dist {TAG}", tenant_id=TENANT)
        db.add_all([product, distributor])
        await db.flush()
        for cal in CALENDARS:
            for grain in ("week", "month", "quarter", "year"):
                current, prev, prior, nxt = _scenario(cal, grain)
                customer = DimCustomer(code=_key("cust")[-32:], name=f"Cust {TAG}", tenant_id=TENANT)
                db.add(customer)
                await db.flush()
                extra_day = current.start + timedelta(days=1)
                extra = 5 if cal.bucket(extra_day, grain).start == current.start else 0
                # A year grain's previous bucket is the prior year, so one row serves both measures.
                if prev.start == prior.start:
                    prior_units = 100
                    points = [(current.start, 10), (prev.start, prior_units), (nxt.start, 3)]
                else:
                    prior_units = 7
                    points = [
                        (current.start, 10),
                        (prev.start, 7),
                        (prior.start, 100),
                        (nxt.start, 3),
                    ]
                if extra:
                    points.append((extra_day, extra))
                for day, units in points:
                    db.add(FactSalesSellout(
                        source_key=_key("so"), tenant_id=TENANT, product_id=product.id, customer_id=customer.id,
                        distributor_id=distributor.id, period_start=day, transaction_date=day,
                        units=units, revenue=0,
                    ))
                await db.flush()
                rows, compiled = await _run(
                    db, CALC, ["period"], grain, cal, tenant=TENANT,
                    period_from=current.start, period_to=nxt.end, filters={"customer": customer.id},
                )
                got = {}
                for row in rows:
                    bs = _as_date(row["bucket_start"])
                    got[bs] = {mid: _num(row[lab]) for mid, lab in compiled.measure_labels.items()}
                current_units = 10 + extra
                assert set(got) == {current.start, nxt.start}, (cal.type, grain, sorted(got))
                cur = got[current.start]
                nx = got[nxt.start]
                assert cur["dsi_sellout.units"] == current_units
                assert cur["dsi_sellout.units_prior_period"] == prior_units
                assert cur["dsi_sellout.units_prior_year"] == 100
                assert cur["dsi_sellout.units_change"] == current_units - prior_units
                assert cur["dsi_sellout.units_pct_change"] == pytest.approx((current_units - prior_units) / prior_units)
                assert cur["dsi_sellout.units_running_total"] == current_units
                assert cur["dsi_sellout.units_share"] == pytest.approx(current_units / (current_units + 3))
                assert cur["dsi_sellout.units_per_week"] == pytest.approx(current_units * 7 / current.days)
                assert nx["dsi_sellout.units"] == 3
                assert nx["dsi_sellout.units_prior_period"] == current_units
                nxt_prior = cal.bucket(cal.same_day_last_year(nxt.start), grain).start
                if nxt_prior == current.start:
                    assert nx["dsi_sellout.units_prior_year"] == current_units
                else:
                    assert nx["dsi_sellout.units_prior_year"] is None
                assert nx["dsi_sellout.units_running_total"] == current_units + 3
                assert nx["dsi_sellout.units_share"] == pytest.approx(3 / (current_units + 3))
                assert nx["dsi_sellout.units_per_week"] == pytest.approx(3 * 7 / nxt.days)
                assert cur["dsi_sellout.units_share"] + nx["dsi_sellout.units_share"] == pytest.approx(1)
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_sunday_week_keeps_the_partial_first_bucket_and_its_previous_week():
    db = await _db()
    try:
        cal = BusinessCalendar({"week_start_day": 6})
        week = next(b for b in cal.buckets(date(2026, 3, 1), date(2026, 3, 31), "week") if b.start <= date(2026, 3, 4) <= b.end)
        prev = cal.bucket(week.start - timedelta(days=1), "week")
        product = DimProduct(sku=_key("sku")[-32:], name=f"E10s {TAG}", tenant_id=TENANT)
        customer = DimCustomer(code=_key("cust")[-32:], name=f"Custs {TAG}", tenant_id=TENANT)
        db.add_all([product, customer])
        await db.flush()
        for day, units in ((week.start, 9), (week.start + timedelta(days=3), 4), (prev.start, 11)):
            db.add(FactSalesSellout(
                source_key=_key("so"), tenant_id=TENANT, product_id=product.id, customer_id=customer.id,
                period_start=day, transaction_date=day, units=units, revenue=0,
            ))
        await db.flush()
        opened = week.start + timedelta(days=3)
        rows, compiled = await _run(
            db, ["dsi_sellout.units", "dsi_sellout.units_prior_period"], ["period"], "week", cal,
            tenant=TENANT, period_from=opened, period_to=week.end, filters={"customer": customer.id},
        )
        assert len(rows) == 1
        bs = rows[0]["bucket_start"]
        assert (bs if isinstance(bs, date) else bs.date()) == week.start
        vals = {mid: _num(rows[0][lab]) for mid, lab in compiled.measure_labels.items()}
        assert vals["dsi_sellout.units"] == 4
        assert vals["dsi_sellout.units_prior_period"] == 11
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_ratio_follows_each_calendar_bucket():
    db = await _db()
    try:
        product = DimProduct(sku=_key("sku")[-32:], name=f"E10r {TAG}", tenant_id=TENANT)
        distributor = DimDistributor(code=_key("dist")[-32:], name=f"Dr {TAG}", tenant_id=TENANT)
        db.add_all([product, distributor])
        await db.flush()
        for cal in CALENDARS:
            customer = DimCustomer(code=_key("cust")[-32:], name=f"Cr {TAG}", tenant_id=TENANT)
            db.add(customer)
            await db.flush()
            bucket = next(b for b in cal.buckets(date(2026, 1, 1), date(2026, 12, 31), "month"))
            case = CporCase(
                case_code=_key("case")[-60:], tenant_id=TENANT, customer_id=customer.id, promotion_type="Price drop",
                window_start=bucket.start, window_end=bucket.end, status="approved", intelligence_exclude=False,
            )
            db.add(case)
            await db.flush()
            db.add(CporCaseLine(
                case_id=case.id, product_id=product.id, distributor_id=distributor.id,
                window_start=bucket.start, window_end=bucket.end, srp=100, vat_rate=15, dealer_margin_pct=10,
                estimate_qty=10, result_qty=4, support_usd=1, ttl_support=180,
            ))
            await db.flush()
            rows, compiled = await _run(
                db, ["cpor.delivery_rate", "cpor.result_units", "cpor.estimate_units"], ["period"], "month", cal,
                tenant=TENANT, period_from=bucket.start, period_to=bucket.end, filters={"customer": customer.id},
            )
            assert len(rows) == 1, cal.config
            bs = rows[0]["bucket_start"]
            assert (bs if isinstance(bs, date) else bs.date()) == bucket.start
            vals = {mid: _num(rows[0][lab]) for mid, lab in compiled.measure_labels.items()}
            assert vals["cpor.estimate_units"] == 10
            assert vals["cpor.result_units"] == 4
            assert vals["cpor.delivery_rate"] == pytest.approx(0.4)
    finally:
        await db.rollback()
        await db.close()


def _ship(**kw):
    base = dict(
        tenant_id=TENANT,
        source_key=_key("ship"),
        report_type="e10",
        raw_source_row={},
        product_resolution_status="resolved",
        distributor_resolution_status="unresolved",
        operating_unit="ZA",
    )
    base.update(kw)
    return FactInboundShipment(**base)


@pytest.mark.anyio
async def test_shipments_apply_the_twin_rule_and_resolved_customer():
    db = await _db()
    try:
        product = DimProduct(sku=_key("sku")[-32:], name=f"E10ship {TAG}", tenant_id=TENANT)
        customer_a = DimCustomer(code=_key("a")[-32:], name=f"A {TAG}", tenant_id=TENANT)
        customer_b = DimCustomer(code=_key("b")[-32:], name=f"B {TAG}", tenant_id=TENANT)
        db.add_all([product, customer_a, customer_b])
        await db.flush()
        confirmed = date(2026, 3, 2)
        db.add_all([
            _ship(product_id=product.id, line_state="shipped", quantity=Decimal("10"), order_no="O1", item_code="I1",
                  ship_confirm_date=confirmed, customer_id=None, resolved_customer_id=customer_a.id),
            _ship(product_id=product.id, line_state="open_order", quantity=Decimal("10"), order_no="O1", item_code="I1",
                  customer_id=customer_b.id, resolved_customer_id=customer_a.id),
            _ship(product_id=product.id, line_state="shipped", quantity=Decimal("10"), order_no="O2", item_code="I2",
                  ship_confirm_date=confirmed, resolved_customer_id=customer_a.id),
            _ship(product_id=product.id, line_state="open_order", quantity=Decimal("25"), order_no="O2", item_code="I2",
                  resolved_customer_id=customer_a.id),
            _ship(product_id=product.id, line_state="open_order", quantity=Decimal("7"), order_no=None, item_code=None,
                  resolved_customer_id=customer_a.id),
            _ship(product_id=product.id, line_state="shipped", quantity=Decimal("4"), order_no="O3", item_code="I3",
                  ship_confirm_date=confirmed, customer_id=customer_a.id, resolved_customer_id=customer_b.id),
        ])
        await db.flush()
        clear_model_cache()
        dm = default_model()
        req = V2Request(measures=["shipments.quantity", "shipments.lines"], breakdowns=["customer"])
        plan = plan_request(dm, req, v1_catalog=load_catalog())
        assert plan.ok, plan.refusals
        compiled = compile_plan(dm, plan, tenant_id=TENANT, calendar=BusinessCalendar())
        rows = (await db.execute(compiled.rows)).mappings().all()
        qty = compiled.measure_labels["shipments.quantity"]
        lines = compiled.measure_labels["shipments.lines"]
        by_customer = {row["customer_id"]: (float(row[qty]), float(row[lines])) for row in rows}
        # A: shipped 10 + shipped 10 + remainder 15 + unpaired open 7. The covered open 10 is out.
        assert by_customer[customer_a.id] == (42.0, 4.0)
        assert by_customer[customer_b.id] == (4.0, 1.0)
        assert None not in by_customer
    finally:
        await db.rollback()
        await db.close()
