"""N-0071 round 3 read-only probe (RUN-20261007-N0071-IMPL).

Read-only: SET TRANSACTION READ ONLY, prints current_database() first, rolls back.
Calls the real readers moved in round 3 (channel ops movement / weekly flow / cover
distribution, net-requirement in-transit, PO auto-link, PO reconciliation, 1H hint) plus
supply overview, and computes the 10 partial lines independently (remainder, pro-rata value).
Usage: python N0071_r3_probe.py <label>   (writes N0071_r3_probe_<label>_out.json next to it)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services import shipment_strict_pair as ssp

LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
OUT = Path(__file__).with_name(f"N0071_r3_probe_{LABEL}_out.json")

# Independent of the helper: grouped shipped totals per strict key, joined to open rows.
INDEPENDENT_PARTIAL = """
WITH s AS (
  SELECT tenant_id, lower(btrim(coalesce(operating_unit,''))) ou, lower(btrim(order_no)) o,
         lower(btrim(item_code)) i, coalesce(sum(quantity),0) shipped_qty, count(*) n_shipped
  FROM fact_inbound_shipment
  WHERE lower(line_state)='shipped' AND order_no IS NOT NULL AND item_code IS NOT NULL
  GROUP BY 1,2,3,4
)
SELECT f.id, f.quantity, s.shipped_qty, f.amount, f.currency_code, f.unit_price, f.status,
       f.ship_confirm_date, f.pod_date, f.purchase_order_id, f.product_id,
       coalesce(f.resolved_distributor_id, f.distributor_id) AS dist_id
FROM fact_inbound_shipment f
JOIN s ON s.tenant_id=f.tenant_id AND s.ou=lower(btrim(coalesce(f.operating_unit,'')))
      AND s.o=lower(btrim(f.order_no)) AND s.i=lower(btrim(f.item_code))
WHERE lower(f.line_state)='open_order' AND btrim(coalesce(f.order_no,''))<>'' AND btrim(coalesce(f.item_code,''))<>''
  AND coalesce(f.quantity,0) > s.shipped_qty
ORDER BY f.id
"""


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


async def _timed(out: dict, key: str, coro):
    t = time.perf_counter()
    try:
        val = await coro
    except Exception as exc:  # report, keep probing
        out[key + "_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        val = None
    out[key + "_s"] = round(time.perf_counter() - t, 2)
    return val


def _f(x) -> float:
    return float(x or 0)


async def main() -> None:
    from app.api.v1.endpoints import channel_ops
    from app.services.commercial_planner.lineup_bulk_rederivation import _shipment_q1_hint
    from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals
    from app.services.commercial_planner.lineup_po_reconciliation import reconcile_case
    from app.services.lineup.net_requirement import _in_transit_by_dist_product
    from app.services.supply_overview import supply_overview

    engine = create_async_engine(_url())
    out: dict = {"label": LABEL, "probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()
        out["helper_has_counted_amount"] = "counted_amount" in getattr(ssp.TwinRemainder, "__dataclass_fields__", {})

        partial = [dict(r) for r in (await db.execute(text(INDEPENDENT_PARTIAL))).mappings().all()]
        out["independent_partial_lines"] = len(partial)
        out["independent_partial_open_units"] = sum(_f(p["quantity"]) for p in partial)
        out["independent_partial_remainder_units"] = sum(_f(p["quantity"]) - _f(p["shipped_qty"]) for p in partial)
        out["independent_partial_po_linked"] = sum(1 for p in partial if p["purchase_order_id"] is not None)
        out["independent_partial_with_ship_confirm_or_pod"] = sum(
            1 for p in partial if p["ship_confirm_date"] is not None or p["pod_date"] is not None
        )
        lines = []
        for p in partial:
            open_q, rem = _f(p["quantity"]), _f(p["quantity"]) - _f(p["shipped_qty"])
            amt = None if p["amount"] is None else float(p["amount"])
            lines.append(
                {
                    "id": int(p["id"]),
                    "open_qty": open_q,
                    "shipped_total": _f(p["shipped_qty"]),
                    "remainder": rem,
                    "currency": p["currency_code"],
                    "amount_stored": amt,
                    "amount_pro_rata": None if amt is None or not open_q else round(amt * rem / open_q, 4),
                    "status": p["status"],
                    "dist_id": p["dist_id"],
                    "product_id": p["product_id"],
                }
            )
        out["partial_lines"] = lines
        by_ccy: dict[str, dict[str, float]] = {}
        for ln in lines:
            b = by_ccy.setdefault(str(ln["currency"]), {"stored": 0.0, "pro_rata": 0.0})
            b["stored"] += ln["amount_stored"] or 0.0
            b["pro_rata"] += ln["amount_pro_rata"] or 0.0
        out["independent_partial_value_by_currency"] = {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in by_ccy.items()}
        partial_pairs = {(int(p["dist_id"]), int(p["product_id"])) for p in partial if p["dist_id"] and p["product_id"]}
        partial_rem_by_pair: dict[tuple[int, int], float] = {}
        for p in partial:
            if p["dist_id"] and p["product_id"]:
                k = (int(p["dist_id"]), int(p["product_id"]))
                partial_rem_by_pair[k] = partial_rem_by_pair.get(k, 0.0) + _f(p["quantity"]) - _f(p["shipped_qty"])

        # Helper's pro-rata (after only)
        if out["helper_has_counted_amount"]:
            stmt, twin = ssp.outerjoin_twin_remainder(select(F.id), F)
            stmt = stmt.add_columns(twin.counted_quantity, twin.counted_amount).where(twin.is_partial_twin)
            res = await _timed(out, "helper_partial_value", db.execute(stmt))
            helper = {int(i): (float(q or 0), None if a is None else round(float(a), 4)) for i, q, a in res.all()}
            indep = {ln["id"]: (ln["remainder"], ln["amount_pro_rata"]) for ln in lines}
            out["helper_pro_rata_equals_independent"] = helper == indep
            out["helper_partial_value_total"] = round(sum(a or 0 for _q, a in helper.values()), 4)

            # Value of every kept open line by currency: pro-rata (now), round 2 (partial = 0), stored.
            from sqlalchemy import case

            stmt, twin = ssp.outerjoin_twin_remainder(select(F.currency_code), F)
            stmt = (
                stmt.add_columns(
                    func.sum(twin.counted_amount),
                    func.sum(case((twin.is_partial_twin, None), else_=F.amount)),
                    func.sum(F.amount),
                )
                .where(func.lower(F.line_state) == "open_order", F.tenant_id == "default")
                .group_by(F.currency_code)
            )
            res = await _timed(out, "open_value", db.execute(stmt))
            out["open_value_by_currency"] = {
                str(c): {"pro_rata": float(a or 0), "round2_partial_zero": float(b or 0), "stored": float(s or 0)}
                for c, a, b, s in res.all()
            }

            from app.api.v1.endpoints import shipping
            from app.services.shipping_commercial_kpis import predicate_current_incoming, predicate_overdue

            today = datetime.now(timezone.utc).date()
            for key, pred in (("kpi_current_incoming", predicate_current_incoming(today)), ("kpi_overdue", predicate_overdue(today))):
                agg = await _timed(out, key, shipping._aggregate_currency_qty_lines(db, {}, pred))
                if agg is not None:
                    out[key] = {"qty": agg[1], "lines": agg[2], "by_currency": agg[0]}

            rows = (await db.execute(select(F).where(F.id.in_([ln["id"] for ln in lines])))).scalars().all()
            sts = await _timed(out, "grid_still_to_ship", shipping._still_to_ship_by_id(db, list(rows)))
            if sts is not None:
                out["grid_still_to_ship_partial"] = {str(k): v for k, v in sorted(sts.items())}
                out["grid_still_to_ship_equals_remainder"] = all(
                    sts.get(ln["id"]) == ln["remainder"] for ln in lines
                )

        # Supply overview pipeline (D-0065 since round 2): the reference screen.
        so = await _timed(out, "supply_overview", supply_overview(db, None))
        if so is not None:
            out["supply_overview"] = {k: so.get(k) for k in ("open_units", "pipeline_lines", "pipeline_units")}

        # Channel ops: movement lens, weekly flow, cover distribution.
        mv = await _timed(out, "channel_movement", channel_ops.channel_ops_movement_lens(db=db, user=None, weeks=13))
        if mv is not None:
            out["channel_movement_shipped_units"] = mv["headlines"]["shipped_units"]
            out["channel_movement_shipped_week"] = mv["headlines"]["shipped_week"]
        wf = await _timed(out, "channel_weekly_flow", channel_ops._cover_weekly_flow(db, "default"))
        if wf is not None:
            out["channel_weekly_flow_shipped_total"] = sum(_f(p["shipped"]) for p in wf["points"])
        cd = await _timed(out, "channel_cover", channel_ops.channel_ops_cover_distribution(db=db, user=None))
        if cd is not None:
            items = cd.get("items") or []
            out["channel_cover_items"] = len(items)
            out["channel_cover_inbound_open_total"] = round(sum(_f(i.get("inbound_open")) for i in items), 4)
            out["channel_cover_inbound_open_partial_pairs"] = {
                f"{i['distributor_id']}-{i['product_id']}": _f(i.get("inbound_open"))
                for i in items
                if (int(i["distributor_id"]), int(i["product_id"])) in partial_pairs
            }

        # Net requirement in-transit (PO-linked only).
        tr = await _timed(out, "net_req_in_transit", _in_transit_by_dist_product(db))
        if tr is not None:
            out["net_req_in_transit_total"] = round(sum(tr.values()), 4)
            out["net_req_in_transit_pairs"] = len(tr)
            out["net_req_in_transit_partial_pairs"] = {f"{d}-{p}": tr.get((d, p)) for d, p in sorted(partial_pairs)}

        # PO auto-link proposals and PO reconciliation (PO-linked only).
        al = await _timed(out, "po_auto_link", po_auto_link_proposals(db, limit=0))
        if al is not None:
            out["po_auto_link_data_unavailable"] = al.get("data_unavailable")
            out["po_auto_link_total"] = al.get("total")
            props = al.get("proposals") or []
            out["po_auto_link_open_order_units"] = round(sum(_f(p.get("total_open_order_units")) for p in props), 4)
            out["po_auto_link_shipped_units"] = round(sum(_f(p.get("total_shipped_units")) for p in props), 4)
        case_rows = (
            await db.execute(
                text(
                    "SELECT case_id, count(*) FROM commercial_lineup_case_po GROUP BY case_id ORDER BY 2 DESC, 1 LIMIT 3"
                )
            )
        ).all()
        recon = {}
        for cid, _n in case_rows:
            rc = await _timed(out, f"recon_{cid}", reconcile_case(db, int(cid)))
            if rc is not None:
                recon[str(cid)] = {
                    "data_unavailable": rc.get("data_unavailable", False),
                    "pipeline_units": round(sum(_f(p.get("pipeline_units")) for p in rc.get("products") or []), 4),
                }
        out["po_reconciliation"] = recon

        # 1H hint for the partial products (ship_confirm_date window), via the sync session.
        prods = sorted({int(p["product_id"]) for p in partial if p["product_id"]})

        def _hints(s):
            return {pid: _shipment_q1_hint(s, product_id=pid, customer_id=None, q1_start=date(2026, 1, 1), q2_start=date(2027, 1, 1)) for pid in prods}

        h = await _timed(out, "hint_1h", db.run_sync(_hints))
        if h is not None:
            out["hint_1h_partial_products"] = {str(k): v for k, v in h.items()}

        await db.rollback()
    await engine.dispose()
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "partial_lines"}, indent=2, default=str))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
