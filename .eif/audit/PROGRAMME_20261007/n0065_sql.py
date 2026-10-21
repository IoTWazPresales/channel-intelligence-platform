"""Write the heaviest captured SQL for a path (unset mode) to n0065_sql_<n>.sql. Offline, no DB.
Usage: python n0065_sql.py <path-substring> [rank]"""
import json
import pathlib
import sys

here = pathlib.Path(__file__).parent
d = json.loads((here / "n0065_cap_unset.json").read_text(encoding="utf-8"))
rank = int(sys.argv[2]) if len(sys.argv) > 2 else 0
cands = [s for s in d["stmts"] if s.get("label") and sys.argv[1] in s["label"] and s.get("ms") is not None]
cands.sort(key=lambda s: -s["ms"])
s = cands[rank]
out = here / f"n0065_sql_{rank}.sql"
out.write_text(f"-- {s['label']} {s['ms']} ms\n-- params: {json.dumps(s['params'], default=str)[:2000]}\n{s['sql']}\n",
               encoding="utf-8")
print("wrote", out, len(s["sql"]))
