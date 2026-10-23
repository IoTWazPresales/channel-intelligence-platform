"""N-0115 parity: the model compiler against the v1 volume_series handler, read-only.

  python scripts/n0115_parity.py --db cip_test
  python scripts/n0115_parity.py --db cip_n0115 --owner        # pg_dump clone, as the owner

For sellout_units and cst_sellthrough_units, every v1 allowed grain x period grain week / month /
quarter x (no filter, the customer with the most rows): v1 handler value and rows vs the compiler's
SQL (no row limit here, so every row is compared). Then times 8 widget-shaped v2 queries through
``run_v2`` (cache off). Everything runs in ONE READ ONLY transaction that is rolled back.
Refuses the database name ``cip`` (``clone_url``). Prints no connection string.

Note: as the owner, row security is bypassed; scoped timings need a non-owner role with grants.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))


async def _main(db_name: str, owner: bool, tenant: str) -> int:
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.fact_customer_sellthrough import FactCustomerSellthrough
    from app.models.facts import FactSalesSellout
    from app.query.calendar_grain import as_date
    from app.query.handlers.volume_series import handle_volume
    from app.query.model.compiler import bucket_key, compile_plan
    from app.query.model.execute import run_v2
    from app.query.model.graph import V2Request, plan_request
    from app.query.model.loader import default_model
    from app.query.types import QueryRequest
    from app.semantics.registry import load_catalog
    from scripts.db_on import clone_url

    url = clone_url(db_name, owner=owner)  # raises SystemExit on 'cip'
    engine = create_async_engine(url)
    dm = default_model()
    v1 = load_catalog()
    try:
        async with AsyncSession(engine) as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            who = (await db.execute(text("select current_database(), current_user"))).one()
            print(f"database={who[0]} user={who[1]} tenant={tenant} read_only=yes")

            top: dict[str, int | None] = {}
            for metric, model_cls in (("sellout_units", FactSalesSellout), ("cst_sellthrough_units", FactCustomerSellthrough)):
                row = (
                    await db.execute(
                        select(model_cls.customer_id, func.count())
                        .where(model_cls.tenant_id == tenant)
                        .group_by(model_cls.customer_id)
                        .order_by(func.count().desc(), model_cls.customer_id)
                        .limit(1)
                    )
                ).first()
                top[metric] = int(row[0]) if row else None

            print()
            print("| metric | grains | period | filter | old total | new total | rows old | rows new | rows compared | mismatches | v1 ms | compiler ms |")
            print("|---|---|---|---|---|---|---|---|---|---|---|---|")
            all_mismatch = 0
            cases = 0
            for metric, mid in (("sellout_units", "dsi_sellout.units"), ("cst_sellthrough_units", "cst_sellthrough.units")):
                metric_def = v1.metric_by_key(metric)
                grain_sets = [sorted(g) for g in metric_def.allowed_grains] + [[]]
                for grains in grain_sets:
                    for pg in (("week", "month", "quarter") if "period" in grains else (None,)):
                        for cust in dict.fromkeys((None, top[metric])):
                            label_filter = f"customer={cust}" if cust else "none"
                            t0 = time.perf_counter()
                            old = await handle_volume(
                                db,
                                QueryRequest(
                                    metric=metric, grains=grains, tenant_id=tenant,
                                    filters={"customer_id": cust} if cust else {}, period_grain=pg,
                                ),
                                metric_key=metric,
                            )
                            v1_ms = (time.perf_counter() - t0) * 1000
                            plan = plan_request(
                                dm,
                                V2Request(measures=[mid], breakdowns=grains, period_grain=pg, filters={"customer": cust} if cust else {}),
                                v1_catalog=v1,
                            )
                            if old.status != "ok" or not plan.measures:
                                reason = old.message if old.status != "ok" else plan.refusals[0].reason
                                print(f"| {metric} | {','.join(grains) or '-'} | {pg or '-'} | {label_filter} | refused | refused | - | - | - | - | - | - |  <!-- {reason} -->")
                                continue
                            plan.limit = 10_000_000  # parity compares every row
                            compiled = compile_plan(dm, plan, tenant_id=tenant)
                            t1 = time.perf_counter()
                            if compiled.stored_types is not None:
                                await db.execute(compiled.stored_types)
                            new_rows = (await db.execute(compiled.rows)).all()
                            new_total_row = (await db.execute(compiled.totals)).one()._mapping
                            c_ms = (time.perf_counter() - t1) * 1000
                            lab = compiled.measure_labels[mid]
                            new_total = float(new_total_row[compiled.total_labels[mid]] or 0)

                            def key_old(r):
                                out = []
                                for g in sorted(grains):
                                    if g == "period":
                                        out.append(r.get("bucket_key"))
                                    elif g == "site_label":
                                        out.append("Unassigned" if r.get("site_label") is None else r.get("site_label"))
                                    else:
                                        out.append(r.get(f"{g}_id"))
                                return tuple(out)

                            def key_new(m):
                                out = []
                                for g in sorted(grains):
                                    if g == "period":
                                        out.append(bucket_key(as_date(m["bucket_start"]), pg))
                                    elif g == "site_label":
                                        out.append(m["site_label"])
                                    else:
                                        out.append(m[f"{g}_id"])
                                return tuple(out)

                            o = {key_old(r): round(float(r["value"]), 6) for r in (old.rows or [])}
                            n = {key_new(r._mapping): round(float(r._mapping[lab] or 0), 6) for r in new_rows}
                            keys = set(o) | set(n)
                            mism = sum(1 for k in keys if o.get(k) != n.get(k))
                            if round(float(old.value or 0), 6) != round(new_total, 6):
                                mism += 1
                            all_mismatch += mism
                            cases += 1
                            print(
                                f"| {metric} | {','.join(grains) or '-'} | {pg or '-'} | {label_filter} | "
                                f"{float(old.value or 0):,.4f} | {new_total:,.4f} | {len(old.rows or [])} | {len(new_rows)} | "
                                f"{len(keys)} | {mism} | {v1_ms:.0f} | {c_ms:.0f} |"
                            )
            print()
            print(f"parity cases: {cases}; total mismatches: {all_mismatch}")

            print()
            print("| widget-shaped v2 query (run_v2, cache off) | rows | ms |")
            print("|---|---|---|")
            widgets = [
                ("DSI units by month, 2025-11..2026-10", V2Request(measures=["dsi_sellout.units"], breakdowns=["period"], period_grain="month", period_from="2025-11-01", period_to="2026-10-31")),
                ("DSI top 10 dealers, units + lines, 2026", V2Request(measures=["dsi_sellout.units", "dsi_sellout.lines"], breakdowns=["customer"], period_from="2026-01-01", period_to="2026-12-31", limit=10)),
                ("DSI units + % change by week, 2026", V2Request(measures=["dsi_sellout.units", "dsi_sellout.units_pct_change"], breakdowns=["period"], period_grain="week", period_from="2026-01-01", period_to="2026-10-31")),
                ("DSI units by month x region x bu", V2Request(measures=["dsi_sellout.units"], breakdowns=["period", "region", "bu"], period_grain="month", period_from="2026-01-01")),
                ("CST units by customer x product (top 500)", V2Request(measures=["cst_sellthrough.units"], breakdowns=["customer", "product"])),
                ("CST stock beside units/week by customer, last 8 weeks", V2Request(measures=["cst_sellthrough.reported_soh", "cst_sellthrough.units_per_week"], breakdowns=["customer"], period_from="2026-08-17", period_to="2026-10-11")),
                ("CST units by month x store", V2Request(measures=["cst_sellthrough.units"], breakdowns=["period", "site_label"], period_grain="month")),
                ("CPOR support USD + delivery rate by status x promo type", V2Request(measures=["cpor.support_usd", "cpor.delivery_rate", "cpor.cases"], breakdowns=["status", "promo_type"])),
            ]
            for label, req in widgets:
                t0 = time.perf_counter()
                r = await run_v2(db, req, tenant_id=tenant, skip_cache=True, dm=dm)
                ms = (time.perf_counter() - t0) * 1000
                status = "" if r["ok"] else f" REFUSED: {r['refusals'][0]['reason']}"
                print(f"| {label}{status} | {len(r['rows'])} | {ms:.0f} |")
            await db.rollback()
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, help="database name (never cip)")
    p.add_argument("--owner", action="store_true", help="log in as postgres (PG_OWNER) on a clone")
    p.add_argument("--tenant", default="default")
    a = p.parse_args()
    if a.db.strip().lower() == "cip":
        raise SystemExit("ABORT: refusing to run on cip; use a pg_dump clone")
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # psycopg async on Windows
    return asyncio.run(_main(a.db, a.owner, a.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
