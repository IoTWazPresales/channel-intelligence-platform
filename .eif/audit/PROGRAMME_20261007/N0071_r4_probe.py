"""N-0071 round 4 read-only probe (RUN-20261007-N0071-IMPL): suggested-PO / suggested-distributor shipped units.

Read-only: SET TRANSACTION READ ONLY (and default_transaction_read_only=on), prints current_database()
first, rolls back. Calls the real readers ``suggest_pos_for_case`` and ``suggest_distributors_for_case``
for every lineup case, totals ``total_shipped_units``, and checks each value against an independent
shipped-only and all-states SUM over the evidence read model. No secret printed.
Usage: python N0071_r4_probe.py <label>   (writes N0071_r4_probe_<label>_out.json next to it)
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

LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
OUT = Path(__file__).with_name(f"N0071_r4_probe_{LABEL}_out.json")
EV = mod.EV


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


async def _indep_po(db, po_id: int, product_ids: list[int]) -> tuple[float, float]:
    """(shipped-only, all-states) units of one PO over the case products, written independently."""
    q = apply_active_evidence_filter(
        select(
            func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0),
            func.coalesce(func.sum(EV.quantity), 0),
        ).where(EV.purchase_order_id == po_id, EV.product_id.in_(product_ids)),
        model=EV,
    )
    s, a = (await db.execute(q)).one()
    return float(s), float(a)


async def _indep_dist(db, dist_id: int, product_ids: list[int]) -> tuple[float, float]:
    q = apply_active_evidence_filter(
        select(
            func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0),
            func.coalesce(func.sum(EV.quantity), 0),
        )
        .select_from(EV)
        .join(PurchaseOrder, PurchaseOrder.id == EV.purchase_order_id)
        .where(PurchaseOrder.distributor_id == dist_id, EV.product_id.in_(product_ids)),
        model=EV,
    )
    s, a = (await db.execute(q)).one()
    return float(s), float(a)


async def main() -> None:
    engine = create_async_engine(_url(), connect_args={"options": "-c default_transaction_read_only=on"})
    out: dict = {"label": LABEL, "probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()
        out["evidence_model"] = EV.__tablename__
        out["line_states"] = {
            str(s): int(n)
            for s, n in (await db.execute(select(EV.line_state, func.count()).group_by(EV.line_state))).all()
        }
        case_ids = [int(i) for i in (await db.execute(select(CommercialLineupCase.id).order_by(CommercialLineupCase.id))).scalars().all()]
        out["cases"] = len(case_ids)

        po = {"cases_with_suggestions": 0, "suggestions": 0, "total_shipped_units": 0.0,
              "indep_shipped_only": 0.0, "indep_all_states": 0.0, "rows_equal_shipped_only": 0,
              "rows_equal_all_states": 0, "rows_zero_shipped": 0, "mismatch_examples": []}
        dist = {"cases_with_suggestions": 0, "suggestions": 0, "total_shipped_units": 0.0,
                "indep_shipped_only": 0.0, "indep_all_states": 0.0, "rows_equal_shipped_only": 0,
                "rows_equal_all_states": 0, "order_follows_matched_then_units": True,
                "cases_with_order_change_vs_all_states": 0, "mismatch_examples": []}
        t0 = time.perf_counter()
        for cid in case_ids:
            pids = sorted({
                int(p) for p in (await db.execute(
                    select(CommercialLineupLine.product_id).where(
                        CommercialLineupLine.case_id == cid, CommercialLineupLine.product_id.isnot(None)
                    ).distinct()
                )).scalars().all()
            })
            res = await mod.suggest_pos_for_case(db, cid)
            if res["suggestions"]:
                po["cases_with_suggestions"] += 1
            for s in res["suggestions"]:
                po["suggestions"] += 1
                po["total_shipped_units"] += s["total_shipped_units"]
                si, ai = await _indep_po(db, s["purchase_order_id"], pids)
                po["indep_shipped_only"] += si
                po["indep_all_states"] += ai
                po["rows_equal_shipped_only"] += int(abs(s["total_shipped_units"] - si) < 1e-6)
                po["rows_equal_all_states"] += int(abs(s["total_shipped_units"] - ai) < 1e-6)
                po["rows_zero_shipped"] += int(s["total_shipped_units"] == 0)
                if abs(s["total_shipped_units"] - si) >= 1e-6 and len(po["mismatch_examples"]) < 5:
                    po["mismatch_examples"].append({"case": cid, "po": s["purchase_order_id"],
                                                    "reader": s["total_shipped_units"], "shipped_only": si, "all_states": ai})
            dres = await mod.suggest_distributors_for_case(db, cid)
            rows = dres["suggested_distributors"]
            if rows:
                dist["cases_with_suggestions"] += 1
            alt = []
            for d in rows:
                dist["suggestions"] += 1
                dist["total_shipped_units"] += d["total_shipped_units"]
                si, ai = await _indep_dist(db, d["distributor_id"], pids)
                dist["indep_shipped_only"] += si
                dist["indep_all_states"] += ai
                dist["rows_equal_shipped_only"] += int(abs(d["total_shipped_units"] - si) < 1e-6)
                dist["rows_equal_all_states"] += int(abs(d["total_shipped_units"] - ai) < 1e-6)
                alt.append((d["matched_product_count"], ai, d["distributor_id"]))
                if abs(d["total_shipped_units"] - si) >= 1e-6 and len(dist["mismatch_examples"]) < 5:
                    dist["mismatch_examples"].append({"case": cid, "distributor": d["distributor_id"],
                                                      "reader": d["total_shipped_units"], "shipped_only": si, "all_states": ai})
            keys = [(d["matched_product_count"], d["total_shipped_units"]) for d in rows]
            if keys != sorted(keys, key=lambda k: (-k[0], -k[1])):
                dist["order_follows_matched_then_units"] = False
            # Would the all-states key order these distributors differently? (strict order changes only)
            alt_order = [x[2] for x in sorted(alt, key=lambda k: (-k[0], -k[1]))]
            cur_order = [d["distributor_id"] for d in rows]
            if len(rows) > 1 and alt_order != cur_order and len({(x[0], x[1]) for x in alt}) == len(alt):
                dist["cases_with_order_change_vs_all_states"] += 1
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
