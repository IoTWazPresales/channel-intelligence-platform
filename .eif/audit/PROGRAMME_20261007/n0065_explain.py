"""N-0065 perf: EXPLAIN ANALYZE the heaviest captured statement per read path under three
settings (unset, '*', 'NB') in one READ ONLY transaction via set_config(..., true).
SELECT statements only; statement_timeout 60s. Read-only.
Usage: python n0065_explain.py <capture.json> <out.json> [topN]
"""
import json
import pathlib
import sys

from n0065_dbh import engine, ro, sa

cap = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
top_n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
by_path: dict[str, list] = {}
for s in cap["stmts"]:
    if s.get("ms") is None or not s.get("label"):
        continue
    mode, path = s["label"].split(" ", 1)
    if mode != "unset":
        continue
    sql = s["sql"].lstrip()
    if not sql.lower().startswith(("select", "with")):
        continue
    by_path.setdefault(path, []).append(s)


def walk(node, acc, depth=0):
    kids = node.get("Plans", [])
    loops = node.get("Actual Loops", 1) or 1
    total = (node.get("Actual Total Time") or 0) * loops
    child = sum((k.get("Actual Total Time") or 0) * (k.get("Actual Loops", 1) or 1) for k in kids)
    rel = node.get("Relation Name")
    filt = node.get("Filter", "") or ""
    calls = 0
    if "cip_product" in filt:
        calls = ((node.get("Actual Rows") or 0) + (node.get("Rows Removed by Filter") or 0)) * loops
    acc.append({"node": node.get("Node Type"), "rel": rel, "self_ms": round(total - child, 1),
                "loops": loops, "rows": node.get("Actual Rows"), "removed": node.get("Rows Removed by Filter"),
                "rls_calls": calls, "subplan": node.get("Subplan Name") or node.get("Parent Relationship")})
    for k in kids:
        walk(k, acc, depth + 1)


SETTINGS = [("unset", None), ("star", "*"), ("NB", "NB")]
out = []
e = engine()
for path, stmts in by_path.items():
    for s in sorted(stmts, key=lambda x: -x["ms"])[:top_n]:
        # Fresh connection per statement: once set_config ran on a backend, the setting reads ''
        # (not NULL) after the transaction ends, so 'unset' must start on a new backend.
        with e.connect() as c:
            ro(c)
            rec = {"path": path, "captured_ms": s["ms"], "sql_head": " ".join(s["sql"].split())[:400], "runs": {}}
            for name, val in SETTINGS:
                # set_config(..., true) is transaction-local; NULL cannot be restored once set, so
                # 'unset' runs first, before any set_config in this transaction.
                if val is not None:
                    c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": val})
                cur = c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()
                try:
                    c.exec_driver_sql("SAVEPOINT x")
                    plan = c.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, SERIALIZE, FORMAT JSON) " + s["sql"],
                                             s["params"] if s["params"] else None).scalar()
                    c.exec_driver_sql("RELEASE SAVEPOINT x")
                    p = plan[0] if isinstance(plan, list) else json.loads(plan)[0]
                    acc = []
                    walk(p["Plan"], acc)
                    acc_sorted = sorted(acc, key=lambda a: -a["self_ms"])[:6]
                    rec["runs"][name] = {"guc": cur, "exec_ms": round(p["Execution Time"], 1),
                                         "plan_ms": round(p["Planning Time"], 1), "rows": p["Plan"].get("Actual Rows"),
                                         "rls_calls": sum(a["rls_calls"] for a in acc), "top_nodes": acc_sorted}
                except Exception as ex:  # noqa: BLE001
                    c.exec_driver_sql("ROLLBACK TO SAVEPOINT x")
                    rec["runs"][name] = {"guc": cur, "error": str(ex).splitlines()[0][:200]}
                r = rec["runs"][name]
                print(f"{name:5} {r.get('exec_ms')}ms rows={r.get('rows')} rls_calls={r.get('rls_calls')} "
                      f"{r.get('error', '')} :: {path}", flush=True)
            out.append(rec)
            c.rollback()
pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("wrote", sys.argv[2])
