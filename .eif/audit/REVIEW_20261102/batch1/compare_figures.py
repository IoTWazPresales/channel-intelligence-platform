"""Print the before/after cip figures side by side (reads the two JSON files next to this script)."""
import json
from pathlib import Path

here = Path(__file__).resolve().parent
b = json.loads((here / "cip_figures_before.json").read_text())
a = json.loads((here / "cip_figures_after.json").read_text())
print("database:", a["database"], "| read-only:", b["transaction_read_only"], a["transaction_read_only"], "|", b["write_probe"], "|", a["write_probe"])
print("rule closed states  before:", b["rule_closed_states"], " after:", a["rule_closed_states"])
print("facts by state:", json.dumps(a["facts_by_state"]))
for k in ("v2_shipments_totals", "cover_distribution_open_inbound", "movement_lens_shipped", "weekly_flow", "intake_weighting_all_products"):
    print(k)
    print("  before", b[k])
    print("  after ", a[k])
bp, ap = b["intake_per_product"], a["intake_per_product"]
chg = [(p, bp[p], ap.get(p)) for p in bp if ap.get(p) != bp[p]]
print("products with intake weighting: before", len(bp), "after", len(ap), "| changed:", len(chg))
rows = []
for p, x, y in chg:
    if y is None:
        rows.append((999.0, p, "no longer has intake evidence", x, y))
    else:
        pct = 100 * (y["avg"] - x["avg"]) / x["avg"] if x["avg"] else 0.0
        rows.append((abs(pct), p, round(pct, 2), x, y))
rows.sort(key=lambda r: -r[0])
for r in rows[:8]:
    print("  ", r[1:], )
