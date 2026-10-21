"""N-0071 GOV-008 (RUN-20261007-N0071-VER) read-only probe on cip. SELECT only, read-only transaction.

Independent formulation: a plain self-join on the strict key with its own blank/NULL guards,
written here without importing the helper's SQL text. Compared with the helper's ORM set.
Never prints connection strings.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services.shipment_strict_pair import exclude_open_when_shipped_twin, open_has_shipped_twin

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break
assert url.startswith("postgresql+psycopg://"), "unexpected driver"

out: dict = {}

INDEPENDENT = """
SELECT DISTINCT o.id
FROM fact_inbound_shipment o
JOIN fact_inbound_shipment s
  ON s.tenant_id = o.tenant_id
 AND lower(trim(coalesce(s.operating_unit, ''))) = lower(trim(coalesce(o.operating_unit, '')))
 AND lower(trim(s.order_no)) = lower(trim(o.order_no))
 AND lower(trim(s.item_code)) = lower(trim(o.item_code))
WHERE lower(o.line_state) = 'open_order'
  AND lower(s.line_state) = 'shipped'
  AND o.order_no IS NOT NULL AND btrim(o.order_no) <> ''
  AND o.item_code IS NOT NULL AND btrim(o.item_code) <> ''
"""


def md5_ids(ids) -> str:
    return hashlib.md5(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()


eng = create_engine(url)
with eng.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    out["current_database"] = conn.execute(text("SELECT current_database()")).scalar()
    out["transaction_read_only"] = conn.execute(text("SHOW transaction_read_only")).scalar()
    out["rls_product_lines_setting"] = conn.execute(text("SELECT current_setting('cip.product_lines', true)")).scalar()

    out["fact_rows"] = conn.execute(text("SELECT count(*) FROM fact_inbound_shipment")).scalar()
    out["line_state_counts"] = {
        r[0]: r[1] for r in conn.execute(text("SELECT line_state, count(*) FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1"))
    }
    out["null_tenant_rows"] = conn.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE tenant_id IS NULL")).scalar()
    out["null_line_state_rows"] = conn.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state IS NULL")).scalar()

    t0 = time.time()
    indep = {int(r[0]) for r in conn.execute(text(INDEPENDENT))}
    out["independent_join_ids"] = len(indep)
    out["independent_join_md5"] = md5_ids(indep)
    out["independent_join_s"] = round(time.time() - t0, 2)

    t0 = time.time()
    helper = {
        int(r[0])
        for r in conn.execute(
            select(F.id).where(func.lower(F.line_state) == "open_order", open_has_shipped_twin(F))
        )
    }
    out["helper_twin_ids"] = len(helper)
    out["helper_twin_md5"] = md5_ids(helper)
    out["helper_twin_s"] = round(time.time() - t0, 2)
    out["sets_equal"] = indep == helper
    out["in_indep_not_helper"] = len(indep - helper)
    out["in_helper_not_indep"] = len(helper - indep)

    t0 = time.time()
    kept = {int(r[0]) for r in conn.execute(select(F.id).where(exclude_open_when_shipped_twin(F)))}
    out["exclude_filter_s"] = round(time.time() - t0, 2)
    all_ids = {int(r[0]) for r in conn.execute(text("SELECT id FROM fact_inbound_shipment"))}
    dropped = all_ids - kept
    out["exclude_filter_dropped"] = len(dropped)
    out["exclude_dropped_equals_indep"] = dropped == indep
    out["dropped_line_states"] = {
        r[0]: r[1]
        for r in conn.execute(
            text("SELECT line_state, count(*) FROM fact_inbound_shipment WHERE id = ANY(:ids) GROUP BY 1"),
            {"ids": sorted(dropped)},
        )
    }
    agg = conn.execute(
        text("SELECT count(*), coalesce(sum(quantity),0), coalesce(sum(amount),0) FROM fact_inbound_shipment WHERE id = ANY(:ids)"),
        {"ids": sorted(indep)},
    ).one()
    out["indep_rows_units_amount"] = [int(agg[0]), float(agg[1]), float(agg[2])]

    # Blank-key opens: how many would pair if the blank guard were missing (shows the guard is live on cip).
    out["blank_key_open_rows"] = conn.execute(
        text(
            "SELECT count(*) FROM fact_inbound_shipment WHERE lower(line_state)='open_order' "
            "AND (btrim(coalesce(order_no,''))='' OR btrim(coalesce(item_code,''))='')"
        )
    ).scalar()

    # No-rewrite evidence.
    r = conn.execute(
        text(
            "SELECT max(updated_at), max(created_at), "
            "count(*) FILTER (WHERE updated_at >= timestamptz '2026-10-07 00:00:00+02'), "
            "count(*) FILTER (WHERE updated_at >= timestamptz '2026-10-07 13:00:00+02'), "
            "count(*) FILTER (WHERE id = ANY(:ids) AND updated_at >= timestamptz '2026-10-07 00:00:00+02') "
            "FROM fact_inbound_shipment"
        ),
        {"ids": sorted(indep)},
    ).one()
    out["max_updated_at"] = str(r[0])
    out["max_created_at"] = str(r[1])
    out["rows_updated_since_20261007_0000_sast"] = int(r[2])
    out["rows_updated_since_20261007_1300_sast"] = int(r[3])
    out["twin_rows_updated_since_20261007_0000_sast"] = int(r[4])
    st = conn.execute(
        text(
            "SELECT n_tup_upd, n_tup_del, n_tup_ins, n_tup_hot_upd, last_autovacuum, last_autoanalyze "
            "FROM pg_stat_user_tables WHERE relname = 'fact_inbound_shipment'"
        )
    ).one()
    out["pg_stat_cumulative"] = {
        "n_tup_upd": st[0], "n_tup_del": st[1], "n_tup_ins": st[2], "n_tup_hot_upd": st[3],
        "last_autovacuum": str(st[4]), "last_autoanalyze": str(st[5]),
    }
    out["now_db"] = str(conn.execute(text("SELECT now()")).scalar())

    # Check 5: supply overview columns that do not apply the rule. How many twin opens they include.
    r5 = conn.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE pod_date IS NULL AND eta_date IS NOT NULL
                               AND eta_date < (now() AT TIME ZONE 'Africa/Johannesburg')::date) AS eta_past_no_pod_all,
              count(*) FILTER (WHERE pod_date IS NULL AND eta_date IS NOT NULL
                               AND eta_date < (now() AT TIME ZONE 'Africa/Johannesburg')::date
                               AND id = ANY(:ids)) AS eta_past_no_pod_twins,
              count(*) FILTER (WHERE status = 'scheduled' AND pod_date IS NULL AND promise_date IS NOT NULL
                               AND promise_date < (now() AT TIME ZONE 'Africa/Johannesburg')::date
                               AND promise_date >= (now() AT TIME ZONE 'Africa/Johannesburg')::date - 180
                               AND eta_date IS NOT NULL
                               AND eta_date >= (now() AT TIME ZONE 'Africa/Johannesburg')::date
                               AND eta_date <= (now() AT TIME ZONE 'Africa/Johannesburg')::date + 90
                               AND id = ANY(:ids)) AS overdue_commercial_twins,
              count(*) FILTER (WHERE status IS DISTINCT FROM 'received' AND NOT (id = ANY(:ids))) AS supply_open_lines_equiv,
              count(*) FILTER (WHERE status <> 'received' AND NOT (id = ANY(:ids))) AS brief_not_received_equiv,
              count(*) FILTER (WHERE status IS NULL) AS null_status_rows
            FROM fact_inbound_shipment WHERE tenant_id = 'default'
            """
        ),
        {"ids": sorted(indep)},
    ).mappings().one()
    out["check5_supply_overview_sql"] = {k: int(v) for k, v in r5.items()}
    out["tenants"] = [r[0] for r in conn.execute(text("SELECT DISTINCT tenant_id FROM fact_inbound_shipment"))]
    conn.rollback()


async def reader_paths() -> dict:
    from app.api.v1.endpoints.dashboard import summary as dash_summary  # noqa: F401  (import check)
    from app.api.v1.endpoints.shipping import shipping_evidence_lines, shipping_evidence_summary
    from app.services.brief_signals import inbound_not_received_count_stmt
    from app.services.supply_overview import supply_overview

    res: dict = {}
    aeng = create_async_engine(url)
    async with AsyncSession(aeng) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        res["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        res["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()

        t0 = time.time()
        summ = await shipping_evidence_summary(db=db, user=None)
        res["summary_s"] = round(time.time() - t0, 2)
        res["summary_total_lines"] = summ["total_lines"]
        res["summary_open_lines_skipped_shipped_twin"] = summ["open_lines_skipped_shipped_twin"]
        res["summary_by_line_state"] = {b["key"]: b["count"] for b in summ["by_line_state"]}

        def grid_kwargs(**over):
            kw = dict(
                skip=0, limit=1, import_job_id=None, distributor_id=None, customer_id=None, purchase_order_id=None,
                line_state=None, report_type=None, product_resolution_status=None,
                distributor_resolution_status=None, customer_resolution_status=None, status=None, search=None,
                eta_from=None, eta_to=None, date_field="eta_date", date_from=None, date_to=None,
                pod_date_is_null=None, currency_code=None, operating_unit=None, product_family=None,
                product_model=None, include_raw_row=False, plan_quarter=None, plan_quarter_label=None,
                plan_business_unit=None, lineup_attribution=None, lifecycle_bucket=None, slip_direction=None,
                cohort=None, user=None,
            )
            kw.update(over)
            return kw

        t0 = time.time()
        g_all = await shipping_evidence_lines(db=db, **grid_kwargs())
        res["grid_total_all_s"] = round(time.time() - t0, 2)
        res["grid_total_all"] = g_all["total"]
        res["grid_total_by_state"] = {}
        for st in res["summary_by_line_state"]:
            g = await shipping_evidence_lines(db=db, **grid_kwargs(line_state=st))
            res["grid_total_by_state"][st] = g["total"]

        res["brief_dashboard_not_received"] = (await db.scalar(inbound_not_received_count_stmt(None))) or 0
        so = await supply_overview(db, None)
        res["supply_overview_keys"] = {
            k: so.get(k)
            for k in ("open_lines", "open_units", "pipeline_lines", "pipeline_units", "shipped_lines",
                      "eta_past_no_pod_lines", "overdue_commercial_lines", "data_unavailable")
            if k in so
        }
        if "open_lines" not in so:
            res["supply_overview_top_keys"] = sorted(so.keys())
            for k in ("counts", "kpis", "raw"):
                if isinstance(so.get(k), dict):
                    res["supply_overview_" + k] = {kk: str(vv) for kk, vv in so[k].items()}
        await db.rollback()
    await aeng.dispose()
    return res


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # psycopg async on Windows
out["reader_paths"] = asyncio.run(reader_paths())
print(json.dumps(out, indent=2, default=str))
