"""2a step 3 (READ-ONLY on cip + the two JSON files from steps 1 and 2): line-by-line join of the workbook's open lines
with cip's pipeline facts, plus the facts that left the pipeline since the 49,849 reading (audit event 26) and the live
headline figure computed with the application's own SQL.
Output: 2a_join_result.json and a stdout summary.
"""
import json
import pathlib
from collections import defaultdict

from ro import TENANT, q, run_ro

HERE = pathlib.Path(__file__).resolve().parent
wb = json.loads((HERE / "2a_workbook_open_lines.json").read_text(encoding="utf-8"))
cip = json.loads((HERE / "2a_cip_pipeline_facts.json").read_text(encoding="utf-8"))


def key_wb(r):
    return (r["order_no"], r["order_line"] or "", r["item"], r["delivery_no"] or "" if r["sheet"] == "Shipped-open" else "")


def lkey(order_no, order_line, item):
    return (str(order_no or "").strip().lower(), str(order_line or "").strip().lower(), str(item or "").strip().lower())


async def work(db):
    out = {}
    # ---- live headline with the application's SQL
    from app.services.supply_overview import _TODAY_SAST, _ISO_WEEK_START_SAST, _headline_sql

    head = await q(db, _headline_sql(_TODAY_SAST, _ISO_WEEK_START_SAST), tenant=TENANT)
    out["headline_now"] = {k: head[0][k] for k in ("open_lines", "open_units", "pipeline_lines", "pipeline_units", "shipped_lines", "shipped_units", "landed_units")}
    print("HEADLINE NOW", out["headline_now"])

    # ---- audit event 26 (facts retired from the pipeline after the 49,849 reading)
    cols = await q(db, "select column_name from information_schema.columns where table_name='platform_audit_event' order by ordinal_position")
    out["audit_cols"] = [c["column_name"] for c in cols]
    ev = await q(db, "select * from platform_audit_event where id in (18,22,23,24,25,26) order by id")
    brief = []
    for e in ev:
        d = {k: (str(v)[:200] if k not in ("details", "payload", "detail") else None) for k, v in e.items()}
        brief.append(d)
    out["audit_events_brief"] = brief
    ev26 = [e for e in ev if e.get("id") == 26]
    ids26 = []
    if ev26:
        blob = json.dumps(ev26[0], default=str)
        # the facts list: find the integer ids the event itself lists
        for k, v in ev26[0].items():
            if isinstance(v, (dict, list)):
                blob = json.dumps(v)
        out["event26_raw_head"] = blob[:1500]
        try:
            payload = next(v for v in ev26[0].values() if isinstance(v, dict) and v)
            for key in ("retired_fact_ids", "superseded_fact_ids", "fact_ids", "superseded", "facts"):
                if key in payload:
                    val = payload[key]
                    ids26 = [x["id"] if isinstance(x, dict) else x for x in val]
                    break
        except StopIteration:
            pass
    out["event26_fact_ids"] = ids26
    if ids26:
        rows = await q(
            db,
            "select id, import_job_id, line_state, status, order_no, order_line, item_code, quantity, superseded_by_fact_id, superseded_by_key, updated_at "
            "from fact_inbound_shipment where id = any(:ids) order by id",
            ids=ids26,
        )
        out["event26_facts"] = rows
        print("EVENT 26 facts", len(rows), "units", sum(r["quantity"] or 0 for r in rows))
        for r in rows:
            print("  ", r["id"], r["line_state"], r["order_no"], r["order_line"], r["item_code"], r["quantity"], "->", r["superseded_by_fact_id"])

    # ---- join
    cipmap = defaultdict(list)
    for r in cip:
        cipmap[lkey(r["order_no"], r["order_line"], r["item_code"])].append(r)
    wbmap = defaultdict(list)
    for r in wb:
        k = lkey(r["order_no"], r["order_line"], r["item"])
        wbmap[k].append(r)

    matched, qty_diff, wb_only, cip_only = [], [], [], []
    seen = set()
    for k, ws_ in wbmap.items():
        cs = cipmap.get(k, [])
        seen.add(k)
        wq = sum(x["qty"] for x in ws_)
        cq = sum((x["counted_qty"] or 0) for x in cs)
        if not cs:
            wb_only.extend(ws_)
        elif abs(wq - cq) < 1e-9:
            matched.append((k, wq, cq, len(ws_), len(cs)))
        else:
            qty_diff.append((k, wq, cq, len(ws_), len(cs), [x["fact_id"] for x in cs]))
    for k, cs in cipmap.items():
        if k not in seen:
            cip_only.extend(cs)

    out["join_counts"] = {
        "workbook_open_lines": len(wb),
        "workbook_open_units": sum(x["qty"] for x in wb),
        "cip_pipeline_facts": len(cip),
        "cip_pipeline_units": sum(x["counted_qty"] or 0 for x in cip),
        "keys_matched_equal_qty": len(matched),
        "units_matched_equal_qty": sum(m[1] for m in matched),
        "keys_matched_qty_differs": len(qty_diff),
        "workbook_units_on_qty_differs": sum(m[1] for m in qty_diff),
        "cip_units_on_qty_differs": sum(m[2] for m in qty_diff),
        "workbook_only_lines": len(wb_only),
        "workbook_only_units": sum(x["qty"] for x in wb_only),
        "cip_only_facts": len(cip_only),
        "cip_only_units": sum(x["counted_qty"] or 0 for x in cip_only),
    }
    out["qty_diff"] = [dict(key=list(m[0]), workbook=m[1], cip=m[2], wb_lines=m[3], cip_facts=m[4], fact_ids=m[5]) for m in qty_diff]
    out["workbook_only"] = wb_only
    out["cip_only"] = [{k: r[k] for k in ("fact_id", "job_id", "report_type", "source_sheet", "order_no", "order_line", "item_code", "customer_po", "counted_qty", "created_at")} for r in cip_only]
    print(json.dumps(out["join_counts"], indent=1))
    print("cip-only:", out["cip_only"])
    print("workbook-only:", wb_only[:10])
    print("qty differs:", out["qty_diff"][:10])

    # ---- the 3 test facts and what states hold the other facts of the workbook's job
    out["test_facts"] = await q(
        db,
        "select id, import_job_id, report_type, line_state, order_no, order_line, item_code, quantity, created_at, fact_upsert_key "
        "from fact_inbound_shipment where tenant_id=:t and order_no ilike 'AUD-PARI%' order by id",
        t=TENANT,
    )
    print("AUD-PARI facts:", out["test_facts"])
    out["job_1697_states"] = await q(
        db,
        "select line_state, count(*) n, coalesce(sum(quantity),0) units from fact_inbound_shipment where tenant_id=:t and import_job_id=1697 group by 1 order by 1",
        t=TENANT,
    )
    print("job 1697 states:", out["job_1697_states"])
    (HERE / "2a_join_result.json").write_text(json.dumps(out, default=str, indent=1), encoding="utf-8")


run_ro(work)
