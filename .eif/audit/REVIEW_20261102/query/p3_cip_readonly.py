"""GOV-008 review 2026-11-02 (N-0115). Read-only checks and timings on cip.

The connection is default_transaction_read_only=on; statement_timeout 60 s; product lines '*'
(owner role cip, so this is NOT a non-owner measurement). The compiler's own statements run;
nothing is written. The app settings are pointed at cip_test so no app session can reach cip.
Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/query/p3_cip_readonly.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"

from sqlalchemy import create_engine, text  # noqa: E402

from app.query.model.compiler import compile_plan  # noqa: E402
from app.query.model.graph import V2Request, plan_request  # noqa: E402
from app.query.model.loader import default_model  # noqa: E402
from app.semantics.registry import load_catalog  # noqa: E402
from app.services.business_calendar import BusinessCalendar, tenant_calendar  # noqa: E402

OUT = Path(__file__).with_name("p3_output.txt")
LINES: list[str] = []


def out(s: str) -> None:
    LINES.append(s)
    print(s, flush=True)


eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip",
                    connect_args={"options": "-c default_transaction_read_only=on"})


def compiled(measures, bds=(), grain=None, frm=None, to=None, filters=None, cal=None):
    dm = default_model()
    plan = plan_request(dm, V2Request(measures=list(measures), breakdowns=list(bds), period_grain=grain,
                                      period_from=frm, period_to=to, filters=dict(filters or {})), v1_catalog=load_catalog())
    assert plan.measures, [r.reason for r in plan.refusals]
    return compile_plan(dm, plan, tenant_id="default", calendar=cal)


with eng.connect() as conn:
    tx = conn.begin()
    try:
        conn.execute(text("SET LOCAL statement_timeout='60s'"))
        conn.execute(text("select set_config('cip.product_lines','*',true)"))
        db, ro = conn.execute(text("select current_database(), current_setting('transaction_read_only')")).one()
        out(f"db={db} read_only={ro}")
        assert db == "cip" and ro == "on"
        out(f"tenant 'default' calendar config: {tenant_calendar('default').config}")

        # 1 shipped quantity vs state 'shipped'
        c = compiled(["shipments.quantity", "shipments.lines"])
        t = conn.execute(c.totals).one()._mapping
        ref = conn.execute(text("select sum(quantity), count(*) from fact_inbound_shipment where tenant_id='default' "
                                "and lower(line_state)='shipped' and ship_confirm_date is not null")).one()
        out(f"[S1] v2 shipments.quantity/lines total = {t['t0']} / {t['t1']};  state 'shipped' only = {ref[0]} / {ref[1]};"
            f"  difference = {t['t0'] - ref[0]} units / {t['t1'] - ref[1]} lines")
        by = conn.execute(text("select lower(line_state), sum(quantity), count(*) from fact_inbound_shipment where tenant_id='default' "
                               "and ship_confirm_date is not null group by 1 order by 1")).all()
        out(f"[S1] dated lines by state: {[tuple(r) for r in by]}")
        sup = conn.execute(text(
            "select count(*), count(*) filter (where n.id is not null and lower(n.line_state)='shipped'), "
            "count(*) filter (where n.ship_confirm_date is not null) "
            "from fact_inbound_shipment s left join fact_inbound_shipment n on n.id = s.superseded_by_fact_id "
            "where lower(s.line_state)='closed_superseded' and s.ship_confirm_date is not null")).one()
        out(f"[S1] dated closed_superseded rows / whose superseding row is 'shipped' / superseding row dated: {tuple(sup)}")
        cs = conn.execute(text(
            "select count(*), count(*) filter (where exists (select 1 from fact_inbound_shipment t where t.tenant_id=s.tenant_id "
            "and lower(t.line_state)='shipped' and lower(trim(coalesce(t.operating_unit,'')))=lower(trim(coalesce(s.operating_unit,''))) "
            "and lower(trim(t.order_no))=lower(trim(s.order_no)) and lower(trim(t.item_code))=lower(trim(s.item_code)))) "
            "from fact_inbound_shipment s where lower(s.line_state)='closed_shipped' and s.ship_confirm_date is not null")).one()
        out(f"[S1] dated closed_shipped rows / with a strict shipped twin: {tuple(cs)}")

        # 2 hidden-counterpart bypass size: priced units vs units
        c = compiled(["dsi_sellout.units", "dsi_sellout.priced_units"])
        t = conn.execute(c.totals).one()._mapping
        out(f"[S2] dsi_sellout.units total={t['t0']} priced_units total={t['t1']} (priced share {float(t['t1']) / float(t['t0']):.4f})")

        # 3 period floors of lineup / cpor / pricing / returns / sellin
        for tbl, col in [("commercial_lineup_case", "inferred_period_start"), ("cpor_case", "window_start"), ("fact_returns", "transaction_date")]:
            r = conn.execute(text(f"select count(*), count({col}), count(*) filter (where extract(day from {col})=1), "
                                  f"count(distinct {col}), min({col}), max({col}) from {tbl}")).one()
            out(f"[S3] {tbl}.{col}: rows, non-null, on day 1, distinct dates, min, max = {tuple(r)}")

        # 4 timings (owner role, product lines '*', cold then warm). Rows statement + totals statement.
        r445 = BusinessCalendar({"type": "retail_445"})
        sun = BusinessCalendar({"week_start_day": 6})
        cases = [
            ("dsi units by week (all time)", dict(measures=["dsi_sellout.units"], bds=["period"], grain="week")),
            ("dsi units+prev+prior_year+pct by month, 2025-01..2026-06", dict(measures=["dsi_sellout.units", "dsi_sellout.units_prior_period", "dsi_sellout.units_prior_year", "dsi_sellout.units_pct_change"], bds=["period"], grain="month", frm="2025-01-01", to="2026-06-30")),
            ("dsi units by customer x product (limit 500)", dict(measures=["dsi_sellout.units", "dsi_sellout.dealers"], bds=["customer", "product"])),
            ("dsi units+share+running by month x bu", dict(measures=["dsi_sellout.units", "dsi_sellout.units_share", "dsi_sellout.units_running_total"], bds=["period", "bu"], grain="month")),
            ("dsi dealers+avg by retail_445 month, prev+prior_year", dict(measures=["dsi_sellout.dealers", "dsi_sellout.units_avg", "dsi_sellout.units_prior_period", "dsi_sellout.units_prior_year"], bds=["period"], grain="month", cal=r445)),
            ("dsi units by Sunday week + prev, window", dict(measures=["dsi_sellout.units", "dsi_sellout.units_prior_period"], bds=["period"], grain="week", frm="2025-06-04", to="2026-06-30", cal=sun)),
            ("dsi units by day, 2026-03", dict(measures=["dsi_sellout.units"], bds=["period"], grain="day", frm="2026-03-01", to="2026-03-31")),
            ("cst units+stock by customer", dict(measures=["cst_sellthrough.units", "cst_sellthrough.reported_soh"], bds=["customer"])),
            ("cst units by month x site", dict(measures=["cst_sellthrough.units", "cst_sellthrough.units_per_week"], bds=["period", "site_label"], grain="month")),
            ("shipments qty by month x customer", dict(measures=["shipments.quantity", "shipments.lines"], bds=["period", "customer"], grain="month")),
            ("shipments open qty by customer (twin remainder)", dict(measures=["shipments.open_quantity", "shipments.open_lines"], bds=["customer"])),
            ("distributor on-hand by distributor x product", dict(measures=["distributor_stock.on_hand"], bds=["distributor", "product"])),
            ("returns by month x distributor", dict(measures=["returns.units", "returns.lines"], bds=["period", "distributor"], grain="month")),
            ("lineup units by status x bu", dict(measures=["lineup.units", "lineup.lines"], bds=["status", "bu"])),
            ("cpor delivery rate by quarter x customer", dict(measures=["cpor.delivery_rate", "cpor.support_usd"], bds=["period", "customer"], grain="quarter")),
        ]
        for label, kw in cases:
            c = compiled(**kw)
            times = []
            for _ in range(2):
                t0 = time.perf_counter()
                n = len(conn.execute(c.rows).all())
                conn.execute(c.totals).one()
                times.append((time.perf_counter() - t0) * 1000)
            out(f"[T] {label}: rows={n} cold={times[0]:.0f} ms warm={times[1]:.0f} ms {'OVER 2s' if max(times) > 2000 else ''}")
    finally:
        tx.rollback()
eng.dispose()
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
