"""Summarise N0065_r3_parity.json (written by tests/test_product_line_rls_parity_n0065_db.py)."""

import json
import pathlib
from collections import Counter

p = pathlib.Path(__file__).with_name("N0065_r3_parity.json")
r = json.loads(p.read_text(encoding="utf-8"))
print("tables:", r["n_tables"], "| 0024 definer bypasses RLS:", r["definer_bypasses_rls"])
print("cells 0024:", r["cells_0024"], "mismatches vs model:", len(r["mismatches_0024"]))
print("cells 0025:", r["cells_0025"], "mismatches vs model:", len(r["mismatches_0025"]))
cross = r["cross_version_differences"]
print("cross-version differing cells:", len(cross))
print("  by label:", dict(Counter(c[1] for c in cross)))
print("  designed-scope flag:", dict(Counter(c[2] for c in cross)))
print("view counts 0024:", r["view_counts_0024"])
print("view counts 0025:", r["view_counts_0025"])
print("view reloptions 0024/0025:", r["view_reloptions_0024"], r["view_reloptions_0025"])
print("plan 0024:")
for x in r["plan_0024"]:
    print("   ", x)
print("plan 0025:")
for x in r["plan_0025"]:
    print("   ", x)
t = r["per_table_0025"]
labels = list(next(iter(t.values())).keys())
print("0025 visible / updated rows per table (cip_test, seeded):")
print("table".ljust(34), " | ".join(lbl.replace("read ", "R").replace("edit ", "E") for lbl in labels))
for name, cells in sorted(t.items()):
    print(name[:34].ljust(34), " ".join(str(cells[lbl]).rjust(3) for lbl in labels))
