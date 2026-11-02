"""GOV-008 review 2026-11-02 (N-0115). Catalog/planner agreement and cache isolation.

Part 1 is pure (no DB). Part 2 seeds cip_test in one session and rolls back.
Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/query/p4_catalog_cache.py
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
from datetime import date
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"

from sqlalchemy import text  # noqa: E402

from app.core.product_line_scope import apply_product_line_guc, request_product_lines, request_role  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.dimensions import DimCustomer, DimProduct  # noqa: E402
from app.models.facts import FactSalesSellout  # noqa: E402
from app.query.cache import clear_query_cache  # noqa: E402
from app.query.model.calc import total_for, window_weeks  # noqa: E402
from app.query.model.catalog import catalog_v2  # noqa: E402
from app.query.model.compiler import compile_plan  # noqa: E402
from app.query.model.execute import run_v2  # noqa: E402
from app.query.model.graph import V2Request, plan_request  # noqa: E402
from app.query.model.loader import default_model  # noqa: E402
from app.semantics.registry import load_catalog  # noqa: E402
from app.services.business_calendar import BusinessCalendar  # noqa: E402

OUT = Path(__file__).with_name("p4_output.txt")
LINES: list[str] = []
TAG = secrets.token_hex(4)


def out(s: str) -> None:
    LINES.append(s)
    print(s, flush=True)


def part1() -> None:
    dm = default_model()
    cat = load_catalog()
    listed = catalog_v2(dm, cat, is_admin=False)
    mismatches = []
    for m in listed["measures"]:
        for g in m.get("period_grains") or []:
            plan = plan_request(dm, V2Request(measures=[m["id"]], breakdowns=["period"], period_grain=g), v1_catalog=cat)
            if not plan.measures:
                mismatches.append((m["id"], g, plan.refusals[0].reason[:70]))
    out(f"[C1] catalog advertises a period grain that the planner refuses: {len(mismatches)}")
    for x in mismatches[:40]:
        out(f"[C1]   {x}")
    # Every advertised breakdown alone should plan
    bad = []
    for m in listed["measures"]:
        for b in m["breakdowns"]:
            plan = plan_request(dm, V2Request(measures=[m["id"]], breakdowns=[b], period_grain="month"), v1_catalog=cat)
            if not plan.measures:
                reason = plan.refusals[0].reason[:70] if plan.refusals else "<no measures and NO refusal>"
                if "needs period" in reason and any("period" in r for r in (m.get("requires") or [])):
                    continue  # advertised via requires
                bad.append((m["id"], b, reason, m.get("requires")))
    out(f"[C2] catalog advertises a breakdown the planner refuses (excluding calc measures whose 'requires' names period): {len(bad)}")
    for x in bad[:20]:
        out(f"[C2]   {x}")
    out(f"[C3] catalog top-level keys: {sorted(listed.keys())}")


async def part2() -> None:
    ta, tb = f"rvc-a-{TAG}", f"rvc-b-{TAG}"
    db = AsyncSessionLocal()
    assert (await db.execute(text("select current_database()"))).scalar_one() == "cip_test"
    try:
        pa = DimProduct(tenant_id=ta, sku=f"rvc{TAG}a"[-30:], name="RVC A", product_line="NB")
        pa2 = DimProduct(tenant_id=ta, sku=f"rvc{TAG}a2"[-30:], name="RVC A2", product_line="NR")
        pb = DimProduct(tenant_id=tb, sku=f"rvc{TAG}b"[-30:], name="RVC B", product_line="NB")
        ca = DimCustomer(tenant_id=ta, code=f"rvc{TAG}ca"[-30:], name="RVC CA")
        cb = DimCustomer(tenant_id=tb, code=f"rvc{TAG}cb"[-30:], name="RVC CB")
        db.add_all([pa, pa2, pb, ca, cb])
        await db.flush()
        for t, p, c, u in [(ta, pa, ca, 10), (ta, pa2, ca, 5), (tb, pb, cb, 999)]:
            db.add(FactSalesSellout(source_key=f"rvc-{TAG}-{p.sku}", tenant_id=t, product_id=p.id, customer_id=c.id,
                                    period_start=date(2026, 3, 2), transaction_date=date(2026, 3, 2), units=u, revenue=0))
        await db.flush()
        cu = DimCustomer(tenant_id=ta, code=f"rvc{TAG}w"[-30:], name="RVC W")
        db.add(cu)
        await db.flush()
        for d in (date(2026, 3, 1), date(2026, 3, 7)):  # Sunday..Saturday: one Sunday week
            db.add(FactSalesSellout(source_key=f"rvc-{TAG}-w-{d}", tenant_id=ta, product_id=pa.id, customer_id=cu.id,
                                    period_start=d, transaction_date=d, units=7, revenue=0))
        await db.flush()
        # Per-week totals on non-platform calendars with no window (row value vs total)
        dm = default_model()
        for cal in (BusinessCalendar({"week_start_day": 6}), BusinessCalendar({"type": "retail_445"})):
            for grain in ("week", "month"):
                plan = plan_request(dm, V2Request(measures=["dsi_sellout.units", "dsi_sellout.units_per_week"], breakdowns=["period"],
                                                  period_grain=grain, filters={"customer": cu.id}), v1_catalog=load_catalog())
                c = compile_plan(dm, plan, tenant_id=ta, calendar=cal)
                rows = (await db.execute(c.rows)).mappings().all()
                tr = (await db.execute(c.totals)).one()._mapping
                weeks = c.weeks_in_window or window_weeks(period_from=None, period_to=None, grain=grain,
                                                          vintage_min=tr["vintage_min"], vintage_max=tr["vintage_max"])
                total = total_for(dm, dm.measure("dsi_sellout.units_per_week"), {m: tr[l] for m, l in c.total_labels.items()}, weeks=weeks)
                out(f"[W] {cal.config['type']} wsd={cal.config['week_start_day']} {grain}: rows (bucket, per_week)="
                    f"{[(str(r['bucket_start']), float(r[c.measure_labels['dsi_sellout.units_per_week']])) for r in rows]} "
                    f"total per_week={None if total is None else round(float(total), 4)} (weeks used {None if weeks is None else round(float(weeks), 3)})")
        clear_query_cache()
        req = V2Request(measures=["dsi_sellout.units"], breakdowns=["bu"])
        a = await run_v2(db, req, tenant_id=ta)
        b = await run_v2(db, req, tenant_id=tb)
        a2 = await run_v2(db, req, tenant_id=ta)
        out(f"[K1] tenant A total={a['totals']} hit={a['cache']['hit']}; tenant B total={b['totals']} hit={b['cache']['hit']}; "
            f"A again hit={a2['cache']['hit']} total={a2['totals']}")
        tok, rtok = request_product_lines.set(frozenset({"NR"})), request_role.set("viewer")
        try:
            await apply_product_line_guc(db)
            s = await run_v2(db, req, tenant_id=ta)
            out(f"[K2] tenant A scoped to NR after an unscoped warm entry: total={s['totals']} hit={s['cache']['hit']} (want 5, miss)")
        finally:
            request_product_lines.reset(tok)
            request_role.reset(rtok)
    finally:
        await db.rollback()
        await db.close()
        clear_query_cache()


if __name__ == "__main__":
    part1()
    asyncio.run(part2())
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
