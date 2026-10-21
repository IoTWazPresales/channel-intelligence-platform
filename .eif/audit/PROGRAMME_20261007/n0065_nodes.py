"""Print the top self-time plan nodes per path from n0065_explain.json. Offline, no DB.
Usage: python n0065_nodes.py [path-substring] [mode]"""
import json
import pathlib
import sys

d = json.loads((pathlib.Path(__file__).parent / "n0065_explain.json").read_text(encoding="utf-8"))
flt = sys.argv[1] if len(sys.argv) > 1 else ""
want = sys.argv[2] if len(sys.argv) > 2 else "NB"
for rec in d:
    if flt not in rec["path"]:
        continue
    print("==", rec["path"], "captured", rec["captured_ms"], "ms")
    if flt:
        print("   ", rec["sql_head"][:400])
    for mode, r in rec["runs"].items():
        if mode != want:
            continue
        if "error" in r:
            print("  ", mode, "ERROR", r["error"])
            continue
        print("  ", mode, r["exec_ms"], "ms rls_calls", int(r["rls_calls"]))
        for n in r["top_nodes"][:3]:
            print(f"      {n['node']:<18} {str(n['rel'] or ''):<30} self={n['self_ms']:>8} loops={n['loops']:>6}"
                  f" rows={n['rows']} removed={n['removed']} rls={int(n['rls_calls'])}")
