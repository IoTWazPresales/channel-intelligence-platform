"""GOV-008 review 2026-11-02 (N-0115 query model). Value-level probes on cip_test.

Every section seeds fictional rows in its own session and rolls back. Nothing is committed.
The script refuses to run unless current_database() is cip_test.
Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/query/p2_cip_test_values.py
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
import traceback
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"

from sqlalchemy import text  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.cpor import CporCase, CporCaseLine  # noqa: E402
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct  # noqa: E402
from app.models.facts import (  # noqa: E402
    FactInboundShipment, FactInventoryDistributor, FactReturns, FactSalesSellout,
)
from app.query.cache import clear_query_cache  # noqa: E402
from app.query.model.calc import total_for, window_weeks  # noqa: E402
from app.query.model.compiler import compile_plan  # noqa: E402
from app.query.model.execute import run_v2  # noqa: E402
from app.query.model.graph import V2Request, plan_request  # noqa: E402
from app.query.model.loader import clear_model_cache, default_model  # noqa: E402
from app.semantics.registry import load_catalog  # noqa: E402
from app.services.business_calendar import BusinessCalendar  # noqa: E402

OUT = Path(__file__).with_name("p2_output.txt")
LINES: list[str] = []
TAG = secrets.token_hex(4)
TA, TB = f"rv-a-{TAG}", f"rv-b-{TAG}"
_n = 0


def out(s: str) -> None:
    LINES.append(s)
    print(s, flush=True)


def check(name: str, got, want) -> None:
    ok = got == want
    out(f"{'PASS' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")


def key(p: str) -> str:
    global _n
    _n += 1
    return f"rv{TAG}{p}{_n}"[-30:]


def f(v):
    return None if v is None else float(v)


async def session():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        raise SystemExit(f"refusing: database is {name}")
    for t in (TA, TB):
        await db.execute(text("INSERT INTO tenant (id, name) VALUES (:i, :n) ON CONFLICT DO NOTHING"), {"i": t, "n": "review fictional"})
    return db


def plan_of(measures, breakdowns=(), grain=None, frm=None, to=None, filters=None, catalog=None):
    dm = default_model()
    req = V2Request(measures=list(measures), breakdowns=list(breakdowns), period_grain=grain,
                    period_from=frm, period_to=to, filters=dict(filters or {}))
    return dm, plan_request(dm, req, v1_catalog=catalog or load_catalog())


async def run_model(db, measures, breakdowns=(), grain=None, frm=None, to=None, filters=None, tenant=TA, cal=None):
    dm, plan = plan_of(measures, breakdowns, grain, frm, to, filters)
    if not plan.measures:
        return None, [r.reason for r in plan.refusals], None
    c = compile_plan(dm, plan, tenant_id=tenant, calendar=cal)
    rows = (await db.execute(c.rows)).mappings().all()
    trow = (await db.execute(c.totals)).one()._mapping
    base = {mid: trow[lab] for mid, lab in c.total_labels.items()}
    weeks = c.weeks_in_window or window_weeks(
        period_from=plan.period_from, period_to=plan.period_to,
        grain=plan.period_grain if "period" in plan.breakdowns else None,
        vintage_min=trow.get("vintage_min"), vintage_max=trow.get("vintage_max"))
    totals = {m.id: f(total_for(dm, m, base, weeks=weeks)) for m in plan.measures}
    outrows = []
    for r in rows:
        d = {k: r[k] for k in r.keys() if not k.startswith("out")}
        for mid, lab in c.measure_labels.items():
            d[mid] = f(r[lab])
        outrows.append(d)
    return outrows, totals, c


# ----------------------------------------------------------------------------- E1 CPOR


async def e1() -> None:
    out("== E1 governed CPOR (real handler via run_v2, cip_test seeded, no ContextVar tenant set)")
    db = await session()
    try:
        ca = [DimCustomer(tenant_id=TA, code=key("ca"), name=f"RV A{i}") for i in range(2)]
        cb = DimCustomer(tenant_id=TB, code=key("cb"), name="RV B0")
        pa = [DimProduct(tenant_id=TA, sku=key("pa"), name=f"RV PA{i}", product_line=bu) for i, bu in enumerate(("NB", "NR"))]
        pb = DimProduct(tenant_id=TB, sku=key("pb"), name="RV PB", product_line="NB")
        db.add_all(ca + [cb] + pa + [pb])
        await db.flush()

        def case(t, cust, promo):
            return CporCase(tenant_id=t, case_code=key("case"), customer_id=cust.id, promotion_type=promo,
                            window_start=date(2026, 2, 1), window_end=date(2026, 2, 28), intelligence_exclude=False)
        c1, c2, c3 = case(TA, ca[0], "Price drop"), case(TA, ca[1], "Bundle"), case(TB, cb, "Price drop")
        db.add_all([c1, c2, c3])
        await db.flush()
        # (case, product, usd, est, result): A NB = 25+15=40 usd; A NR = 60; B NB = 900
        for cs, p, usd, est, res in [(c1, pa[0], 25, 10, 5), (c1, pa[1], 60, 20, 10), (c2, pa[0], 15, 10, 9), (c3, pb, 900, 50, 50)]:
            db.add(CporCaseLine(case_id=cs.id, product_id=p.id, window_start=cs.window_start, window_end=cs.window_end,
                                srp=100, vat_rate=15, dealer_margin_pct=10, estimate_qty=est, result_qty=res,
                                ttl_support_usd=usd, ttl_support=usd * 18))
        await db.flush()
        clear_query_cache()
        clear_model_cache()

        async def v2(measure, bds, filters):
            r = await run_v2(db, V2Request(measures=[measure], breakdowns=bds, filters=filters), tenant_id=TA, skip_cache=True)
            rows = [x.get(measure) for x in r["rows"]]
            return r["ok"], r["totals"].get(measure), rows, [x["reason"] for x in r["refusals"]]

        # Original counterexample 1: bu=NB by customer (was total 100, two customers)
        ok, tot, rows, ref = await v2("support_spend", ["customer"], {"bu": "NB"})
        check("E1.1 support_spend customer bu=NB total", tot, 40.0)
        check("E1.1 rows sum == total", sum(rows), tot)
        # Original counterexample 2: nonexistent customer (was rows [] total 100)
        ok, tot, rows, ref = await v2("support_spend", ["customer"], {"customer": 2_000_000_000})
        check("E1.2 nonexistent customer total/rows", (tot, rows), (0.0, []))
        # Cross-tenant filter values: tenant B's customer id and a BU that exists only in B with 900 USD
        ok, tot, rows, ref = await v2("support_spend", ["customer"], {"customer": cb.id})
        check("E1.3 tenant B customer id from tenant A", (tot, rows), (0.0, []))
        ok, tot, rows, ref = await v2("support_spend", ["bu"], {})
        check("E1.4 tenant A by bu (B's 900 must not appear)", (tot, sorted(rows)), (100.0, [40.0, 60.0]))
        # filter x grain matrix
        for bds in (["customer"], ["bu"], ["promo_type"]):
            for flt, want in (({}, 100.0), ({"bu": "NB"}, 40.0), ({"bu": "nr"}, 60.0), ({"customer": ca[0].id}, 85.0),
                              ({"customer": ca[1].id, "bu": "NB"}, 15.0), ({"customer": ca[1].id, "bu": "NR"}, 0.0)):
                ok, tot, rows, ref = await v2("support_spend", bds, flt)
                check(f"E1.5 support_spend {bds} {flt} total, rows-sum", (tot, sum(r or 0 for r in rows)), (want, want))
        for bds in (["customer"], ["bu"]):
            ok, tot, rows, ref = await v2("delivery_rate", bds, {"customer": ca[0].id})
            check(f"E1.6 delivery_rate {bds} customer A0 total", round(tot, 6), round(15 / 30, 6))
        ok, tot, rows, ref = await v2("support_spend", ["customer"], {"product": pa[0].id})
        check("E1.7 unsupported product filter refused", ok, False)
        out(f"      refusal: {ref}")
        ok, tot, rows, ref = await v2("support_spend", ["customer", "bu"], {})
        check("E1.8 cross-tab refused", ok, False)
        out(f"      refusal: {ref}")
        ok, tot, rows, ref = await v2("support_spend", ["customer"], {"bu": ["NB", "NR"]})
        check("E1.9 multi-value bu refused", ok, False)
    finally:
        await db.rollback()
        await db.close()


# ----------------------------------------------------------------------------- E6 overlay


async def e6() -> None:
    out("== E6 tenant overlay: counterpart refusals, spec keys executed on cip_test")
    base = load_catalog()
    hidden = replace(base, metrics=tuple(replace(m, hidden=True) if m.key == "sellout_units" else m for m in base.metrics),
                     tenant_id="rv", overlay_applied=True)
    clear_model_cache()
    dm = default_model()
    for mid in ["dsi_sellout.units", "dsi_sellout.units_avg", "dsi_sellout.units_min", "dsi_sellout.units_max",
                "dsi_sellout.units_prior_year", "dsi_sellout.units_running_total", "dsi_sellout.units_share",
                "dsi_sellout.units_per_week", "dsi_sellout.units_change", "dsi_sellout.priced_units",
                "dsi_sellout.lines", "dsi_sellout.dealers"]:
        _, plan = plan_of([mid], ["period"], "month", catalog=hidden)
        out(f"  hidden sellout_units -> {mid}: {'REFUSED' if not plan.measures else 'ALLOWED'}"
            + (f" ({plan.refusals[0].reason[:70]})" if plan.refusals else ""))
    # Narrowed to {product}
    narrow = replace(base, metrics=tuple(replace(m, allowed_grains=(frozenset({"product"}),)) if m.key == "sellout_units" else m
                                         for m in base.metrics), tenant_id="rv", overlay_applied=True)
    for mid, bds in [("dsi_sellout.units", ["customer"]), ("dsi_sellout.units_avg", ["customer"]),
                     ("dsi_sellout.priced_units", ["customer"]), ("dsi_sellout.units", ["product"])]:
        _, plan = plan_of([mid], bds, catalog=narrow)
        out(f"  narrowed sellout_units={{product}} -> {mid} by {bds}: {'REFUSED' if not plan.measures else 'ALLOWED'}")
    # Narrow with filter (filter on customer while grain is product)
    _, plan = plan_of(["dsi_sellout.units"], ["product"], filters={"customer": 1}, catalog=narrow)
    out(f"  narrowed {{product}} + customer filter: {'REFUSED' if not plan.measures else 'ALLOWED'} (filters are not grains)")
    # catalog shape for non-admin
    from app.query.model.catalog import catalog_v2
    listed = {m["id"] for m in catalog_v2(dm, hidden, is_admin=False)["measures"]}
    out(f"  non-admin catalog lists (hidden): units={('dsi_sellout.units' in listed)} avg={('dsi_sellout.units_avg' in listed)} "
        f"priced_units={('dsi_sellout.priced_units' in listed)} prior_year={('dsi_sellout.units_prior_year' in listed)}")
    # Spec keys: injection-shaped / unknown
    spec = replace(base, spec_keys=("gpu",))
    for bid in ["spec_gpu", "spec_cpu", "spec_gpu'--", "spec_gpu.vram", "spec_GPU", "spec_"]:
        _, plan = plan_of(["dsi_sellout.units"], [bid], catalog=spec)
        out(f"  spec breakdown {bid!r}: {'ALLOWED' if plan.measures else 'REFUSED'}"
            + (f" ({plan.refusals[0].reason[:80]})" if plan.refusals else ""))
    _, plan = plan_of(["dsi_sellout.units"], ["customer"], filters={"spec_cpu": "x"}, catalog=spec)
    out(f"  filter on unknown spec key: {'ALLOWED' if plan.measures else 'REFUSED'}")
    # Execute spec breakdown + same-key filter (bind-name collision?) with injection-shaped value
    db = await session()
    try:
        p1 = DimProduct(tenant_id=TA, sku=key("s1"), name="RV S1", specs_json={"gpu": "RTX 4060", "cpu": "i7"})
        p2 = DimProduct(tenant_id=TA, sku=key("s2"), name="RV S2", specs_json={"gpu": "'; drop table dim_product; --"})
        p3 = DimProduct(tenant_id=TA, sku=key("s3"), name="RV S3", specs_json={})
        pB = DimProduct(tenant_id=TB, sku=key("sb"), name="RV SB", specs_json={"gpu": "RTX 4060"})
        cu = DimCustomer(tenant_id=TA, code=key("sc"), name="RV SC")
        cuB = DimCustomer(tenant_id=TB, code=key("scb"), name="RV SCB")
        db.add_all([p1, p2, p3, pB, cu, cuB])
        await db.flush()
        for p, c, t, u in [(p1, cu, TA, 3), (p2, cu, TA, 5), (p3, cu, TA, 7), (pB, cuB, TB, 1000)]:
            db.add(FactSalesSellout(source_key=key("so"), tenant_id=t, product_id=p.id, customer_id=c.id,
                                    period_start=date(2026, 3, 2), transaction_date=date(2026, 3, 2), units=u, revenue=0))
        await db.flush()
        for flt in ({}, {"spec_gpu": "RTX 4060"}, {"spec_gpu": "'; drop table dim_product; --"}, {"spec_gpu": None}):
            dm2, plan = plan_of(["dsi_sellout.units"], ["spec_gpu"], filters=flt, catalog=spec)
            try:
                c = compile_plan(dm2, plan, tenant_id=TA)
                rows = (await db.execute(c.rows)).mappings().all()
                out(f"  exec spec_gpu filter={flt}: rows={[(r['spec_gpu'], f(r['out0'])) for r in rows]}")
            except Exception as exc:  # noqa: BLE001
                out(f"FAIL exec spec_gpu filter={flt}: {type(exc).__name__}: {str(exc)[:200]}")
                await db.rollback()
                return
        still = (await db.execute(text("select count(*) from dim_product where id=:i"), {"i": p2.id})).scalar_one()
        check("E6 injection-shaped spec value left dim_product intact", still, 1)
    finally:
        await db.rollback()
        await db.close()


# ----------------------------------------------------------------------------- E7 values


def ship(**kw):
    base = dict(tenant_id=TA, source_key=key("sh"), report_type="rv", raw_source_row={},
                product_resolution_status="resolved", distributor_resolution_status="unresolved", operating_unit="ZA")
    base.update(kw)
    return FactInboundShipment(**base)


async def e7() -> None:
    out("== E7 shipments closed states, on-hand latest, returns tenancy")
    db = await session()
    try:
        p = DimProduct(tenant_id=TA, sku=key("p"), name="RV P")
        p2 = DimProduct(tenant_id=TA, sku=key("p2"), name="RV P2")
        pB = DimProduct(tenant_id=TB, sku=key("pB"), name="RV PB")
        c = DimCustomer(tenant_id=TA, code=key("c"), name="RV C")
        cB = DimCustomer(tenant_id=TB, code=key("cB"), name="RV CB")
        d1 = DimDistributor(tenant_id=TA, code=key("d1"), name="RV D1")
        d2 = DimDistributor(tenant_id=TA, code=key("d2"), name="RV D2")
        dB = DimDistributor(tenant_id=TB, code=key("dB"), name="RV DB")
        db.add_all([p, p2, pB, c, cB, d1, d2, dB])
        await db.flush()
        sc = date(2026, 3, 2)
        new_ship = ship(product_id=p.id, line_state="shipped", quantity=Decimal(6), order_no="O4", item_code="I4",
                        ship_confirm_date=sc, resolved_customer_id=c.id)
        db.add(new_ship)
        await db.flush()
        db.add_all([
            # Shipped + its open twin partially covered (remainder 5)
            ship(product_id=p.id, line_state="shipped", quantity=Decimal(10), order_no="O1", item_code="I1",
                 ship_confirm_date=sc, customer_id=None, resolved_customer_id=c.id),
            ship(product_id=p.id, line_state="open_order", quantity=Decimal(15), order_no="O1", item_code="I1", resolved_customer_id=c.id),
            # An open order closed by a later report because it shipped; it carries a ship confirm date (29 such rows on cip)
            ship(product_id=p.id, line_state="shipped", quantity=Decimal(4), order_no="O3", item_code="I3",
                 ship_confirm_date=sc, resolved_customer_id=c.id),
            ship(product_id=p.id, line_state="closed_shipped", quantity=Decimal(4), order_no="O3", item_code="I3",
                 ship_confirm_date=sc, resolved_customer_id=c.id),
            # A PO-less shipped twin retired as closed_superseded by the newer row new_ship (47 such rows on cip)
            ship(product_id=p.id, line_state="closed_superseded", quantity=Decimal(6), order_no="O4", item_code="I4",
                 ship_confirm_date=sc, resolved_customer_id=c.id, superseded_by_fact_id=new_ship.id),
            ship(product_id=p.id, line_state="closed_disappeared", quantity=Decimal(9), order_no="O5", item_code="I5", resolved_customer_id=c.id),
            ship(product_id=p.id, line_state="closed_moved", quantity=Decimal(8), order_no="O6", item_code="I6", resolved_customer_id=c.id),
            # Tenant B shipped line
            ship(tenant_id=TB, product_id=pB.id, line_state="shipped", quantity=Decimal(500), order_no="OB", item_code="IB",
                 ship_confirm_date=sc, resolved_customer_id=cB.id),
        ])
        await db.flush()
        clear_model_cache()
        rows, tot, _ = await run_model(db, ["shipments.quantity", "shipments.lines"], ["customer"])
        out(f"  shipments by customer rows={[(r.get('customer_id'), r['shipments.quantity'], r['shipments.lines']) for r in rows]} totals={tot}")
        check("E7.1 shipped quantity counts state 'shipped' only (10+4+6)", tot["shipments.quantity"], 20.0)
        check("E7.1 shipped lines (3)", tot["shipments.lines"], 3.0)
        rows, tot, _ = await run_model(db, ["shipments.open_quantity", "shipments.open_lines"], ["customer"])
        check("E7.2 open quantity = remainder 5; closed states 0", (tot["shipments.open_quantity"], tot["shipments.open_lines"]), (5.0, 1.0))
        rows, tot, _ = await run_model(db, ["shipments.quantity", "shipments.open_quantity"], ["customer"])
        out(f"  mixed shipped+open: {tot}")

        # Distributor stock: latest per distributor, never summed across dates
        for dist, prod, d, q in [(d1, p, date(2026, 1, 10), 5), (d1, p, date(2026, 2, 10), 8), (d1, p2, date(2026, 1, 10), 3),
                                 (d2, p, date(2026, 2, 1), 2), (dB, pB, date(2026, 2, 1), 777)]:
            db.add(FactInventoryDistributor(source_key=key("inv"), tenant_id=TB if dist is dB else TA, product_id=prod.id,
                                            distributor_id=dist.id, as_of_date=d, on_hand_units=q))
        await db.flush()
        rows, tot, _ = await run_model(db, ["distributor_stock.on_hand"])
        check("E7.3 on-hand total = D1 latest (8) + D2 latest (2), not 18", tot["distributor_stock.on_hand"], 10.0)
        rows, tot, _ = await run_model(db, ["distributor_stock.on_hand"], ["distributor", "product"])
        out(f"  on-hand by distributor x product: {[(r['distributor_id'], r['product_id'], r['distributor_stock.on_hand']) for r in rows]}")
        rows, tot, _ = await run_model(db, ["distributor_stock.on_hand"], to="2026-01-31")
        check("E7.4 on-hand as of 2026-01-31 = 5 + 3", tot["distributor_stock.on_hand"], 8.0)
        rows, tot, _ = await run_model(db, ["distributor_stock.on_hand"], ["product"], filters={"product": p2.id})
        out(f"  on-hand filter product=P2 (only in D1's older report): rows={[(r['product_id'], r['distributor_stock.on_hand']) for r in rows]} total={tot}")
        _, refusal, _ = await run_model(db, ["distributor_stock.on_hand"], ["period"], "month")
        out(f"  on-hand by period: {refusal}")

        # Returns: tenant via product
        db.add_all([
            FactReturns(source_key=key("r"), distributor_id=d1.id, product_id=p.id, customer_id=c.id, transaction_date=sc, return_quantity=2),
            FactReturns(source_key=key("r"), distributor_id=dB.id, product_id=pB.id, customer_id=cB.id, transaction_date=sc, return_quantity=300),
        ])
        await db.flush()
        rows, tot, _ = await run_model(db, ["returns.units", "returns.lines"], ["customer"])
        check("E7.5 returns tenant A only", (tot["returns.units"], tot["returns.lines"]), (2.0, 1.0))
        rows, tot, _ = await run_model(db, ["returns.units"], ["customer"], filters={"customer": cB.id})
        check("E7.6 returns filtered by tenant-B customer id", tot["returns.units"], 0.0)
        # refused measures
        for mid in ["shipments.amount", "dsi_sellout.value_ex_vat", "cst_sellthrough.value", "cpor.open_cases", "listing_observation"]:
            _, refusal, _ = await run_model(db, [mid])
            out(f"  refused {mid}: {refusal}")
    finally:
        await db.rollback()
        await db.close()


# ----------------------------------------------------------------------------- E8 / E10 calendars


async def e8() -> None:
    out("== E8/E10 calendar values")
    db = await session()
    try:
        p = DimProduct(tenant_id=TA, sku=key("cp"), name="RV CP")
        db.add(p)
        await db.flush()

        async def cust():
            cu = DimCustomer(tenant_id=TA, code=key("cc"), name="RV CC")
            db.add(cu)
            await db.flush()
            return cu

        async def sell(cu, d, u):
            db.add(FactSalesSellout(source_key=key("so"), tenant_id=TA, product_id=p.id, customer_id=cu.id,
                                    period_start=d, transaction_date=d, units=u, revenue=0))

        M = ["dsi_sellout.units", "dsi_sellout.units_prior_period", "dsi_sellout.units_prior_year", "dsi_sellout.units_pct_change"]

        # D1: platform month, window 2026-03-01..2026-04-30 (E10 defect 1), plus prior period across the window start
        cu = await cust()
        for d, u in [(date(2025, 3, 15), 100), (date(2025, 4, 15), 40), (date(2026, 2, 10), 7), (date(2026, 3, 5), 10), (date(2026, 4, 5), 20)]:
            await sell(cu, d, u)
        await db.flush()
        rows, tot, _ = await run_model(db, M, ["period"], "month", "2026-03-01", "2026-04-30", {"customer": cu.id})
        got = [(str(r["bucket_start"]), r["dsi_sellout.units"], r["dsi_sellout.units_prior_period"], r["dsi_sellout.units_prior_year"]) for r in rows]
        check("D1 platform month window: (bucket, units, prev, prior_year)", got,
              [("2026-03-01", 10.0, 7.0, 100.0), ("2026-04-01", 20.0, 10.0, 40.0)])

        # D2: Sunday week, window opens mid-week, prev + prior year together (E10 defect 2)
        sun = BusinessCalendar({"week_start_day": 6})
        cu = await cust()
        wk = sun.bucket(date(2026, 3, 4), "week")  # Sun 2026-03-01
        prevwk = sun.bucket(wk.start - timedelta(days=1), "week")
        pywk = sun.bucket(sun.same_day_last_year(wk.start), "week")
        for d, u in [(wk.start, 9), (date(2026, 3, 4), 4), (wk.start + timedelta(days=7), 6), (prevwk.start, 11), (pywk.start + timedelta(days=1), 50)]:
            await sell(cu, d, u)
        await db.flush()
        rows, tot, _ = await run_model(db, M, ["period"], "week", "2026-03-04", "2026-03-14", {"customer": cu.id}, cal=sun)
        got = [(str(r["bucket_start"]), r["dsi_sellout.units"], r["dsi_sellout.units_prior_period"], r["dsi_sellout.units_prior_year"]) for r in rows]
        check("D2 Sunday week rows (first bucket partial=4, its prev 11, prior-year 50)", got,
              [(str(wk.start), 4.0, 11.0, 50.0), (str(wk.start + timedelta(days=7)), 6.0, 4.0, None)])
        rsum = sum(r["dsi_sellout.units"] for r in rows)
        check("D2 rows sum == total", rsum, tot["dsi_sellout.units"])

        # D3: retail 4-4-5 previous period and prior year, month + quarter, across a fiscal-year boundary
        r445 = BusinessCalendar({"type": "retail_445"})
        for grain in ("month", "quarter"):
            cu = await cust()
            fy = r445.year(date(2026, 6, 1))
            first = r445.bucket(fy.start, grain)              # P01 / Q1 of FY
            prev = r445.bucket(first.start - timedelta(days=1), grain)   # last of the previous FY
            py = r445.bucket(r445.same_day_last_year(first.start), grain)
            second = r445.bucket(first.end + timedelta(days=1), grain)
            py2 = r445.bucket(r445.same_day_last_year(second.start), grain)
            for d, u in [(first.start + timedelta(days=2), 22), (second.start, 33), (prev.start + timedelta(days=1), 11),
                         (py.start + timedelta(days=3), 101), (py2.start + timedelta(days=3), 202)]:
                await sell(cu, d, u)
            await db.flush()
            rows, tot, _ = await run_model(db, M, ["period"], grain, first.start.isoformat(), second.end.isoformat(), {"customer": cu.id}, cal=r445)
            got = [(r["dsi_sellout.units"], r["dsi_sellout.units_prior_period"], r["dsi_sellout.units_prior_year"]) for r in rows]
            check(f"D3 retail_445 {grain} FY boundary (units, prev, prior_year)", got, [(22.0, 11.0, 101.0), (33.0, 22.0, 202.0)])

        # D4: retail 4-4-5 53-week year: last period and week 53
        y53 = None
        for y in range(2020, 2032):
            yr = r445.year(date(y, 6, 1))
            if yr.days == 371:
                y53 = yr
                break
        out(f"  53-week retail year found: {y53.label if y53 else None} {y53.start if y53 else ''}..{y53.end if y53 else ''}")
        if y53 is not None:
            cu = await cust()
            p12 = r445.bucket(y53.end, "month")
            p12_prev_year = r445.bucket(r445.same_day_last_year(p12.start), "month")
            w53 = r445.bucket(y53.end, "week")
            w53_py = r445.bucket(r445.same_day_last_year(w53.start), "week")
            for d, u in [(p12.start, 1), (w53.start, 2), (p12_prev_year.start, 30), (w53_py.start, 40)]:
                await sell(cu, d, u)
            await db.flush()
            rows, tot, _ = await run_model(db, M, ["period"], "month", p12.start.isoformat(), p12.end.isoformat(), {"customer": cu.id}, cal=r445)
            out(f"  D4 P12 of 53-wk year {p12.start}..{p12.end} ({p12.days} d): {[(r['dsi_sellout.units'], r['dsi_sellout.units_prior_year']) for r in rows]} "
                f"(expected units 3, prior year = P12 prior year incl. its last week = 30+40 if w53_py falls in it: w53_py={w53_py.start})")
            rows, tot, _ = await run_model(db, M, ["period"], "week", w53.start.isoformat(), w53.end.isoformat(), {"customer": cu.id}, cal=r445)
            out(f"  D4 week 53 {w53.start}: {[(r['dsi_sellout.units'], r['dsi_sellout.units_prior_year']) for r in rows]} (python py week {w53_py.start})")

        # D5: day grain on day fact vs CST refusal
        cu = await cust()
        for d, u in [(date(2025, 3, 10), 70), (date(2026, 3, 9), 3), (date(2026, 3, 10), 5)]:
            await sell(cu, d, u)
        await db.flush()
        rows, tot, _ = await run_model(db, M, ["period"], "day", "2026-03-10", "2026-03-10", {"customer": cu.id})
        got = [(str(r["bucket_start"]), r["dsi_sellout.units"], r["dsi_sellout.units_prior_period"], r["dsi_sellout.units_prior_year"]) for r in rows]
        check("D5 day grain (units, prev day, same day last year)", got, [("2026-03-10", 5.0, 3.0, 70.0)])
        for mid in ("cst_sellthrough.units", "cpor.result_units", "lineup.units", "sellin.units", "recorded_prices.net_price_avg", "returns.units"):
            _, plan = plan_of([mid], ["period"], "day")
            out(f"  day grain {mid}: {'ALLOWED' if plan.measures else 'REFUSED: ' + plan.refusals[0].reason[:60]}")

        # D6: per-week total on a retail calendar without a window (window_weeks is Gregorian)
        cu = await cust()
        p03 = r445.bucket(date(2026, 3, 20), "month")
        for d, u in [(p03.start, 35), (p03.end, 35)]:
            await sell(cu, d, u)
        await db.flush()
        rows, tot, c = await run_model(db, ["dsi_sellout.units", "dsi_sellout.units_per_week"], ["period"], "month", filters={"customer": cu.id}, cal=r445)
        out(f"  D6 retail P03 {p03.start}..{p03.end} ({p03.days} d): row per_week={[r['dsi_sellout.units_per_week'] for r in rows]} "
            f"total per_week={tot['dsi_sellout.units_per_week']} expected {70 * 7 / p03.days:.4f}")

        # D7: share + running total with limit (share over all rows, not displayed)
        cu1, cu2 = await cust(), await cust()
        for cu_, d, u in [(cu1, date(2026, 5, 4), 30), (cu2, date(2026, 5, 4), 10), (cu1, date(2026, 6, 1), 60)]:
            await sell(cu_, d, u)
        await db.flush()
        rows, tot, _ = await run_model(db, ["dsi_sellout.units", "dsi_sellout.units_share", "dsi_sellout.units_running_total"],
                                       ["period", "customer"], "month", "2026-05-01", "2026-06-30",
                                       {"customer": [cu1.id, cu2.id]})
        got = [(str(r["bucket_start"]), r["customer_id"] == cu1.id, r["dsi_sellout.units"], round(r["dsi_sellout.units_share"], 4),
                r["dsi_sellout.units_running_total"]) for r in rows]
        check("D7 share/running", got, [("2026-05-01", True, 30.0, 0.3, 30.0), ("2026-05-01", False, 10.0, 0.1, 10.0),
                                        ("2026-06-01", True, 60.0, 0.6, 90.0)])
    finally:
        await db.rollback()
        await db.close()


async def main() -> None:
    for fn in (e1, e6, e7, e8):
        try:
            await fn()
        except Exception:  # noqa: BLE001
            out(f"ERROR in {fn.__name__}:\n{traceback.format_exc()}")
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
