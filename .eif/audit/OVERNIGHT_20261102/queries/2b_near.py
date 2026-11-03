"""OFFLINE (no DB): proposal-only nearest-master check for the 479 unmatched lines, from the read-only dump.
A near master is a PROPOSAL for a steward to look at, never a match."""
import collections
import json
import re

BASE = ".eif/audit/OVERNIGHT_20261102/queries/"
D = json.load(open(BASE + "2b_dump_lines.out.json"))
rows = json.load(open(BASE + "2b_analyse_rows.out.json"))
M = D["master"]


def k(s):
    return (s or "").strip().lower()


def lev(a, b, cap=3):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


by_base = collections.defaultdict(list)
for p in M:
    for f in ("sales_model_name", "model_name"):
        if p.get(f):
            by_base[k(p[f]).split("-")[0]].append(p)
by_pre = collections.defaultdict(list)
for p in M:
    if p["sku"]:
        by_pre[k(p["sku"]).split("-")[0]].append(p)

items = {}
for r in rows:
    it = k(r["item_code"])
    d = items.setdefault(it, {"item_code": r["item_code"], "sales_model_name": r["sales_model_name"], "lines": 0, "units": 0.0, "distributors": set()})
    d["lines"] += 1
    d["units"] += r["quantity"]
    d["distributors"].add(r["distributor"])

out = []
for it, d in items.items():
    sm = k(d["sales_model_name"])
    base = sm.split("-")[0] if sm else ""
    pre = it.split("-")[0]
    same_base = {p["id"]: p for p in by_base.get(base, [])} if base else {}
    same_pre = {p["id"]: p for p in by_pre.get(pre, [])}
    best_sm = None
    for p in same_base.values():
        dist = lev(sm, k(p["sales_model_name"]))
        if best_sm is None or dist < best_sm[0]:
            best_sm = (dist, p["sales_model_name"], p["sku"])
    best_sku = None
    for p in same_pre.values():
        dist = lev(it, k(p["sku"]))
        if best_sku is None or dist < best_sku[0]:
            best_sku = (dist, p["sku"], p["sales_model_name"])
    out.append({"item_code": d["item_code"], "sales_model_name": d["sales_model_name"], "lines": d["lines"], "units": d["units"],
                "n_distributors": len(d["distributors"]), "masters_same_model_base": len(same_base), "masters_same_sku_prefix": len(same_pre),
                "nearest_by_sales_model": best_sm, "nearest_by_sku": best_sku,
                "family_depth": ("model_base_and_sku_prefix" if same_base and same_pre else "model_base_only" if same_base else "sku_prefix_only" if same_pre else "none")})
out.sort(key=lambda x: -x["units"])
summ = collections.defaultdict(lambda: {"items": 0, "lines": 0, "units": 0.0})
for o in out:
    s = summ[o["family_depth"]]
    s["items"] += 1
    s["lines"] += o["lines"]
    s["units"] += o["units"]
close = collections.defaultdict(lambda: {"items": 0, "lines": 0, "units": 0.0})
for o in out:
    d1 = o["nearest_by_sales_model"][0] if o["nearest_by_sales_model"] else 99
    d2 = o["nearest_by_sku"][0] if o["nearest_by_sku"] else 99
    lab = "edit_distance_le_2_on_sales_model_or_sku" if min(d1, d2) <= 2 else "edit_distance_3_or_more_or_no_sibling"
    o["nearness"] = lab
    close[lab]["items"] += 1
    close[lab]["lines"] += o["lines"]
    close[lab]["units"] += o["units"]
res = {"family_depth_summary": dict(summ), "nearness_summary": dict(close), "items": out}
json.dump(res, open(BASE + "2b_near.out.json", "w"), indent=1, default=str)
print(json.dumps({"family_depth_summary": res["family_depth_summary"], "nearness_summary": res["nearness_summary"]}, indent=1))
print([ (o["item_code"], o["sales_model_name"], o["nearest_by_sales_model"], o["nearest_by_sku"]) for o in out if o["nearness"].startswith("edit_distance_le_2")][:10])
