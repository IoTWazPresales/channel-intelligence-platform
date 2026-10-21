"""N-0071 round 4 read-only probe 2 (RUN-20261007-N0071-IMPL): suggested-PO / suggested-distributor shipped units.

Read-only: SET TRANSACTION READ ONLY (and default_transaction_read_only=on), prints current_database()
first, rolls back. Calls the real readers ``suggest_pos_for_case`` and ``suggest_distributors_for_case``
for every lineup case, totals ``total_shipped_units``, and checks each value against an independent
shipped-only and all-states SUM over the evidence read model (one grouped query per case, by PO and by
distributor). No secret printed.

Usage: python N0071_r4_probe2.py <label> [pre]   (writes N0071_r4_probe2_<label>_out.json next to it)
``pre`` replaces ``_shipped_units_sum`` in memory with the pre-fix all-states SUM (the only expression the
fix changed), so the real readers give the before figure; the service file is not touched.
(N0071_r4_probe.py is the first version: one independent query per suggestion, too slow on cip.)
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
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner import lineup_case_suggested_pos as mod
from app.services.imports.shipment_evidence_read import apply_active_evidence_filter

ARGS = sys.argv[1:]
LABEL = ARGS[0] if ARGS else "run"
PRE = "pre" in ARGS[1:]
OUT = Path(__file__).with_name(f"N0071_r4_probe2_{LABEL}_out.json")
EV = mod.EV
if PRE:
    mod._shipped_units_sum = lambda: func.coalesce(func.sum(mod.EV.quantity), 0)


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


async def _indep_by_po(db, product_ids: list[int]) -> dict:
    """po_id -> (shipped-only, all-states) over the case products, written independently."""
    q = apply_active_evidence_filter(
        select(
            EV.purchase_order_id,
            func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0),
            func.coalesce(func.sum(EV.quantity), 0),
        )
        .where(EV.purchase_order_id.isnot(None), EV.product_id.in_(product_ids))
        .group_by(EV.purchase_order_id),
        model=EV,
    )
    return {int(p): (float(s), float(a)) for p, s, a in (await db.execute(q)).all()}


async def _indep_by_dist(db, product_ids: list[int]) -> dict:
    q = apply_active_evidence_filter(
        select(
            PurchaseOrder.distributor_id,
            func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0),
            func.coalesce(func.sum(EV.quantity), 0),
        )
        .select_from(EV)
        .join(PurchaseOrder, PurchaseOrder.id == EV.purchase_order_id)
        .where(PurchaseOrder.distributor_id.isnot(None), EV.product_id.in_(product_ids))
        .group_by(PurchaseOrder.distributor_id),
        model=EV,
    )
    return {int(d): (float(s), float(a)) for d, s, a in (await db.execute(q)).all()}


def _blank() -> dict:
    return {"cases_with_suggestions": 0, "suggestions": 0, "total_shipped_units": 0.0,
            "indep_shipped_only": 0.0, "indep_all_states": 0.0, "rows_equal_shipped_only": 0,
            "rows_equal_all_states": 0, "rows_zero_shipped": 0, "mismatch_vs_shipped_only_examples": []}


async def main() -> None:
    engine = create_async_engine(_url(), connect_args={"options": "-c default_transaction_read_only=on"})
    out: dict = {"label": LABEL, "pre_fix_expression_in_memory": PRE,
                 "probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()
        out["evidence_model"] = EV.__tablename__
        case_ids = [int(i) for i in (await db.execute(
            select(CommercialLineupCase.id).order_by(CommercialLineupCase.id))).scalars().all()]
        out["cases"] = len(case_ids)
        po, dist = _blank(), _blank()
        dist["order_follows_matched_then_units"] = True
        dist["cases_where_all_states_key_orders_differently"] = 0
        t0 = time.perf_counter()
        for cid in case_ids:
            pids = sorted({
                int(p) for p in (await db.execute(
                    select(CommercialLineupLine.product_id).where(
                        CommercialLineupLine.case_id == cid, CommercialLineupLine.product_id.isnot(None)
                    ).distinct()
                )).scalars().all()
            })
            ipo = await _indep_by_po(db, pids) if pids else {}
            idist = await _indep_by_dist(db, pids) if pids else {}
            res = await mod.suggest_pos_for_case(db, cid)
            if res["suggestions"]:
                po["cases_with_suggestions"] += 1
            for s in res["suggestions"]:
                v = s["total_shipped_units"]
                si, ai = ipo.get(s["purchase_order_id"], (0.0, 0.0))
                po["suggestions"] += 1
                po["total_shipped_units"] += v
                po["indep_shipped_only"] += si
                po["indep_all_states"] += ai
                po["rows_equal_shipped_only"] += int(abs(v - si) < 1e-6)
                po["rows_equal_all_states"] += int(abs(v - ai) < 1e-6)
                po["rows_zero_shipped"] += int(v == 0)
                if abs(v - si) >= 1e-6 and len(po["mismatch_vs_shipped_only_examples"]) < 5:
                    po["mismatch_vs_shipped_only_examples"].append(
                        {"case": cid, "po": s["purchase_order_id"], "reader": v, "shipped_only": si, "all_states": ai})
            rows = (await mod.suggest_distributors_for_case(db, cid))["suggested_distributors"]
            if rows:
                dist["cases_with_suggestions"] += 1
            alt = []
            for d in rows:
                v = d["total_shipped_units"]
                si, ai = idist.get(d["distributor_id"], (0.0, 0.0))
                dist["suggestions"] += 1
                dist["total_shipped_units"] += v
                dist["indep_shipped_only"] += si
                dist["indep_all_states"] += ai
                dist["rows_equal_shipped_only"] += int(abs(v - si) < 1e-6)
                dist["rows_equal_all_states"] += int(abs(v - ai) < 1e-6)
                dist["rows_zero_shipped"] += int(v == 0)
                alt.append((d["matched_product_count"], si, ai, d["distributor_id"]))
                if abs(v - si) >= 1e-6 and len(dist["mismatch_vs_shipped_only_examples"]) < 5:
                    dist["mismatch_vs_shipped_only_examples"].append(
                        {"case": cid, "distributor": d["distributor_id"], "reader": v, "shipped_only": si, "all_states": ai})
            keys = [(d["matched_product_count"], d["total_shipped_units"]) for d in rows]
            if keys != sorted(keys, key=lambda k: (-k[0], -k[1])):
                dist["order_follows_matched_then_units"] = False
            if len(alt) > 1:
                by_ship = [x[3] for x in sorted(alt, key=lambda k: (-k[0], -k[1], k[3]))]
                by_all = [x[3] for x in sorted(alt, key=lambda k: (-k[0], -k[2], k[3]))]
                if by_ship != by_all:
                    dist["cases_where_all_states_key_orders_differently"] += 1
        out["elapsed_s"] = round(time.perf_counter() - t0, 2)
        for d in (po, dist):
            for k in ("total_shipped_units", "indep_shipped_only", "indep_all_states"):
                d[k] = round(d[k], 4)
        out["suggest_pos"] = po
        out["suggest_distributors"] = dist
        await db.rollback()
    await engine.dispose()
    txt = json.dumps(out, indent=2, default=str)
    OUT.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
