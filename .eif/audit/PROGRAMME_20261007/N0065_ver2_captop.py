"""List the top captured statements per heavy path and mode from N0065_r3_cap_cip_0025.json (no DB access)."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
cap = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "N0065_r3_cap_cip_0025.json")
d = json.load(open(cap, encoding="utf-8"))
for lab in ("brief" + "/signals", "cover-" + "distribution"):
    for m in ("unset", "star", "NB"):
        st = [s for s in d["stmts"] if s.get("label") and s["label"].startswith(m + " ") and lab in s["label"]
              and s.get("ms") is not None]
        tot = round(sum(s["ms"] for s in st))
        st.sort(key=lambda s: -s["ms"])
        print(f"{m:5} {lab} n={len(st)} sum_ms={tot}")
        for s in st[:5]:
            print(f"   {s['ms']:>8} {s['engine']:5} {' '.join(s['sql'].split())[:150]}")
