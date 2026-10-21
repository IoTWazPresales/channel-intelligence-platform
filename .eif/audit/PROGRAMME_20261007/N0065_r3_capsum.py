"""Summarise an n0065_capture.py JSON: per path and mode, each statement's ms and SQL head.

python N0065_r3_capsum.py <capture.json> [path-substring]
"""

import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
needle = sys.argv[2] if len(sys.argv) > 2 else ""
for s in d["stmts"]:
    if all(n in (s["label"] or "") for n in needle.split("+")):
        sql = " ".join((s.get("sql") or "").split())
        print(f"{s['label']:45} {s.get('ms')!s:>9} ms rows={s.get('rows')}  {sql[:220]}")
