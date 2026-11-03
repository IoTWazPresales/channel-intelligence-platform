"""OFFLINE analysis (no DB access) over the dump written by 2b_dump_lines.py (read-only query output).
Classifies the 479 no_match lines by cause using normalised look-ups against the Product Master dump."""
import collections
import json
import re

BASE = ".eif/audit/OVERNIGHT_20261102/queries/"
D = json.load(open(BASE + "2b_dump_lines.out.json"))
L, M, A = D["lines"], D["master"], D["alias"]


def key(s):  # production _product_token_key (strip, lower, trailing .0 on digits)
    if s is None:
        return ""
    t = str(s).strip().lower()
    if not t or t == "nan":
        return ""
    if t.endswith(".0") and t[:-2].isdigit():
        t = t[:-2]
    return t


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", key(s))


def trimsep(s):
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", key(s))


def nolead0(s):
    return alnum(s).lstrip("0")


def digits(s):
    return re.sub(r"\D", "", key(s)).lstrip("0")


FIELDS = ["sku", "part_number", "sales_model_name", "model_name", "marketing_name", "ean", "upc"]


def build(fn):
    idx = collections.defaultdict(lambda: collections.defaultdict(set))
    for p in M:
        for f in FIELDS:
            v = p.get(f)
            k = fn(v) if v else ""
            if k:
                idx[k][f].add(p["id"])
    return idx


I_exact, I_alnum, I_trim, I_nolead0, I_digits = build(key), build(alnum), build(trimsep), build(nolead0), build(digits)
alias_exact = collections.defaultdict(set)
for a in A:
    alias_exact[key(a["alias_value"])].add(a["product_id"])

sku_prefix = collections.defaultdict(set)
for p in M:
    if p["sku"]:
        sku_prefix[key(p["sku"]).split("-")[0]].add(p["id"])
model_base = collections.defaultdict(set)
for p in M:
    for f in ("sales_model_name", "model_name"):
        v = p.get(f)
        if v:
            model_base[key(v).split("-")[0]].add(p["id"])
sm_full_base = collections.defaultdict(set)
for p in M:
    v = p.get("sales_model_name")
    if v and "-" in key(v):
        sm_full_base[key(v).rsplit("-", 1)[0]].add(p["id"])


def family(l):
    ic = key(l["item_code"])
    m = re.match(r"^\d*([a-z]+)", ic)
    return m.group(1).upper() if m else "?"


def pattern(l):
    parts = [
        "item" if key(l["item_code"]) else None,
        "model" if key(l["sales_model_name"]) else None,
        "customer_item" if key(l["customer_item"]) else None,
        "barcode" if (key(l["ean_code"]) or key(l["upc_code"])) else None,
        "mpor" if key(l["mpor_item_no"]) else None,
    ]
    return "+".join(x for x in parts if x)


def hits(idx, fn, val):
    k = fn(val) if val else ""
    return {f: sorted(ids) for f, ids in idx.get(k, {}).items()} if k else {}


def classify(l):
    ev = {}
    toks = {"item_code": l["item_code"], "sales_model_name": l["sales_model_name"], "ean_code": l["ean_code"],
            "upc_code": l["upc_code"], "mpor_item_no": l["mpor_item_no"]}
    exact = {}
    for n, v in toks.items():
        h = hits(I_exact, key, v)
        if h:
            exact[n] = h
        if v and key(v) in alias_exact:
            exact.setdefault(n, {})["alias"] = sorted(alias_exact[key(v)])
    ev["exact_hits"] = exact
    if exact:
        return "EXACT_HIT_BUT_UNMATCHED", ev
    fmt = {}
    for n, v in toks.items():
        if not v:
            continue
        for lab, idx, fn in (("alnum", I_alnum, alnum), ("trim_separators", I_trim, trimsep), ("lead0_alnum", I_nolead0, nolead0)):
            h = hits(idx, fn, v)
            if h:
                fmt.setdefault(n, {})[lab] = h
        if n in ("ean_code", "upc_code", "mpor_item_no") and len(digits(v)) >= 8:
            h = hits(I_digits, digits, v)
            if h:
                fmt.setdefault(n, {})["digits_no_leading_zero"] = h
    ev["format_hits"] = fmt
    if fmt:
        return "FORMAT_PROBLEM", ev
    near = {}
    ic = key(l["item_code"])
    sm = key(l["sales_model_name"])
    if ic and ic.split("-")[0] in sku_prefix:
        near["sku_prefix_masters"] = len(sku_prefix[ic.split("-")[0]])
    if sm and sm.split("-")[0] in model_base:
        near["model_base_masters"] = len(model_base[sm.split("-")[0]])
    if sm and "-" in sm and sm.rsplit("-", 1)[0] in sm_full_base:
        near["sales_model_without_trailer_masters"] = len(sm_full_base[sm.rsplit("-", 1)[0]])
    ev["near"] = near
    if near.get("sales_model_without_trailer_masters") or (near.get("sku_prefix_masters") and near.get("model_base_masters")):
        return "NEAR_FAMILY_ONLY", ev
    return "CATALOGUE_GAP", ev


rows = []
for l in L:
    c, ev = classify(l)
    rows.append({**{k: l[k] for k in ("id", "line_state", "distributor", "customer", "item_code", "sales_model_name", "ean_code",
                                      "upc_code", "mpor_item_no", "quantity")}, "family": family(l), "pattern": pattern(l), "cause": c, "ev": ev})

prod = {}
for r in rows:
    prod.setdefault(key(r["item_code"]), []).append(r)

summary = {}
ct = collections.Counter()
cu = collections.Counter()
for r in rows:
    ct[r["cause"]] += 1
    cu[r["cause"]] += r["quantity"]
summary["cause_totals"] = dict(ct)
summary["cause_units"] = dict(cu)
summary["distinct_item_codes"] = len(prod)
summary["item_codes_with_mixed_cause"] = [k for k, v in prod.items() if len({x["cause"] for x in v}) > 1]
fam_match = collections.Counter()
for p in M:
    m = re.match(r"^\d*([a-z]+)", key(p["sku"] or ""))
    f = m.group(1).upper() if m else "?"
    fam_match[f == (p["product_line"] or "").upper()] += 1
summary["family_rule_equals_master_product_line"] = {str(k): v for k, v in fam_match.items()}
fams = {r["family"] for r in rows}
MASTER_FAM = collections.Counter()
for p in M:
    m = re.match(r"^\d*([a-z]+)", key(p["sku"] or ""))
    MASTER_FAM[m.group(1).upper() if m else "?"] += 1
summary["by_family"] = sorted(
    ({"family": f, "lines": sum(1 for r in rows if r["family"] == f), "units": sum(r["quantity"] for r in rows if r["family"] == f),
      "distinct_item_codes": len({key(r["item_code"]) for r in rows if r["family"] == f}),
      "master_rows_same_family": MASTER_FAM.get(f, 0)} for f in fams),
    key=lambda x: -x["units"])


def smf(r):
    m = re.match(r"^([A-Za-z]+)", r["sales_model_name"] or "")
    return m.group(1).upper() if m else "?"


sm_fam = collections.defaultdict(lambda: [0, 0.0])
for r in rows:
    sm_fam[smf(r)][0] += 1
    sm_fam[smf(r)][1] += r["quantity"]
summary["by_sales_model_leading_letters"] = sorted(([k, v[0], v[1]] for k, v in sm_fam.items()), key=lambda x: -x[2])
pats = {r["pattern"] for r in rows}
summary["by_pattern"] = sorted(({"pattern": p, "lines": sum(1 for r in rows if r["pattern"] == p), "units": sum(r["quantity"] for r in rows if r["pattern"] == p)} for p in pats), key=lambda x: -x["units"])
samples = collections.defaultdict(list)
for r in rows:
    if len(samples[r["cause"]]) < 6:
        samples[r["cause"]].append({k: r[k] for k in ("item_code", "sales_model_name", "ean_code", "upc_code", "mpor_item_no")} | {"ev": r["ev"]})
summary["samples"] = dict(samples)
G = collections.defaultdict(lambda: {"lines": 0, "units": 0.0, "items": collections.Counter(), "models": collections.Counter(), "causes": collections.Counter(), "cause_units": collections.Counter(), "customers": collections.Counter()})
for r in rows:
    g = G[(r["distributor"], r["pattern"], r["family"])]
    g["lines"] += 1
    g["units"] += r["quantity"]
    g["items"][r["item_code"]] += r["quantity"]
    g["models"][r["sales_model_name"]] += r["quantity"]
    g["causes"][r["cause"]] += 1
    g["cause_units"][r["cause"]] += r["quantity"]
    g["customers"][r["customer"] or "<unresolved>"] += r["quantity"]
groups = []
for (d, p, f), g in G.items():
    groups.append({"distributor": d, "pattern": p, "family": f, "lines": g["lines"], "units": g["units"], "distinct_item_codes": len(g["items"]),
                   "top_items": [k for k, _ in g["items"].most_common(3)], "top_models": [k for k, _ in g["models"].most_common(3)],
                   "top_customers": [k for k, _ in g["customers"].most_common(3)],
                   "causes_lines": dict(g["causes"]), "causes_units": dict(g["cause_units"])})
groups.sort(key=lambda x: -x["units"])
summary["n_groups"] = len(groups)
summary["top25_groups"] = groups[:25]
summary["top25_units"] = sum(g["units"] for g in groups[:25])
dxc = {}
for r in rows:
    dxc.setdefault(r["distributor"], collections.Counter())[r["cause"]] += 1
summary["distributor_x_cause"] = {k: dict(v) for k, v in dxc.items()}
fp = [r for r in rows if r["cause"] == "FORMAT_PROBLEM"]
summary["format_problem_rows"] = [{k: r[k] for k in ("distributor", "item_code", "sales_model_name", "ean_code", "upc_code", "mpor_item_no", "quantity")} | {"fmt": r["ev"]["format_hits"]} for r in fp][:60]
odd = collections.Counter()
for r in rows:
    for n in ("item_code", "sales_model_name", "ean_code", "upc_code"):
        v = r[n]
        if not v:
            continue
        if v != v.strip():
            odd[n + ":outer_whitespace"] += 1
        if re.search(r"[_\s]+$", v):
            odd[n + ":trailing_sep_or_space"] += 1
        if v != v.upper() and n in ("item_code", "sales_model_name"):
            odd[n + ":not_upper"] += 1
        if v.endswith(".0"):
            odd[n + ":dot_zero"] += 1
        if n in ("ean_code", "upc_code") and not v.isdigit():
            odd[n + ":nondigit"] += 1
summary["token_oddities"] = dict(odd)
json.dump(summary, open(BASE + "2b_analyse.out.json", "w"), indent=1, default=str)
json.dump(rows, open(BASE + "2b_analyse_rows.out.json", "w"), default=str)
print(json.dumps({k: summary[k] for k in ("cause_totals", "cause_units", "distinct_item_codes", "item_codes_with_mixed_cause",
                                           "family_rule_equals_master_product_line", "token_oddities", "n_groups", "top25_units")}, indent=1))
