"""Summarise N0065_r5_parity.json (no database)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
r = json.load(open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "N0065_r5_parity.json"), encoding="utf-8"))
print({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()
       if k.startswith(("cells", "mismatches", "n_tables", "definer"))})
for k in ("mismatches_0024", "mismatches_0025", "mismatches_0026", "mismatches_0027"):
    for m in r.get(k, []):
        print(k, m[0], m[1], json.dumps(m[2])[:400])
for key in ("cross_0025_0026", "cross_0026_0027"):
    cx = r.get(key, [])
    print(f"{key}: {len(cx)} cells; tables {sorted({t for t, _ in cx})}")
    labels = sorted({l for _, l in cx})
    print("   labels:", labels)
for k in ("view_counts_0026", "view_counts_0027", "view_reloptions_0027", "pick_config_0026", "pick_config_0027"):
    print(k, r.get(k))
cv = r.get("cross_version_differences", [])
print("cross 0024/0025:", len(cv), "designed:", sum(1 for x in cv if x[2]))
p = r.get("per_table_0027", {})
for t, cells in p.items():
    print(f"0027 {t}:", {l: v for l, v in cells.items() if l.startswith("read")})
