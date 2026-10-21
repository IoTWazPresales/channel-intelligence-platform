"""GOV-008 RUN-20261008-N0071-VER3: read-only cip probe for N-0071 round 4 (suggested POs / distributors).

Read-only: connection option default_transaction_read_only=on, SET TRANSACTION READ ONLY,
statement_timeout 60s, prints current_database() first, rolls back. No secret printed. No DML.

Independent formulation: ONE set-based raw-SQL query over every lineup case (case products joined to
the evidence relation, GROUP BY case and PO / case and distributor), shipped-only written as
lower(btrim(line_state)) = 'shipped' (the PO auto-link normalisation), not the ORM expression under test.
The real readers are then called for a SAMPLE of cases only and compared row by row.

Usage (from apps/api): .venv/Scripts/python.exe <this file>
Writes N0071_ver3_probe_out.json next to this file.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.services.commercial_planner import lineup_case_suggested_pos as mod
from app.services.imports.shipment_evidence_read import shipment_evidence_read_relation

OUT = Path(__file__).with_name("N0071_ver3_probe_out.json")
SAMPLE_N = 8


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


async def main() -> None:
    rel = shipment_evidence_read_relation()
    active = "" if rel == "shipment_evidence_current" else " AND ev.corpus_superseded_at IS NULL"
    engine = create_async_engine(
        _url(),
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=60000"},
    )
    out: dict = {"probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "evidence_relation": rel, "reader_model": mod.EV.__tablename__}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        out["statement_timeout"] = (await db.execute(text("SHOW statement_timeout"))).scalar()
        out["row_security"] = (await db.execute(text("SHOW row_security"))).scalar()

        # line_state spellings in the evidence relation (exact vs normalised comparison)
        out["line_state_values"] = [
            {"value": v, "rows": int(n), "units": float(u or 0)}
            for v, n, u in (await db.execute(text(
                f"SELECT line_state, count(*), sum(quantity) FROM {rel} ev WHERE true{active} "
                "GROUP BY line_state ORDER BY line_state"))).all()
        ]
        out["po_linked_by_state"] = [
            {"value": v, "rows": int(n), "units": float(u or 0)}
            for v, n, u in (await db.execute(text(
                f"SELECT line_state, count(*), sum(quantity) FROM {rel} ev "
                f"WHERE ev.purchase_order_id IS NOT NULL{active} GROUP BY line_state ORDER BY line_state"))).all()
        ]

        t0 = time.perf_counter()
        by_po = {}
        for cid, po_id, so, al, mpc in (await db.execute(text(f"""
            WITH cp AS (SELECT DISTINCT case_id, product_id FROM commercial_lineup_line
                        WHERE product_id IS NOT NULL)
            SELECT cp.case_id, ev.purchase_order_id,
                   coalesce(sum(ev.quantity) FILTER (WHERE lower(btrim(ev.line_state)) = 'shipped'), 0),
                   coalesce(sum(ev.quantity), 0),
                   count(DISTINCT ev.product_id)
            FROM cp JOIN {rel} ev ON ev.product_id = cp.product_id
            WHERE ev.purchase_order_id IS NOT NULL{active}
            GROUP BY cp.case_id, ev.purchase_order_id"""))).all():
            by_po[(int(cid), int(po_id))] = (float(so), float(al), int(mpc))
        by_dist = {}
        for cid, did, so, al, mpc, npo in (await db.execute(text(f"""
            WITH cp AS (SELECT DISTINCT case_id, product_id FROM commercial_lineup_line
                        WHERE product_id IS NOT NULL)
            SELECT cp.case_id, po.distributor_id,
                   coalesce(sum(ev.quantity) FILTER (WHERE lower(btrim(ev.line_state)) = 'shipped'), 0),
                   coalesce(sum(ev.quantity), 0),
                   count(DISTINCT ev.product_id), count(DISTINCT po.id)
            FROM cp JOIN {rel} ev ON ev.product_id = cp.product_id
            JOIN purchase_order po ON po.id = ev.purchase_order_id
            JOIN dim_distributor d ON d.id = po.distributor_id
            WHERE true{active}
            GROUP BY cp.case_id, po.distributor_id"""))).all():
            by_dist[(int(cid), int(did))] = (float(so), float(al), int(mpc), int(npo))
        out["independent_sql_s"] = round(time.perf_counter() - t0, 2)
        out["independent_case_po_pairs"] = len(by_po)
        out["independent_case_po_pairs_with_open_units"] = sum(1 for v in by_po.values() if v[1] != v[0])

        # sample: the cases with the most open (non-shipped) units on PO-linked evidence, plus the
        # lowest-id cases with products, so both "fix matters" and ordinary cases are covered
        open_by_case: dict[int, float] = {}
        for (cid, _), (so, al, _m) in by_po.items():
            open_by_case[cid] = open_by_case.get(cid, 0.0) + (al - so)
        ranked = sorted(open_by_case, key=lambda c: (-open_by_case[c], c))
        sample = ranked[: SAMPLE_N - 2] + [c for c in sorted(open_by_case) if c not in ranked[: SAMPLE_N - 2]][:2]
        out["sample_cases"] = sample
        out["sample_open_units_by_case"] = {str(c): open_by_case[c] for c in sample}

        po_cmp = {"rows": 0, "eq_shipped_only": 0, "eq_all_states": 0, "matched_eq": 0, "zero": 0,
                  "reader_total": 0.0, "indep_shipped_only_total": 0.0, "indep_all_states_total": 0.0,
                  "mismatches": []}
        dist_cmp = {"rows": 0, "eq_shipped_only": 0, "eq_all_states": 0, "matched_eq": 0, "po_count_eq": 0,
                    "zero": 0, "reader_total": 0.0, "indep_shipped_only_total": 0.0,
                    "indep_all_states_total": 0.0, "order_ok_cases": 0, "order_cases": 0,
                    "all_states_would_reorder_cases": 0, "mismatches": []}
        t1 = time.perf_counter()
        for cid in sample:
            for s in (await mod.suggest_pos_for_case(db, cid))["suggestions"]:
                so, al, mpc = by_po.get((cid, s["purchase_order_id"]), (None, None, None))
                v = s["total_shipped_units"]
                po_cmp["rows"] += 1
                po_cmp["reader_total"] += v
                po_cmp["indep_shipped_only_total"] += so or 0
                po_cmp["indep_all_states_total"] += al or 0
                po_cmp["eq_shipped_only"] += int(so is not None and abs(v - so) < 1e-6)
                po_cmp["eq_all_states"] += int(al is not None and abs(v - al) < 1e-6)
                po_cmp["matched_eq"] += int(mpc == s["matched_product_count"])
                po_cmp["zero"] += int(v == 0)
                if (so is None or abs(v - so) >= 1e-6) and len(po_cmp["mismatches"]) < 5:
                    po_cmp["mismatches"].append({"case": cid, "po": s["purchase_order_id"], "reader": v,
                                                 "indep": so})
            rows = (await mod.suggest_distributors_for_case(db, cid))["suggested_distributors"]
            keys_reader = []
            alt = []
            for d in rows:
                so, al, mpc, npo = by_dist.get((cid, d["distributor_id"]), (None, None, None, None))
                v = d["total_shipped_units"]
                dist_cmp["rows"] += 1
                dist_cmp["reader_total"] += v
                dist_cmp["indep_shipped_only_total"] += so or 0
                dist_cmp["indep_all_states_total"] += al or 0
                dist_cmp["eq_shipped_only"] += int(so is not None and abs(v - so) < 1e-6)
                dist_cmp["eq_all_states"] += int(al is not None and abs(v - al) < 1e-6)
                dist_cmp["matched_eq"] += int(mpc == d["matched_product_count"])
                dist_cmp["po_count_eq"] += int(npo == d["po_count"])
                dist_cmp["zero"] += int(v == 0)
                keys_reader.append((mpc or 0, so or 0.0))
                alt.append((mpc or 0, so or 0.0, al or 0.0, d["distributor_id"]))
                if (so is None or abs(v - so) >= 1e-6) and len(dist_cmp["mismatches"]) < 5:
                    dist_cmp["mismatches"].append({"case": cid, "distributor": d["distributor_id"],
                                                   "reader": v, "indep": so})
            if rows:
                dist_cmp["order_cases"] += 1
                dist_cmp["order_ok_cases"] += int(keys_reader == sorted(keys_reader, key=lambda k: (-k[0], -k[1])))
                if len(alt) > 1:
                    a = [x[3] for x in sorted(alt, key=lambda k: (-k[0], -k[1], k[3]))]
                    b = [x[3] for x in sorted(alt, key=lambda k: (-k[0], -k[2], k[3]))]
                    dist_cmp["all_states_would_reorder_cases"] += int(a != b)
        out["reader_calls_s"] = round(time.perf_counter() - t1, 2)
        for d in (po_cmp, dist_cmp):
            for k in ("reader_total", "indep_shipped_only_total", "indep_all_states_total"):
                d[k] = round(d[k], 4)
        out["suggest_pos"] = po_cmp
        out["suggest_distributors"] = dist_cmp

        # no-write evidence
        out["pg_stat"] = [
            {"table": r, "ins": int(i), "upd": int(u), "del": int(dl)}
            for r, i, u, dl in (await db.execute(text(
                "SELECT relname, n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables "
                "WHERE relname IN ('fact_inbound_shipment','shipment_evidence_observation',"
                "'shipment_evidence_line','purchase_order','commercial_lineup_case_po') ORDER BY relname"))).all()
        ]
        out["transaction_read_only_end"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        await db.rollback()
    await engine.dispose()
    txt = json.dumps(out, indent=2, default=str)
    OUT.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
