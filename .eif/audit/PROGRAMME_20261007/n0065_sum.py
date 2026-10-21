"""Summarise captured statement time per (mode, path). Offline, no DB."""
import collections
import json
import pathlib
import sys

here = pathlib.Path(__file__).parent
for f in sys.argv[1:]:
    d = json.loads((here / f).read_text(encoding="utf-8"))
    agg = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
    for s in d["stmts"]:
        if not s.get("label"):
            continue
        a = agg[s["label"]]
        a[0] += 1
        a[1] += 1 if s.get("engine") == "sync" else 0
        a[2] += s.get("ms") or 0
        a[3] = max(a[3], s.get("ms") or 0)
    for k, v in agg.items():
        print(f"{v[2]:9.0f}ms n={v[0]:3} sync={v[1]:3} max={v[3]:8.0f} {k}")
    if "--top" in sys.argv[1:]:
        pass
