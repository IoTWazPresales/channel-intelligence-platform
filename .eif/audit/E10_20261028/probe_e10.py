"""E10 independent probes for E6-E9 (a4118c30). Review artifact, not product code.

Part A runs on cip_test inside one transaction that is rolled back.
Part B runs on cip inside one READ ONLY transaction (shape and timing only, no writes).

Run from the project root:  apps/api/.venv/Scripts/python.exe .eif/audit/E10_20261028/probe_e10.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402

_s = get_settings()
CIP_SYNC_URL = _s.database_url_sync


def _swap(url: str, target: str) -> str:
    return re.sub(r"/cip(\?|$)", rf"/{target}\1", url)


os.environ["DATABASE_URL"] = _swap(_s.database_url, "cip_test")
os.environ["DATABASE_URL_SYNC"] = _swap(_s.database_url_sync, "cip_test")
get_settings.cache_clear()

from sqlalchemy import create_engine, text  # noqa: E402

from app.models.facts import FactSalesSellout  # noqa: E402
from app.query.model.compiler import bucket_fields, compile_plan  # noqa: E402
from app.query.model.graph import V2Request, plan_request  # noqa: E402
from app.query.model.loader import clear_model_cache, default_model  # noqa: E402
from app.semantics.registry import load_catalog  # noqa: E402
from app.services.business_calendar import BusinessCalendar  # noqa: E402

RESULTS: list[str] = []


def out(line: str) -> None:
    RESULTS.append(line)
    print(line, flush=True)


def plan_for(measures, breakdowns, grain, frm=None, to=None):
    dm = default_model()
    req = V2Request(
        measures=list(measures),
        breakdowns=list(breakdowns),
        period_grain=grain,
        period_from=frm,
        period_to=to,
    )
    plan = plan_request(dm, req, v1_catalog=load_catalog())
    assert plan.ok, [r.reason for r in plan.refusals]
    return dm, plan


async def rows_of(db, dm, plan, tenant, calendar=None):
    compiled = compile_plan(dm, plan, tenant_id=tenant, calendar=calendar)
    res = (await db.execute(compiled.rows)).all()
    tot = (await db.execute(compiled.totals)).one()._mapping
    return compiled, [r._mapping for r in res], tot


# ----------------------------------------------------------------------------- Part A (cip_test)


async def part_a() -> None:
    from app.db.session import AsyncSessionLocal
    from tests.test_query_model_db import TA, _key, _seed

    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    out(f"A.db = {name}")
    if name != "cip_test":
        out("A.SKIPPED: not cip_test")
        await db.close()
        return
    try:
        s = await _seed(db)
        # One year-earlier row so a prior-year comparison has something to find.
        db.add(
            FactSalesSellout(
                source_key=_key("dsi"), tenant_id=TA, product_id=s.pA1.id, customer_id=s.cA1.id,
                distributor_id=s.dA.id, period_start=date(2025, 3, 3), transaction_date=date(2025, 3, 3),
                units=100, revenue=0,
            )
        )
        await db.flush()

        # A1 prior_year inside a bounded window (the normal dashboard request).
        dm, plan = plan_for(
            ["dsi_sellout.units", "dsi_sellout.units_prior_year"], ["period"], "month", "2026-03-01", "2026-04-30"
        )
        _, rows, _ = await rows_of(db, dm, plan, TA)
        by = {str(r["bucket_start"]): (r["out0"], r["out1"]) for r in rows}
        out(f"A1 prior_year window 2026-03..04 rows={by}  expected 2026-03-01 prior_year=100")
        # A1b same request without a window (prior-year rows are inside the scan).
        dm, plan = plan_for(["dsi_sellout.units", "dsi_sellout.units_prior_year"], ["period"], "month")
        _, rows, _ = await rows_of(db, dm, plan, TA)
        by = {str(r["bucket_start"]): (r["out0"], r["out1"]) for r in rows}
        out(f"A1b prior_year no window rows={by}")

        # A2 Sunday weeks + prior_period, window starting mid-week.
        sunday = BusinessCalendar({"type": "gregorian", "fiscal_year_start_month": 1, "week_start_day": 6})
        dm, plan = plan_for(
            ["dsi_sellout.units", "dsi_sellout.units_prior_period"], ["period"], "week", "2026-03-04", "2026-03-31"
        )
        _, rows, tot = await rows_of(db, dm, plan, TA, calendar=sunday)
        listed = [(str(r["bucket_start"]), float(r["out0"])) for r in rows]
        out(f"A2 sunday weeks + prior rows={listed} rows_sum={sum(v for _, v in listed)} total={float(tot['t0'])}")
        # A2b same calendar, no comparison measure (control).
        dm, plan = plan_for(["dsi_sellout.units"], ["period"], "week", "2026-03-04", "2026-03-31")
        _, rows, tot = await rows_of(db, dm, plan, TA, calendar=sunday)
        listed = [(str(r["bucket_start"]), float(r["out0"])) for r in rows]
        out(f"A2b sunday weeks control rows={listed} rows_sum={sum(v for _, v in listed)} total={float(tot['t0'])}")

        # A3 retail 4-4-5 months + prior_period.
        retail = BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1})
        dm, plan = plan_for(["dsi_sellout.units", "dsi_sellout.units_prior_period"], ["period"], "month")
        _, rows, _ = await rows_of(db, dm, plan, TA, calendar=retail)
        listed = [
            (bucket_fields(r["bucket_start"], "month", retail)["bucket_key"], str(r["bucket_start"]), r["out0"], r["out1"])
            for r in rows
        ]
        out(f"A3 retail_445 month + prior rows={listed}")

        # A4 share_of_total and running_total on a limited result.
        dm, plan = plan_for(
            ["dsi_sellout.units", "dsi_sellout.units_share", "dsi_sellout.units_running_total"],
            ["period", "customer"],
            "month",
            "2026-03-01",
            "2027-01-31",
        )
        _, rows, tot = await rows_of(db, dm, plan, TA)
        share_sum = sum(float(r["out1"] or 0) for r in rows)
        out(f"A4 share sum over rows={share_sum:.6f} rows={len(rows)} total_units={float(tot['t0'])}")
        out("A4 rows=" + str([(str(r['bucket_start']), r['customer_id'], float(r['out0']), float(r['out2'])) for r in rows]))
    finally:
        await db.rollback()
        await db.close()


# ----------------------------------------------------------------------------- Part B (cip read only)


def part_b() -> None:
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg://", CIP_SYNC_URL)
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            name = conn.execute(text("select current_database()")).scalar_one()
            out(f"B.db = {name}")
            if name != "cip":
                out("B.SKIPPED: not cip")
                return
            conn.execute(text("SELECT set_config('cip.product_lines', '*', true)"))
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))

            states = conn.execute(
                text(
                    "SELECT lower(line_state) s, count(*) n, count(ship_confirm_date) with_scd, "
                    "coalesce(sum(quantity),0) qty FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1"
                )
            ).all()
            out("B1 shipment line_state: " + str([tuple(r) for r in states]))
            from app.services.shipment_strict_pair import OPEN_TWIN_REMAINDER_SQL

            twin = conn.execute(
                text(
                    "WITH r AS (" + OPEN_TWIN_REMAINDER_SQL + ") "
                    "SELECT count(*) FILTER (WHERE lower(f.line_state)='open_order') open_rows, "
                    "coalesce(sum(f.quantity) FILTER (WHERE lower(f.line_state)='open_order'),0) open_qty_raw, "
                    "coalesce(sum(coalesce(r.counted_qty, f.quantity)) FILTER (WHERE lower(f.line_state)='open_order'),0) open_qty_counted, "
                    "count(*) FILTER (WHERE lower(f.line_state)='open_order' AND f.ship_confirm_date IS NOT NULL) open_with_scd "
                    "FROM fact_inbound_shipment f LEFT JOIN r ON r.fact_id = f.id"
                )
            ).one()
            out(f"B2 open lines raw vs twin-counted: {tuple(twin)}")
            cust = conn.execute(
                text(
                    "SELECT count(*) FILTER (WHERE customer_id IS NULL AND resolved_customer_id IS NOT NULL), "
                    "count(*) FILTER (WHERE distributor_id IS NULL AND resolved_distributor_id IS NOT NULL), "
                    "count(*) FILTER (WHERE customer_id IS DISTINCT FROM resolved_customer_id AND resolved_customer_id IS NOT NULL) "
                    "FROM fact_inbound_shipment"
                )
            ).one()
            out(f"B3 shipment customer_id null but resolved set / distributor same / customer differs: {tuple(cust)}")

            sellin = conn.execute(
                text(
                    "SELECT count(*), count(DISTINCT extract(day from period_start)), "
                    "count(*) FILTER (WHERE extract(day from period_start) = 1), "
                    "count(*) FILTER (WHERE extract(isodow from period_start) = 1), min(period_start), max(period_start) "
                    "FROM fact_sales_sellin"
                )
            ).one()
            out(f"B4 sell-in rows, distinct day-of-month, on day 1, on Monday, min, max: {tuple(sellin)}")

            pricing = conn.execute(
                text("SELECT currency, count(*) FROM fact_pricing GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
            ).all()
            out("B5 fact_pricing currencies: " + str([tuple(r) for r in pricing]))

            lineup_null = conn.execute(
                text("SELECT count(*) FILTER (WHERE commercial_status IS NULL), count(*) FROM commercial_lineup_case")
            ).one()
            out(f"B6 lineup cases with null commercial_status / all: {tuple(lineup_null)}")

            # B7 timing: week grain on dsi_sellout, platform vs retail_445 CASE buckets.
            clear_model_cache()
            dm, plan = plan_for(["dsi_sellout.units"], ["period"], "week")
            for label, cal in (("platform", None), ("retail_445", BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1}))):
                compiled = compile_plan(dm, plan, tenant_id="default", calendar=cal)
                t0 = time.perf_counter()
                n = len(conn.execute(compiled.rows).all())
                ms = (time.perf_counter() - t0) * 1000
                out(f"B7 week grain {label}: rows={n} ms={ms:.0f}")
        finally:
            tx.rollback()
    eng.dispose()


def main() -> None:
    clear_model_cache()
    if "--b-only" not in sys.argv:
        asyncio.run(part_a())
    part_b()
    Path(__file__).with_name("probe_output.txt").write_text("\n".join(RESULTS) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
