"""N-0115 compiler on a real database (cip_test only; one rolled-back transaction per test).

- parity: compiler == volume_series (the v1 handler) for sellout_units and cst_sellthrough_units at
  every v1 grain x week / month / quarter x (no filter, one customer filter), including ISO week 53;
- tenant isolation: two tenants, zero leakage, on the tenant_id path and the tenant_via dim_product
  path; dimension rows of another tenant never label a row;
- LEFT JOIN 'Unassigned' bucket keeps totals; totals from SQL despite the row limit;
- calculated null rules (prior / pct_change / difference / ratio / per-week);
- CST stored-period refusal with the v1 text; reported stock = sell-through overview's rule;
- CPOR measures follow the portfolio service's own rules;
- product-line scope and the 10 s statement timeout are bound inside the compiled transaction.
"""

from __future__ import annotations

import secrets
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactReturns, FactSalesSellout
from app.query.cache import clear_query_cache
from app.query.handlers.volume_series import handle_volume
from app.query.model.execute import run_v2
from app.query.model.graph import V2Request
from app.query.model.loader import MODEL_PATH, load_model
from app.query.types import QueryRequest

TAG = secrets.token_hex(3)
TA = f"n0115-a-{TAG}"
TB = f"n0115-b-{TAG}"
LINE = f"NB{TAG}"
_seq = 0


def _key(prefix: str) -> str:
    global _seq
    _seq += 1
    return f"n0115-{TAG}-{prefix}-{_seq}"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_query_cache()
    yield
    clear_query_cache()


async def _session_or_skip():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        pytest.skip("cip_test only")
    return db


class Seed:
    pass


async def _seed(db) -> Seed:
    s = Seed()
    region = DimRegion(code=_key("rg")[-32:], name=f"Region {TAG}")
    db.add(region)
    await db.flush()
    s.region = region.id

    def prod(tenant, line, tag):
        return DimProduct(sku=_key(f"p{tag}"), name=f"N0115 {tag}", sales_model_name=f"M-{tag}-{TAG}", product_line=line, tenant_id=tenant)

    s.pA1, s.pA2, s.pB1 = prod(TA, LINE, "a1"), prod(TA, None, "a2"), prod(TB, LINE, "b1")
    s.cA1 = DimCustomer(code=_key("ca1"), name=f"Dealer A1 {TAG}", tenant_id=TA, region_id=region.id)
    s.cA2 = DimCustomer(code=_key("ca2"), name=f"Dealer A2 {TAG}", tenant_id=TA)
    s.cB1 = DimCustomer(code=_key("cb1"), name=f"Dealer B1 {TAG}", tenant_id=TB, region_id=region.id)
    s.dA = DimDistributor(code=_key("d")[-32:], name=f"Disti A {TAG}", tenant_id=TA)
    s.dB = DimDistributor(code=_key("d")[-32:], name=f"Disti B {TAG}", tenant_id=TB)
    db.add_all([s.pA1, s.pA2, s.pB1, s.cA1, s.cA2, s.cB1, s.dA, s.dB])
    await db.flush()

    def dsi(tenant, p, c, d, day, units):
        db.add(
            FactSalesSellout(
                source_key=_key("dsi"), tenant_id=tenant, product_id=p.id, customer_id=c.id,
                distributor_id=d.id if d else None, period_start=day, transaction_date=day,
                units=units, revenue=0,
            )
        )

    # Tenant A: several weeks, a quarter boundary, ISO week 53 (2026-12-28 .. 2027-01-03), no-distributor rows.
    for day, p, c, d, u in [
        (date(2026, 3, 2), s.pA1, s.cA1, s.dA, 10),
        (date(2026, 3, 4), s.pA2, s.cA1, s.dA, 5),
        (date(2026, 3, 16), s.pA1, s.cA2, None, 7),  # no distributor: out only when distributor is a breakdown
        (date(2026, 3, 23), s.pA1, s.cA1, s.dA, 0),  # a zero week
        (date(2026, 3, 31), s.pA2, s.cA2, s.dA, 3),
        (date(2026, 3, 30), s.pA1, s.cA1, s.dA, 4),
        (date(2026, 4, 1), s.pA1, s.cA1, s.dA, 6),
        (date(2026, 12, 31), s.pA1, s.cA1, s.dA, 2),
        (date(2027, 1, 2), s.pA2, s.cA2, None, 9),
    ]:
        dsi(TA, p, c, d, day, u)
    # Tenant B: big numbers that would show if they leaked.
    for day in (date(2026, 3, 2), date(2026, 3, 31), date(2026, 12, 31)):
        dsi(TB, s.pB1, s.cB1, s.dB, day, 1000)

    def cst(tenant, p, c, start, units, *, site=None, soh=None, ptype="weekly"):
        db.add(
            FactCustomerSellthrough(
                source_key=_key("cst"), tenant_id=tenant, customer_id=c.id, product_id=p.id,
                period_start_date=start, period_type=ptype, period_grain="month" if ptype == "monthly" else "week",
                units_sold=units, site_label=site, reported_soh=soh,
            )
        )

    for start, p, site, u, soh in [
        (date(2026, 3, 2), s.pA1, "S1", 4, None),
        (date(2026, 3, 2), s.pA1, "S2", 6, None),
        (date(2026, 3, 9), s.pA2, None, 3, None),
        (date(2026, 3, 30), s.pA1, "S1", 8, 20),
        (date(2026, 3, 30), s.pA2, "S2", 1, 5),
        (date(2026, 4, 6), s.pA1, "S1", 2, None),
        (date(2026, 12, 28), s.pA1, "S1", 5, None),
    ]:
        cst(TA, p, s.cA1, start, u, site=site, soh=soh)
    cst(TA, s.pA1, s.cA2, date(2026, 3, 1), 30, ptype="monthly", soh=12)
    cst(TB, s.pB1, s.cB1, date(2026, 3, 2), 1000, site="S1", soh=1000)
    await db.flush()
    return s


async def _v1(db, metric, grains, *, grain=None, filters=None, tenant=TA):
    req = QueryRequest(
        metric=metric, grains=list(grains), filters=dict(filters or {}), tenant_id=tenant,
        period_grain=grain if "period" in grains else None,
    )
    return await handle_volume(db, req, metric_key=metric)


async def _v2(db, measures, breakdowns=(), *, tenant=TA, dm=None, **kw):
    return await run_v2(
        db, V2Request(measures=list(measures), breakdowns=list(breakdowns), **kw), tenant_id=tenant, skip_cache=True, dm=dm
    )


def _row_key(row: dict, grains) -> tuple:
    out = []
    for g in sorted(grains):
        if g == "period":
            out.append(row.get("bucket_key"))
        elif g == "site_label":
            v = row.get("site_label")
            out.append("Unassigned" if v is None else v)
        else:
            out.append(row.get(f"{g}_id"))
    return tuple(out)


SELLOUT_GRAINS = [
    ["distributor", "product"], ["period"], ["period", "product"], ["period", "distributor"],
    ["period", "distributor", "product"], ["customer"], ["period", "customer"], ["product"], [],
]
CST_GRAINS = [
    ["customer"], ["product"], ["customer", "product"], ["customer", "product", "site_label"],
    ["period"], ["period", "customer"], ["period", "product"], [],
]


@pytest.mark.anyio
async def test_compiler_matches_volume_series_at_every_grain():
    db = await _session_or_skip()
    try:
        s = await _seed(db)
        checked = 0
        for metric, mid, grain_sets in (
            ("sellout_units", "dsi_sellout.units", SELLOUT_GRAINS),
            ("cst_sellthrough_units", "cst_sellthrough.units", CST_GRAINS),
        ):
            for grains in grain_sets:
                for pg in (("week", "month", "quarter") if "period" in grains else (None,)):
                    for cust in (None, s.cA1.id):
                        v1_filters = {"customer_id": cust} if cust else {}
                        v2_filters = {"customer": cust} if cust else {}
                        if metric == "cst_sellthrough_units" and pg == "week" and not cust:
                            continue  # tenant A holds a monthly CST customer: week is refused (tested below)
                        old = await _v1(db, metric, grains, grain=pg, filters=v1_filters)
                        new = await _v2(db, [mid], grains, period_grain=pg, filters=v2_filters, limit=5000)
                        assert old.status == "ok", (metric, grains, pg, old.message)
                        assert new["ok"], (metric, grains, pg, new["refusals"])
                        assert round(new["totals"][mid], 6) == round(old.value, 6), (metric, grains, pg, cust)
                        o = {_row_key(r, grains): round(r["value"], 6) for r in old.rows or []}
                        n = {_row_key(r, grains): round(r[mid], 6) for r in new["rows"]}
                        assert n == o, (metric, grains, pg, cust)
                        checked += 1
        assert checked > 60
        # ISO week 53 is one bucket across the year end, keyed like v1.
        w = await _v2(db, ["dsi_sellout.units"], ["period"], period_grain="week")
        w53 = [r for r in w["rows"] if r["bucket_key"] == "2026-W53"]
        assert len(w53) == 1 and w53[0]["dsi_sellout.units"] == 11.0 and w53[0]["bucket_start"] == "2026-12-28"
        q = await _v2(db, ["dsi_sellout.units"], ["period"], period_grain="quarter")
        assert [r["bucket_key"] for r in q["rows"]] == ["2026-Q1", "2026-Q2", "2026-Q4", "2027-Q1"]
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_two_tenants_zero_leakage():
    db = await _session_or_skip()
    try:
        s = await _seed(db)
        a = await _v2(db, ["dsi_sellout.units", "dsi_sellout.lines"], ["customer", "product"])
        b = await _v2(db, ["dsi_sellout.units"], ["customer", "product"], tenant=TB)
        assert a["totals"]["dsi_sellout.units"] == 46.0 and a["totals"]["dsi_sellout.lines"] == 9
        assert b["totals"]["dsi_sellout.units"] == 3000.0
        assert {r["customer_id"] for r in a["rows"]} == {s.cA1.id, s.cA2.id}
        assert {r["customer_id"] for r in b["rows"]} == {s.cB1.id}
        # Filtering tenant A on tenant B's ids finds nothing.
        x = await _v2(db, ["dsi_sellout.units"], ["customer"], filters={"customer": s.cB1.id})
        assert x["rows"] == [] and x["totals"]["dsi_sellout.units"] == 0.0
        # Region via the customer dimension: tenant B's customer shares the region but never shows in A.
        r = await _v2(db, ["dsi_sellout.units"], ["region"])
        assert sum(row["dsi_sellout.units"] for row in r["rows"]) == 46.0
        c = await _v2(db, ["cst_sellthrough.units"], ["site_label"])
        assert c["totals"]["cst_sellthrough.units"] == 59.0
        cb = await _v2(db, ["cst_sellthrough.units"], ["site_label"], tenant=TB)
        assert cb["totals"]["cst_sellthrough.units"] == 1000.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_tenant_via_dim_product_path(tmp_path: Path):
    db = await _session_or_skip()
    try:
        s = await _seed(db)
        data = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))
        data["models"]["returns_test"] = {
            "label": "Returns (test)",
            "table": "fact_returns",
            "tenant_via": "dim_product",
            "time": {"column": "transaction_date", "floor": "day"},
            "joins": {"product": {"fk": "product_id"}, "distributor": {"fk": "distributor_id"}},
            "measures": {"units": {"label": "Return units", "unit": "units", "agg": "sum", "column": "return_quantity"}},
        }
        p = tmp_path / "model.yaml"
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        dm = load_model(p)
        for prod, dist, qty in ((s.pA1, s.dA, 4), (s.pA2, s.dA, 1), (s.pB1, s.dB, 500)):
            db.add(
                FactReturns(
                    source_key=_key("ret"), distributor_id=dist.id, product_id=prod.id, customer_id=s.cA1.id,
                    transaction_date=date(2026, 3, 3), return_quantity=qty,
                )
            )
        await db.flush()
        a = await _v2(db, ["returns_test.units"], ["product"], dm=dm, filters={"distributor": [s.dA.id, s.dB.id]})
        b = await _v2(db, ["returns_test.units"], ["product"], dm=dm, tenant=TB, filters={"distributor": [s.dA.id, s.dB.id]})
        assert a["totals"]["returns_test.units"] == 5.0
        assert {r["product_id"] for r in a["rows"]} == {s.pA1.id, s.pA2.id}
        assert b["totals"]["returns_test.units"] == 500.0
        assert "t_product" in a["explain"]["sql"]
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_unassigned_bucket_keeps_totals_and_names_sit_beside_ids():
    db = await _session_or_skip()
    try:
        s = await _seed(db)
        bu = await _v2(db, ["dsi_sellout.units"], ["bu"])
        by = {r["bu"]: r["dsi_sellout.units"] for r in bu["rows"]}
        assert by == {LINE: 29.0, "Unassigned": 17.0}
        assert sum(by.values()) == bu["totals"]["dsi_sellout.units"] == 46.0
        reg = await _v2(db, ["dsi_sellout.units"], ["region"])
        names = {r["region_name"]: r["dsi_sellout.units"] for r in reg["rows"]}
        assert names == {f"Region {TAG}": 27.0, "Unassigned": 19.0}
        cust = await _v2(db, ["dsi_sellout.units"], ["customer"])
        assert {r["customer_name"] for r in cust["rows"]} == {f"Dealer A1 {TAG}", f"Dealer A2 {TAG}"}
        prod = await _v2(db, ["dsi_sellout.units"], ["product"])
        assert {r["product_name"] for r in prod["rows"]} == {f"M-a1-{TAG}", f"M-a2-{TAG}"}
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_limit_truncates_rows_but_totals_come_from_sql():
    db = await _session_or_skip()
    try:
        await _seed(db)
        r = await _v2(db, ["dsi_sellout.units"], ["customer"], limit=1)
        assert len(r["rows"]) == 1 and r["truncated"] is True
        assert r["totals"]["dsi_sellout.units"] == 46.0
        assert r["explain"]["row_count"] == 2
        top = r["rows"][0]["dsi_sellout.units"]
        assert top == 27.0  # default sort: first measure, largest first
        asc = await _v2(db, ["dsi_sellout.units"], ["customer"], sort_by="dsi_sellout.units", sort_dir="asc", limit=1)
        assert asc["rows"][0]["dsi_sellout.units"] == 19.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_calculated_measures_null_rules():
    db = await _session_or_skip()
    try:
        await _seed(db)
        calc = ["dsi_sellout.units", "dsi_sellout.units_prior_period", "dsi_sellout.units_change", "dsi_sellout.units_pct_change"]
        r = await _v2(db, calc, ["period"], period_grain="week", period_from="2026-03-02", period_to="2026-04-05")
        rows = {x["bucket_key"]: x for x in r["rows"]}
        # W10 (2026-03-02): previous week has no rows -> prior null, change null, pct null (never an invented 0).
        w10 = rows["2026-W10"]
        assert w10["dsi_sellout.units"] == 15.0 and w10["dsi_sellout.units_prior_period"] is None
        assert w10["dsi_sellout.units_change"] is None and w10["dsi_sellout.units_pct_change"] is None
        # W12 (2026-03-16) follows a week with no rows (W11): prior null.
        assert rows["2026-W12"]["dsi_sellout.units_prior_period"] is None
        # W13 (2026-03-23) sold 0 after W12's 7: change -7, pct -1.
        assert rows["2026-W13"]["dsi_sellout.units_prior_period"] == 7.0
        assert rows["2026-W13"]["dsi_sellout.units_change"] == -7.0
        assert rows["2026-W13"]["dsi_sellout.units_pct_change"] == -1.0
        # W14 (2026-03-30) follows W13's 0: pct null (previous is 0), change = 13.
        assert rows["2026-W14"]["dsi_sellout.units"] == 13.0
        assert rows["2026-W14"]["dsi_sellout.units_pct_change"] is None
        assert rows["2026-W14"]["dsi_sellout.units_change"] == 13.0
        assert "2026-W09" not in rows  # the widened bucket is read, never shown
        assert r["totals"]["dsi_sellout.units_pct_change"] is None and r["totals"]["dsi_sellout.units"] == 35.0
        # Per week: March in month buckets = 29 units / (31 / 7) weeks.
        pw = await _v2(
            db, ["dsi_sellout.units_per_week"], ["period"], period_grain="month", period_from="2026-03-01", period_to="2026-03-31"
        )
        assert pw["rows"][0]["dsi_sellout.units_per_week"] == pytest.approx(29 / (31 / 7))
        assert pw["totals"]["dsi_sellout.units_per_week"] == pytest.approx(29 / (31 / 7))
        # A partial bucket counts only its days in the window: 2026-04-01 only -> 6 units / (1/7).
        pw2 = await _v2(
            db, ["dsi_sellout.units_per_week"], ["period"], period_grain="month", period_from="2026-03-01", period_to="2026-04-01"
        )
        apr = [x for x in pw2["rows"] if x["bucket_key"] == "2026-04"][0]
        assert apr["dsi_sellout.units_per_week"] == pytest.approx(6 / (1 / 7))
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_cst_never_finer_than_stored_with_the_v1_text():
    db = await _session_or_skip()
    try:
        await _seed(db)
        old = await _v1(db, "cst_sellthrough_units", ["period"], grain="week")
        new = await _v2(db, ["cst_sellthrough.units"], ["period"], period_grain="week")
        assert old.status == "refused" and not new["ok"]
        assert new["refusals"][0]["reason"] == old.message
        assert new["refusals"][0]["wall"] == "W-ONE-STORED-PERIOD"
        ok = await _v2(db, ["cst_sellthrough.units"], ["period"], period_grain="month")
        assert ok["ok"] and ok["totals"]["cst_sellthrough.units"] == 59.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_reported_stock_follows_the_sell_through_overview_rule():
    from app.services.channel_intelligence.sell_through_overview import OverviewFilters, load_stock_positions

    db = await _session_or_skip()
    try:
        s = await _seed(db)
        f = OverviewFilters(date_from=date(2026, 3, 1), date_to=date(2026, 4, 30), tenant_id=TA)
        positions, _dates = await db.run_sync(lambda sync: load_stock_positions(sync, f, f.date_to))
        by_customer: dict[int, float] = {}
        for (cid, _pid), v in positions.items():
            by_customer[cid] = by_customer.get(cid, 0.0) + v["soh"]
        r = await _v2(
            db, ["cst_sellthrough.reported_soh", "cst_sellthrough.units_per_week"], ["customer"],
            period_from="2026-03-01", period_to="2026-04-30",
        )
        got = {row["customer_id"]: row["cst_sellthrough.reported_soh"] for row in r["rows"]}
        assert got == by_customer == {s.cA1.id: 25.0, s.cA2.id: 12.0}
        assert r["totals"]["cst_sellthrough.reported_soh"] == 37.0
        # A site filter narrows the latest report date, as the overview's does.
        f2 = OverviewFilters(date_from=date(2026, 3, 1), date_to=date(2026, 4, 30), tenant_id=TA, sites=["S2"])
        positions2, _ = await db.run_sync(lambda sync: load_stock_positions(sync, f2, f2.date_to))
        r2 = await _v2(db, ["cst_sellthrough.reported_soh"], ["customer"], period_to="2026-04-30", filters={"site_label": ["S2"]})
        assert {row["customer_id"]: row["cst_sellthrough.reported_soh"] for row in r2["rows"]} == {
            cid: v["soh"] for (cid, _), v in positions2.items()
        }
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_cpor_measures_follow_the_portfolio_service():
    from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence

    db = await _session_or_skip()
    try:
        s = await _seed(db)

        def case(code, **kw):
            c = CporCase(
                case_code=_key(code)[-60:], tenant_id=TA, customer_id=s.cA1.id, promotion_type="Price drop",
                window_start=date(2026, 3, 2), window_end=date(2026, 3, 29), **kw,
            )
            db.add(c)
            return c

        live, superseded, excluded = case("live", status="approved"), case("sup"), case("exc", intelligence_exclude=True)
        await db.flush()
        superseded.superseded_by_case_id = live.id

        def line(c, prod, est, res, usd, *, remark=None, ttl_usd=None, ws=date(2026, 3, 2)):
            db.add(
                CporCaseLine(
                    case_id=c.id, product_id=prod.id, distributor_id=s.dA.id, window_start=ws, window_end=ws + timedelta(days=27),
                    srp=100, vat_rate=15, dealer_margin_pct=10, estimate_qty=est, result_qty=res, support_usd=usd,
                    ttl_support_usd=ttl_usd, ttl_support=(usd or 0) * est * 18, remark=remark,
                )
            )

        line(live, s.pA1, 10, 8, 2.5)
        line(live, s.pA2, 4, 0, 1.0, ttl_usd=7, ws=date(2026, 3, 9))
        line(live, s.pA1, 5, 5, 3.0, remark="[voided] by steward", ws=date(2026, 3, 16))
        line(live, s.pA2, 0, 0, 3.0, ws=date(2026, 3, 23))
        line(superseded, s.pA1, 99, 99, 9.0)
        line(excluded, s.pA1, 77, 77, 9.0)
        await db.flush()

        portfolio = await db.run_sync(build_portfolio_intelligence)
        mine = next(c for c in portfolio["by_customer"] if c["customer_id"] == s.cA1.id)
        r = await _v2(
            db, ["cpor.support_usd", "cpor.support_zar", "cpor.estimate_units", "cpor.result_units", "cpor.delivery_rate",
                 "cpor.support_per_unit_usd", "cpor.cases", "cpor.lines"],
            ["customer"], filters={"customer": s.cA1.id},
        )
        row = r["rows"][0]
        assert row["cpor.support_usd"] == pytest.approx(mine["support_usd"]) == pytest.approx(25 + 7)
        assert row["cpor.support_zar"] == pytest.approx(mine["support_zar"])
        assert row["cpor.estimate_units"] == mine["estimate_qty"] == 14.0
        assert row["cpor.result_units"] == mine["result_qty"] == 8.0
        assert row["cpor.delivery_rate"] == pytest.approx(mine["delivery_rate"])
        assert row["cpor.support_per_unit_usd"] == pytest.approx(mine["support_per_unit_sold_usd"])
        assert row["cpor.cases"] == 1.0 and row["cpor.lines"] == 2.0
        # Ratio null when the denominator is 0: product a2 sold nothing.
        byp = await _v2(db, ["cpor.support_per_unit_usd"], ["product"], filters={"customer": s.cA1.id})
        vals = {x["product_id"]: x["cpor.support_per_unit_usd"] for x in byp["rows"]}
        assert vals[s.pA2.id] is None and vals[s.pA1.id] == pytest.approx(25 / 8)
        st = await _v2(db, ["cpor.cases"], ["status", "workflow_status"], filters={"customer": s.cA1.id})
        assert [(x["status"], x["workflow_status"]) for x in st["rows"]] == [("approved", "draft")]
        # Tenant B sees none of tenant A's cases.
        none = await _v2(db, ["cpor.support_usd"], ["customer"], tenant=TB)
        assert none["rows"] == [] and none["totals"]["cpor.support_usd"] == 0.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_scope_and_timeout_are_bound_inside_the_compiled_transaction():
    from app.core.product_line_scope import request_editable_product_lines, request_product_lines, request_role

    probe = await _session_or_skip()
    await probe.close()
    t1 = request_product_lines.set(frozenset({LINE}))
    t2 = request_editable_product_lines.set(frozenset())
    t3 = request_role.set("viewer")
    try:
        async with AsyncSessionLocal() as db:
            r = await _v2(db, ["dsi_sellout.units"], ["customer"])
            assert r["ok"]
            assert r["explain"]["scope"] == {"product_lines": LINE, "role": "viewer", "source": "this transaction"}
            # Same transaction: the product-line setting and the 10 s timeout are still in force.
            assert (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar_one() == LINE
            assert (await db.execute(text("show statement_timeout"))).scalar_one() == "10s"
            await db.rollback()
            # A new transaction binds the scope again (after_begin listener); the timeout was LOCAL.
            assert (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar_one() == LINE
            assert (await db.execute(text("show statement_timeout"))).scalar_one() != "10s"
            await db.rollback()
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)
        request_role.reset(t3)
