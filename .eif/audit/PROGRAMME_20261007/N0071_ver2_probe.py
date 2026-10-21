"""N-0071 GOV-008 re-verification (RUN-20261008-N0071-VER2): cip READ ONLY probe.

Independent SQL (GROUP BY shipped totals + join; not the helper's window form) for the
partial lines, remainder, pro-rata value, covered set, "Unreceived past ETA", overdue and
pipeline, compared with the real reader functions. SELECT only, READ ONLY transaction,
rolled back. No secret is printed.
Run from apps/api: .venv/Scripts/python.exe <this file>
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings

OUT = sys.argv[1] if len(sys.argv) > 1 else None

# Independent pairing: shipped totals per strict key by GROUP BY, joined to open rows.
PAIRS_CTE = """
WITH s AS (
  SELECT tenant_id,
         lower(btrim(coalesce(operating_unit, ''))) AS ou,
         lower(btrim(order_no)) AS o,
         lower(btrim(item_code)) AS i,
         sum(coalesce(quantity, 0)) AS shipped_qty,
         count(*) AS n_shipped
  FROM fact_inbound_shipment
  WHERE lower(line_state) = 'shipped'
    AND btrim(coalesce(order_no, '')) <> ''
    AND btrim(coalesce(item_code, '')) <> ''
  GROUP BY 1, 2, 3, 4
),
pairs AS (
  SELECT f.id, f.tenant_id, coalesce(f.quantity, 0) AS open_qty, s.shipped_qty, s.n_shipped,
         s.ou, s.o, s.i,
         CASE WHEN coalesce(f.quantity, 0) > s.shipped_qty THEN 'partial' ELSE 'covered' END AS kind
  FROM fact_inbound_shipment f
  JOIN s ON s.tenant_id = f.tenant_id
        AND s.ou = lower(btrim(coalesce(f.operating_unit, '')))
        AND s.o = lower(btrim(f.order_no))
        AND s.i = lower(btrim(f.item_code))
  WHERE lower(f.line_state) = 'open_order'
    AND btrim(coalesce(f.order_no, '')) <> ''
    AND btrim(coalesce(f.item_code, '')) <> ''
)
"""


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


def _f(x) -> float:
    return float(x or 0)


async def main() -> None:
    from app.api.v1.endpoints import channel_ops, shipping
    from app.models.facts import FactInboundShipment as F
    from app.services.shipment_strict_pair import twin_remainder
    from app.services.shipping_commercial_kpis import predicate_overdue
    from app.services.supply_overview import supply_overview

    out: dict = {"probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    engine = create_async_engine(_url(), connect_args={"options": "-c default_transaction_read_only=on"})
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()
        out["db_now"] = str((await db.execute(text("SELECT now()"))).scalar())
        today_sast = (await db.execute(text("SELECT (now() AT TIME ZONE 'Africa/Johannesburg')::date"))).scalar()
        today_utc = shipping._utc_today()
        out["today_sast"], out["today_utc"] = str(today_sast), str(today_utc)

        # --- 1. pairs, covered, partial (independent) ---
        r = (await db.execute(text(PAIRS_CTE + """
            SELECT kind, count(*) AS n, sum(open_qty) AS open_units, sum(shipped_qty) AS shipped_units,
                   sum(greatest(open_qty - shipped_qty, 0)) AS remainder
            FROM pairs GROUP BY kind ORDER BY kind"""))).mappings().all()
        out["indep_pairs_by_kind"] = {x["kind"]: {k: _f(v) for k, v in x.items() if k != "kind"} for x in r}

        partial = (await db.execute(text(PAIRS_CTE + """
            SELECT p.id, p.open_qty, p.shipped_qty, p.open_qty - p.shipped_qty AS remainder,
                   f.amount, f.currency_code, f.status, f.line_state, f.eta_date, f.pod_date, f.promise_date,
                   f.ship_confirm_date, f.distributor_id, f.product_id, f.purchase_order_id
            FROM pairs p JOIN fact_inbound_shipment f ON f.id = p.id
            WHERE p.kind = 'partial' ORDER BY p.id"""))).mappings().all()
        lines = []
        for p in partial:
            oq, rem = _f(p["open_qty"]), _f(p["remainder"])
            amt = None if p["amount"] is None else float(p["amount"])
            lines.append({
                "id": int(p["id"]), "open": oq, "shipped": _f(p["shipped_qty"]), "remainder": rem,
                "amount": amt, "pro_rata": None if amt is None or not oq else round(amt * rem / oq, 4),
                "currency": p["currency_code"], "status": p["status"],
                "eta_date": str(p["eta_date"]), "pod_date": str(p["pod_date"]),
                "promise_date": str(p["promise_date"]), "ship_confirm_date": str(p["ship_confirm_date"]),
                "has_dist": p["distributor_id"] is not None, "has_product": p["product_id"] is not None,
                "has_po": p["purchase_order_id"] is not None,
            })
        out["indep_partial_lines"] = lines
        out["indep_partial_count"] = len(lines)
        out["indep_partial_open"] = sum(x["open"] for x in lines)
        out["indep_partial_shipped"] = sum(x["shipped"] for x in lines)
        out["indep_partial_remainder"] = sum(x["remainder"] for x in lines)
        out["indep_partial_amount"] = round(sum(x["amount"] or 0 for x in lines), 4)
        out["indep_partial_pro_rata"] = round(sum(x["pro_rata"] or 0 for x in lines), 4)

        # Helper counted_amount / counted_quantity for the same ids (code under test).
        tw = twin_remainder(F)
        ids = [x["id"] for x in lines]
        hr = (await db.execute(
            select(F.id, tw.counted_quantity, tw.counted_amount).select_from(F)
            .outerjoin(tw.subquery, tw.onclause).where(F.id.in_(ids))
        )).all()
        helper = {int(i): (_f(q), None if a is None else round(float(a), 4)) for i, q, a in hr}
        out["helper_matches_indep_partial"] = all(
            helper.get(x["id"]) == (x["remainder"], x["pro_rata"]) for x in lines
        ) and len(helper) == len(lines)

        # Helper covered set vs independent covered set.
        hk = (await db.execute(
            select(func.count()).select_from(F).outerjoin(tw.subquery, tw.onclause)
            .where(~tw.kept)
        )).scalar()
        out["helper_not_kept_count"] = int(hk)
        cov_ids = [int(i) for i in (await db.execute(text(PAIRS_CTE + "SELECT id FROM pairs WHERE kind='covered'"))).scalars()]
        hk_ids = sorted(int(i) for i in (await db.execute(
            select(F.id).select_from(F).outerjoin(tw.subquery, tw.onclause).where(~tw.kept)
        )).scalars())
        out["helper_not_kept_equals_indep_covered"] = hk_ids == sorted(cov_ids)

        # --- edge checks ---
        out["edge_keys_with_more_than_one_open_twin_line"] = int((await db.execute(text(PAIRS_CTE + """
            SELECT count(*) FROM (SELECT tenant_id, ou, o, i FROM pairs GROUP BY 1,2,3,4 HAVING count(*) > 1) x"""))).scalar())
        out["edge_keys_with_more_than_one_shipped_twin"] = int((await db.execute(text(PAIRS_CTE + """
            SELECT count(DISTINCT (tenant_id, ou, o, i)) FROM pairs WHERE n_shipped > 1"""))).scalar())
        out["edge_negative_qty_rows"] = int((await db.execute(text(
            "SELECT count(*) FROM fact_inbound_shipment WHERE quantity < 0"))).scalar())
        out["edge_twin_open_qty_null_or_zero"] = int((await db.execute(text(PAIRS_CTE + """
            SELECT count(*) FROM pairs p JOIN fact_inbound_shipment f ON f.id = p.id
            WHERE f.quantity IS NULL OR f.quantity = 0"""))).scalar())
        out["edge_distinct_line_states"] = [
            (str(a), int(b)) for a, b in (await db.execute(text(
                "SELECT line_state, count(*) FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1"))).all()
        ]

        # --- 2. Unreceived past ETA / overdue / pipeline (independent, tenant default) ---
        indep = (await db.execute(text(PAIRS_CTE + """
            , cov AS (SELECT id FROM pairs WHERE kind = 'covered')
            , part AS (SELECT id, open_qty - shipped_qty AS rem FROM pairs WHERE kind = 'partial')
            SELECT
              count(*) FILTER (WHERE f.pod_date IS NULL AND f.eta_date IS NOT NULL AND f.eta_date < :ts) AS eta_past_raw,
              count(*) FILTER (WHERE f.pod_date IS NULL AND f.eta_date IS NOT NULL AND f.eta_date < :ts
                               AND f.id NOT IN (SELECT id FROM cov)) AS eta_past_rule,
              min(f.eta_date) FILTER (WHERE f.pod_date IS NULL AND f.eta_date IS NOT NULL AND f.eta_date < :ts
                               AND f.id NOT IN (SELECT id FROM cov)) AS oldest_eta_past_rule,
              count(*) FILTER (WHERE f.status = 'scheduled' AND f.pod_date IS NULL AND f.promise_date IS NOT NULL
                               AND f.promise_date < :ts AND f.promise_date >= :ts - 180
                               AND f.eta_date IS NOT NULL AND f.eta_date >= :ts AND f.eta_date <= :ts + 90
                               AND f.id NOT IN (SELECT id FROM cov)) AS overdue_rule_sast,
              count(*) FILTER (WHERE f.status = 'scheduled' AND f.pod_date IS NULL AND f.promise_date IS NOT NULL
                               AND f.promise_date < :tu AND f.promise_date >= :tu - 180
                               AND f.eta_date IS NOT NULL AND f.eta_date >= :tu AND f.eta_date <= :tu + 90
                               AND f.id NOT IN (SELECT id FROM cov)) AS overdue_rule_utc,
              count(*) FILTER (WHERE f.status = 'scheduled' AND f.pod_date IS NULL AND f.promise_date IS NOT NULL
                               AND f.promise_date < :ts AND f.promise_date >= :ts - 180
                               AND f.eta_date IS NOT NULL AND f.eta_date >= :ts AND f.eta_date <= :ts + 90) AS overdue_raw_sast,
              count(*) FILTER (WHERE f.pod_date IS NULL AND f.line_state = 'open_order'
                               AND f.id NOT IN (SELECT id FROM cov)) AS pipeline_lines,
              sum(CASE WHEN part.id IS NOT NULL THEN part.rem ELSE f.quantity END)
                 FILTER (WHERE f.pod_date IS NULL AND f.line_state = 'open_order'
                         AND f.id NOT IN (SELECT id FROM cov)) AS pipeline_units,
              sum(f.quantity) FILTER (WHERE f.pod_date IS NULL AND f.line_state = 'open_order') AS pipeline_units_raw,
              count(*) FILTER (WHERE f.status IS DISTINCT FROM 'received' AND f.id NOT IN (SELECT id FROM cov)) AS open_lines,
              sum(CASE WHEN part.id IS NOT NULL THEN part.rem ELSE f.quantity END)
                 FILTER (WHERE f.status IS DISTINCT FROM 'received' AND f.id NOT IN (SELECT id FROM cov)) AS open_units
            FROM fact_inbound_shipment f
            LEFT JOIN part ON part.id = f.id
            WHERE f.tenant_id = 'default'
        """), {"ts": today_sast, "tu": today_utc})).mappings().one()
        out["indep_headline"] = {k: (str(v) if k.startswith("oldest") else _f(v)) for k, v in indep.items()}

        # Channel ops inbound_open per (dist, product), independent.
        co = (await db.execute(text(PAIRS_CTE + """
            , cov AS (SELECT id FROM pairs WHERE kind = 'covered')
            , part AS (SELECT id, open_qty - shipped_qty AS rem FROM pairs WHERE kind = 'partial')
            SELECT f.distributor_id, f.product_id,
                   sum(CASE WHEN part.id IS NOT NULL THEN part.rem ELSE coalesce(f.quantity, 0) END) AS q,
                   sum(CASE WHEN f.line_state = 'open_order' THEN
                         CASE WHEN part.id IS NOT NULL THEN part.rem ELSE coalesce(f.quantity, 0) END END) AS q_open
            FROM fact_inbound_shipment f LEFT JOIN part ON part.id = f.id
            WHERE f.tenant_id = 'default' AND f.pod_date IS NULL
              AND f.distributor_id IS NOT NULL AND f.product_id IS NOT NULL
              AND f.id NOT IN (SELECT id FROM cov)
            GROUP BY 1, 2"""))).all()
        indep_co = {(int(d), int(p)): _f(q) for d, p, q, _qo in co}
        out["indep_channel_inbound_open_total"] = round(sum(indep_co.values()), 4)
        out["indep_channel_inbound_open_open_order_part"] = round(sum(_f(qo) for *_x, qo in co), 4)
        miss = (await db.execute(text(PAIRS_CTE + """
            , cov AS (SELECT id FROM pairs WHERE kind = 'covered')
            , part AS (SELECT id, open_qty - shipped_qty AS rem FROM pairs WHERE kind = 'partial')
            SELECT sum(CASE WHEN part.id IS NOT NULL THEN part.rem ELSE coalesce(f.quantity, 0) END)
            FROM fact_inbound_shipment f LEFT JOIN part ON part.id = f.id
            WHERE f.tenant_id = 'default' AND f.pod_date IS NULL AND f.line_state = 'open_order'
              AND (f.distributor_id IS NULL OR f.product_id IS NULL)
              AND f.id NOT IN (SELECT id FROM cov)"""))).scalar()
        out["indep_pipeline_units_without_dist_or_product"] = _f(miss)

        # --- 3. real readers ---
        t = time.perf_counter()
        so = await supply_overview(db, None)
        out["supply_overview_s"] = round(time.perf_counter() - t, 2)
        out["supply_overview"] = {k: (str(so.get(k)) if "eta_past" in k and "lines" not in k else so.get(k)) for k in (
            "open_lines", "open_units", "eta_past_no_pod_lines", "oldest_eta_past", "oldest_days_past_eta",
            "overdue_commercial_lines", "pipeline_lines", "pipeline_units", "shipped_units", "arrived_units")}

        t = time.perf_counter()
        ov_cur, ov_qty, ov_lines = await shipping._aggregate_currency_qty_lines(
            db, {"tenant_id": "default"}, predicate_overdue(today_utc)
        )
        out["shipping_kpi_overdue"] = {"lines": ov_lines, "qty": ov_qty, "by_currency": ov_cur,
                                       "s": round(time.perf_counter() - t, 2)}

        t = time.perf_counter()
        cd = await channel_ops.channel_ops_cover_distribution(db=db, user=None)
        out["channel_cover_s"] = round(time.perf_counter() - t, 2)
        items = cd.get("items") or []
        mism = []
        for it in items:
            key = (int(it["distributor_id"]), int(it["product_id"]))
            got = _f(it.get("inbound_open"))
            exp = indep_co.get(key, 0.0)
            if abs(got - exp) > 1e-6:
                mism.append({"pair": f"{key[0]}-{key[1]}", "channel_ops": got, "indep": exp})
        out["channel_cover_items"] = len(items)
        out["channel_cover_inbound_open_items_total"] = round(sum(_f(i.get("inbound_open")) for i in items), 4)
        out["channel_cover_items_mismatch_vs_indep"] = mism[:20]
        out["channel_cover_items_mismatch_count"] = len(mism)

        # Grid "Still to ship" for the 10 partial lines (real helper).
        sts = await shipping._still_to_ship_by_id(db, [SimpleNamespace(id=i, line_state="open_order") for i in ids])
        out["grid_still_to_ship_equals_indep_remainder"] = all(
            _f(sts.get(x["id"])) == x["remainder"] for x in lines
        )

        # --- 4. no fact write ---
        nw = (await db.execute(text("""
            SELECT count(*) AS n, max(updated_at) AS max_upd, max(created_at) AS max_crt,
                   count(*) FILTER (WHERE updated_at >= now() - interval '36 hours') AS upd_36h,
                   count(*) FILTER (WHERE created_at >= now() - interval '36 hours') AS crt_36h
            FROM fact_inbound_shipment"""))).mappings().one()
        out["no_write"] = {k: str(v) for k, v in nw.items()}
        st = (await db.execute(text(
            "SELECT n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables WHERE relname = 'fact_inbound_shipment'"
        ))).mappings().first()
        out["pg_stat_fact_inbound_shipment"] = dict(st) if st else None

        out["transaction_read_only_at_end"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["current_database_at_end"] = (await db.execute(text("SELECT current_database()"))).scalar()
        await db.rollback()
    await engine.dispose()
    txt = json.dumps(out, indent=2, default=str)
    if OUT:
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write(txt)
    print(txt)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
