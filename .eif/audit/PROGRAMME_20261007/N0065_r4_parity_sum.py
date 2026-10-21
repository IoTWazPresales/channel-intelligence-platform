"""Summarise N0065_r4_parity.json (no database)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
r = json.load(open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "N0065_r4_parity.json"), encoding="utf-8"))
print({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()
       if k.startswith(("cells", "mismatches", "n_tables", "definer"))})
for k in ("mismatches_0024", "mismatches_0025", "mismatches_0026"):
    for m in r.get(k, []):
        c = m[2]
        if "move" in c:
            bad_m = {s: v for s, v in c["move"].items() if v["allowed"] != v["exp"]}
            bad_i = {s: v for s, v in c["insert"].items() if v["allowed"] != v["exp"]}
            print(k, m[0], m[1], "update", c.get("update"), "exp", c.get("update_exp"), "bad move", bad_m, "bad insert", bad_i)
        else:
            print(k, m[0], m[1], json.dumps(c)[:600])
print("cross_0025_0026:", len(r.get("cross_0025_0026", [])), sorted({t for t, _ in r.get("cross_0025_0026", [])}))
for t, l in r.get("cross_0025_0026", []):
    print("   ", t, l)
for k in ("view_counts_0024", "view_counts_0025", "view_counts_0026", "view_reloptions_0026"):
    print(k, r.get(k))
cv = r.get("cross_version_differences", [])
print("cross 0024/0025:", len(cv), "designed:", sum(1 for x in cv if x[2]))
