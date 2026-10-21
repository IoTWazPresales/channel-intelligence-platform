"""N-0071 round 2 read-only probe (RUN-20261007-N0071-IMPL).

Read-only: SET TRANSACTION READ ONLY, prints current_database() first, rolls back.
Calls the real reader functions (supply overview, brief count, /summary, overdue KPI)
and an independent self-join for the partial-ship pairs (D-0065).
Usage: python N0071_r2_probe.py <label>   (writes N0071_r2_probe_<label>_out.json next to it)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services import shipment_strict_pair as ssp
from app.services.shipping_commercial_kpis import predicate_overdue

LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
OUT = Path(__file__).with_name(f"N0071_r2_probe_{LABEL}_out.json")

INDEPENDENT_PAIRS = """
WITH s AS (
  SELECT tenant_id, lower(btrim(coalesce(operating_unit,''))) ou, lower(btrim(order_no)) o,
         lower(btrim(item_code)) i, coalesce(sum(quantity),0) shipped_qty, count(*) n_shipped
  FROM fact_inbound_shipment
  WHERE lower(line_state)='shipped' AND order_no IS NOT NULL AND item_code IS NOT NULL
  GROUP BY 1,2,3,4
)
SELECT f.id, f.quantity, s.shipped_qty, s.n_shipped, f.status, f.eta_date, f.promise_date, f.pod_date,
       f.amount, f.currency_code
FROM fact_inbound_shipment f
JOIN s ON s.tenant_id=f.tenant_id AND s.ou=lower(btrim(coalesce(f.operating_unit,'')))
      AND s.o=lower(btrim(f.order_no)) AND s.i=lower(btrim(f.item_code))
WHERE lower(f.line_state)='open_order' AND btrim(coalesce(f.order_no,''))<>'' AND btrim(coalesce(f.item_code,''))<>''
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


async def _after_only(db, out: dict, partial: list[dict], today) -> None:
    """Readers only present after round 2: helper vs independent remainder, per-reader timings."""
    from app.api.v1.endpoints import shipping
    from app.services.commercial_planner.inbound_lineup_quarter import lineup_quarter_summary
    from app.services.cpor.intake_weighted_mac import _disti_cost_proxy_wavg, _intake_wavg
    from app.services.shipping_commercial_kpis import predicate_current_incoming

    stmt, twin = ssp.outerjoin_twin_remainder(select(F.id, F.quantity), F)
    stmt = stmt.add_columns(twin.counted_quantity).where(twin.is_partial_twin)
    res = await _timed(out, "helper_partial", db.execute(stmt))
    helper = sorted((int(i), float(q or 0), float(c or 0)) for i, q, c in res.all())
    indep = sorted(
        (int(p["id"]), float(p["quantity"] or 0), float(p["quantity"] or 0) - float(p["shipped_qty"] or 0))
        for p in partial
    )
    out["helper_partial_lines"] = len(helper)
    out["helper_partial_remainder_units"] = sum(h[2] for h in helper)
    out["helper_equals_independent_partial"] = helper == indep

    res = await _timed(
        out,
        "keep_counted_line_count",
        db.execute(select(func.count()).select_from(F).where(F.tenant_id == "default", ssp.keep_counted_line(F))),
    )
    out["keep_counted_line_count"] = res.scalar() if res is not None else None

    agg = await _timed(
        out, "kpi_current_incoming", shipping._aggregate_currency_qty_lines(db, {}, predicate_current_incoming(today))
    )
    if agg is not None:
        out["kpi_current_incoming"] = {"qty": agg[1], "lines": agg[2], "by_currency": agg[0]}
    agg = await _timed(out, "kpi_overdue", shipping._aggregate_currency_qty_lines(db, {}, predicate_overdue(today)))
    if agg is not None:
        out["kpi_overdue"] = {"qty": agg[1], "lines": agg[2]}

    shifts = await _timed(
        out, "eta_shift_scope", shipping._eta_shift_metrics(db, sample_limit=0, require_current_incoming=True, today=today)
    )
    if shifts is not None:
        out["eta_shift_slipped_count"] = shifts.get("slipped_count")

    for pq in ("26Q2", "26Q3", "26Q4"):
        summ = await _timed(out, f"lineup_{pq}", lineup_quarter_summary(db, plan_quarter=pq))
        if summ is not None:
            out[f"lineup_{pq}"] = {
                k: summ.get(k) for k in ("pipeline_units", "shipped_units", "unattributed_units", "landed_units")
            }

    # Timing baseline: the same reader with the round-1 (D-0057) filter swapped in.
    import types

    from app.services.commercial_planner import inbound_lineup_quarter as ilq

    real = ilq.outerjoin_twin_remainder

    def _d0057(stmt, model):
        return stmt.where(ssp.exclude_open_when_shipped_twin(model)), types.SimpleNamespace(counted_quantity=model.quantity)

    ilq.outerjoin_twin_remainder = _d0057
    try:
        summ = await _timed(out, "lineup_26Q3_d0057_emulated", lineup_quarter_summary(db, plan_quarter="26Q3"))
        if summ is not None:
            out["lineup_26Q3_d0057_emulated"] = {
                k: summ.get(k) for k in ("pipeline_units", "shipped_units", "unattributed_units", "landed_units")
            }
    finally:
        ilq.outerjoin_twin_remainder = real

    pid_row = (
        await db.execute(
            select(F.product_id, func.coalesce(F.resolved_distributor_id, F.distributor_id))
            .where(F.id.in_([int(p["id"]) for p in partial]), F.purchase_order_id.is_not(None), F.product_id.is_not(None))
            .limit(1)
        )
    ).first()
    out["cpor_partial_lines_po_linked"] = pid_row is not None
    if pid_row is None:  # no partial line is PO-linked: time the reader on a PO-linked open twin instead
        twin_ids = select(F.id).where(func.lower(F.line_state) == "open_order", ~ssp.exclude_open_when_shipped_twin(F))
        pid_row = (
            await db.execute(
                select(F.product_id, func.coalesce(F.resolved_distributor_id, F.distributor_id))
                .where(
                    F.id.in_([int(i) for i in (await db.execute(twin_ids)).scalars().all()]),
                    F.purchase_order_id.is_not(None),
                    F.product_id.is_not(None),
                    F.unit_price > 0,
                )
                .limit(1)
            )
        ).first()
    if pid_row is not None:
        pid, did = int(pid_row[0]), (int(pid_row[1]) if pid_row[1] is not None else None)
        from datetime import date

        def _run(s):
            a = _intake_wavg(s, distributor_id=did, product_id=pid, window_start=date(2026, 1, 1), window_end=date(2026, 12, 31))
            b = _disti_cost_proxy_wavg(s, distributor_id=did, product_id=pid) if did is not None else None
            return a, b

        r = await _timed(out, "cpor_intake", db.run_sync(_run))
        if r is not None:
            (qty, wavg, _asof, _fl), b = r
            out["cpor_intake_sample"] = {
                "product_id": pid,
                "distributor_id": did,
                "intake_qty": float(qty),
                "intake_wavg": float(wavg) if wavg is not None else None,
                "disti_proxy_wavg": float(b[0]) if b and b[0] is not None else None,
            }


async def main() -> None:
    from app.api.v1.endpoints.shipping import shipping_evidence_summary
    from app.services.brief_signals import inbound_not_received_count_stmt
    from app.services.supply_overview import supply_overview

    engine = create_async_engine(_url())
    out: dict = {"label": LABEL, "probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()
        out["db_today_sast"] = str((await db.execute(text("SELECT (now() AT TIME ZONE 'Africa/Johannesburg')::date"))).scalar())

        rows = (await db.execute(text(INDEPENDENT_PAIRS))).mappings().all()
        pairs = [dict(r) for r in rows]
        partial = [p for p in pairs if float(p["quantity"] or 0) > float(p["shipped_qty"] or 0)]
        out["independent_pairs"] = len(pairs)
        out["independent_skipped"] = len(pairs) - len(partial)
        out["independent_partial_lines"] = len(partial)
        out["independent_partial_open_units"] = sum(float(p["quantity"] or 0) for p in partial)
        out["independent_partial_remainder_units"] = sum(
            float(p["quantity"] or 0) - float(p["shipped_qty"] or 0) for p in partial
        )
        out["independent_partial_multi_shipped_twins"] = sum(1 for p in partial if int(p["n_shipped"]) > 1)
        out["partial_lines"] = [
            {
                "id": int(p["id"]),
                "open_qty": float(p["quantity"] or 0),
                "shipped_total": float(p["shipped_qty"] or 0),
                "n_shipped": int(p["n_shipped"]),
                "status": p["status"],
                "eta_date": str(p["eta_date"]),
                "promise_date": str(p["promise_date"]),
                "pod_date": str(p["pod_date"]),
                "has_amount": p["amount"] is not None,
            }
            for p in partial
        ]

        t = time.perf_counter()
        so = await supply_overview(db, None)
        out["supply_overview_s"] = round(time.perf_counter() - t, 2)
        out["supply_overview"] = {
            k: so.get(k)
            for k in (
                "data_unavailable",
                "open_lines",
                "open_units",
                "eta_past_no_pod_lines",
                "oldest_eta_past",
                "oldest_days_past_eta",
                "pipeline_lines",
                "pipeline_units",
                "shipped_lines",
                "shipped_units",
                "landed_lines",
                "landed_units",
                "arrived_lines",
                "overdue_commercial_lines",
            )
        }

        t = time.perf_counter()
        out["brief_not_received"] = (await db.execute(inbound_not_received_count_stmt(None))).scalar()
        out["brief_s"] = round(time.perf_counter() - t, 2)

        t = time.perf_counter()
        summ = await shipping_evidence_summary(db=db, user=None)
        out["summary_s"] = round(time.perf_counter() - t, 2)
        out["summary"] = {
            "total_lines": summ["total_lines"],
            "open_lines_skipped_shipped_twin": summ["open_lines_skipped_shipped_twin"],
            "by_line_state": summ["by_line_state"],
        }

        today = datetime.now(timezone.utc).date()
        keep = getattr(ssp, "keep_counted_line", None) or ssp.exclude_open_when_shipped_twin
        t = time.perf_counter()
        out["shipping_overdue_kpi_lines"] = (
            await db.execute(
                select(func.count()).select_from(F).where(F.tenant_id == "default", predicate_overdue(today), keep(F))
            )
        ).scalar()
        out["shipping_overdue_kpi_s"] = round(time.perf_counter() - t, 2)

        if hasattr(ssp, "twin_remainder"):
            await _after_only(db, out, partial, today)
        await db.rollback()
    await engine.dispose()
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "partial_lines"}, indent=2, default=str))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
