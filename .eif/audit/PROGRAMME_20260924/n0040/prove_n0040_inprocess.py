"""N-0040 D-g proof, in-process (no DB writes, no clone).

CREATE DATABASE is denied for role cip (N-0039 evidence) and the archive tree is outside the
allowed roots, so the proof re-runs the OLD resolver (HEAD copy: old_resolver.py,
old_period_inference.py, old_archive_config.py) and the NEW resolver over every persisted lineup
case's own inputs, read read-only from cip:
  - rows: each case's commercial_lineup_line product_id (a synthetic token per line; the line
    resolves exactly when it has product_id), BU per product from dim_product.product_line
  - sheet_name / folder_path: the case's import_job lineup_parse_options (bulk path)
  - filename: case.file_name (H5 filename fallback)
Old codes: resolver default {NB,NR,NX,NV} (H1, what the preview endpoint used, H3);
archive/web folder codes {NB,NR,NV,NX,PF,XB} (H2/H8). New codes: sellable dim_product.product_line.
Outputs: BU per case (auto tier, and final with the steward/slice business_unit as manual),
collision groups (period|customer|BU) over active cases, the 7 supersession pairs, and the
filename-fallback product_line per case.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE.parents[3] / "apps" / "api"
sys.path.insert(0, str(API))

import psycopg  # noqa: E402

from app.services.commercial_planner import lineup_business_unit_resolution as new_res  # noqa: E402
from app.services.commercial_planner import lineup_period_inference as new_pi  # noqa: E402
from app.services.commercial_planner import lineup_backfill_archive_config as new_arch  # noqa: E402
from app.services.imports.distributor_sales_inventory import (  # noqa: E402
    ProductResolutionIndex,
    _product_token_key,
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


old_res = _load("old_resolver")
old_pi = _load("old_period_inference")
old_arch = _load("old_archive_config")

conn = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname="cip")
conn.read_only = True
cur = conn.cursor()
cur.execute("select current_database()")
print("current_database() =", cur.fetchone()[0], "(read-only session)")

cur.execute(
    "select trim(product_line), count(*) from dim_product where product_line is not null "
    "and trim(product_line) <> '' group by 1 order by 2 desc, 1"
)
line_rows = cur.fetchall()
NEW_CODES = frozenset(r[0] for r in line_rows)
print("sellable product lines (new source):", len(NEW_CODES), ", ".join(f"{c}={n}" for c, n in line_rows))
cur.execute("select count(*) from dim_product where product_line is null or trim(product_line) = ''")
print("NULL/blank product_line rows:", cur.fetchone()[0])
OLD_RESOLVER_CODES = old_res.CANONICAL_SHEET_BU_CODES
OLD_ARCHIVE_CODES = old_arch.DEFAULT_ACZA_TENANT_BU_CODES
print("old resolver default codes:", sorted(OLD_RESOLVER_CODES), "| old archive/web codes:", sorted(OLD_ARCHIVE_CODES))

cur.execute("select id, trim(product_line) from dim_product where product_line is not null and trim(product_line) <> ''")
bu_by_pid = {int(pid): pl for pid, pl in cur.fetchall()}

cur.execute(
    """
    select c.id, c.file_name, c.business_unit, c.product_line, c.inferred_period_start,
           c.superseded_by_case_id, c.commercial_status, j.staged_metadata
    from commercial_lineup_case c left join import_job j on j.id = c.import_job_id
    order by c.id
    """
)
cases = cur.fetchall()
cur.execute("select case_id, id, product_id, customer_id from commercial_lineup_line order by case_id, id")
lines_by_case: dict[int, list[tuple[int, int | None, int | None]]] = defaultdict(list)
for case_id, lid, pid, cust in cur.fetchall():
    lines_by_case[int(case_id)].append((int(lid), pid, cust))
conn.rollback()
conn.close()


def _index_for(lines):
    sku_to_id = {_product_token_key(f"n0040-line-{lid}"): int(pid) for lid, pid, _ in lines if pid is not None}
    return ProductResolutionIndex(
        sku_to_id=sku_to_id, part_number_to_ids={}, sales_model_name_to_ids={}, model_name_to_ids={},
        marketing_name_to_ids={}, ean_to_ids={}, upc_to_ids={}, alias_value_to_ids={},
        steward_alias_by_key={}, products_by_id={},
    )


def _folder_old_new(folder_path: str | None):
    """Folder path as the old web/archive parser (6 codes) vs the new one (catalogue codes) would stage it."""
    if not folder_path:
        return None, None
    rel = Path(folder_path.replace("\\", "/")) / "file.xlsx"
    old = old_arch.parse_archive_relative_path(rel, tenant_bu_codes=OLD_ARCHIVE_CODES)["folder_path"]
    new = new_arch.parse_archive_relative_path(rel, tenant_bu_codes=NEW_CODES)["folder_path"]
    return old, new


results = []
for cid, fname, bu, pl, period_start, sup, status, meta in cases:
    meta = meta if isinstance(meta, dict) else {}
    opts = meta.get("lineup_parse_options") or {}
    sheet = opts.get("sheet_name")
    folder_raw = opts.get("folder_path")
    manual = opts.get("business_unit")
    folder_old, folder_new = _folder_old_new(folder_raw)
    lines = lines_by_case.get(int(cid), [])
    idx = _index_for(lines)
    old_rows = [old_res.LineupRowProductTokens(sku_raw=f"n0040-line-{lid}") for lid, _, _ in lines]
    new_rows = [new_res.LineupRowProductTokens(sku_raw=f"n0040-line-{lid}") for lid, _, _ in lines]
    o = old_res.resolve_lineup_business_unit(
        rows=old_rows, product_index=idx, business_unit_by_product_id=bu_by_pid,
        sheet_name=sheet, folder_path=folder_old,
    )
    n = new_res.resolve_lineup_business_unit(
        rows=new_rows, product_index=idx, business_unit_by_product_id=bu_by_pid,
        sheet_name=sheet, folder_path=folder_new, tenant_bu_codes=NEW_CODES,
    )
    fo = (manual or o.business_unit)
    fn = (manual or n.business_unit)
    old_fname_pl = old_pi.infer_product_line_from_filename(fname)
    new_fname_pl = new_pi.infer_product_line_from_filename(fname, line_codes=NEW_CODES)
    resolved_plines = [bu_by_pid[int(p)] for _, p, _ in lines if p is not None and int(p) in bu_by_pid]
    old_case_pl = old_pi.infer_case_product_line(
        filename=fname, total_rows=len(lines), resolved_product_lines=resolved_plines
    )
    new_case_pl = new_pi.infer_case_product_line(
        filename=fname, total_rows=len(lines), resolved_product_lines=resolved_plines, line_codes=NEW_CODES
    )
    cust_counts = Counter(c for _, _, c in lines if c is not None)
    customer = cust_counts.most_common(1)[0][0] if cust_counts else None
    results.append(dict(
        id=cid, file=fname, persisted_bu=bu, persisted_pl=pl, sheet=sheet, folder=folder_raw,
        manual=manual, old_auto=(o.business_unit, o.source_tier), new_auto=(n.business_unit, n.source_tier),
        old_final=fo, new_final=fn, old_fname_pl=old_fname_pl, new_fname_pl=new_fname_pl,
        period=str(period_start) if period_start else None, customer=customer, superseded_by=sup,
        status=status, rows=len(lines), resolved=sum(1 for _, p, _ in lines if p is not None),
        old_flags=o.flags, new_flags=n.flags,
        old_case_pl=old_case_pl, new_case_pl=new_case_pl,
    ))

print()
print("case | rows/resolved | sheet | folder | manual | persisted BU | old auto (tier) | new auto (tier) | old final | new final | fname PL old->new")
for r in results:
    print(
        f"{r['id']} | {r['rows']}/{r['resolved']} | {r['sheet']} | {r['folder']} | {r['manual']} | {r['persisted_bu']} | "
        f"{r['old_auto'][0]} ({r['old_auto'][1]}) | {r['new_auto'][0]} ({r['new_auto'][1]}) | {r['old_final']} | {r['new_final']} | "
        f"{r['old_fname_pl']} -> {r['new_fname_pl']}"
    )

auto_changed = [r for r in results if r["old_auto"] != r["new_auto"]]
final_changed = [r for r in results if r["old_final"] != r["new_final"]]
final_vs_persisted_new = [r for r in results if r["new_final"] is not None and r["new_final"] != r["persisted_bu"]]
final_vs_persisted_old = [r for r in results if r["old_final"] is not None and r["old_final"] != r["persisted_bu"]]
fname_changed = [r for r in results if r["old_fname_pl"] != r["new_fname_pl"]]
print()
print("cases:", len(results))
print("auto BU changed old->new:", len(auto_changed), [(r["id"], r["old_auto"], r["new_auto"]) for r in auto_changed])
print("final BU (manual else auto) changed old->new:", len(final_changed), [(r["id"], r["old_final"], r["new_final"]) for r in final_changed])
print("new final BU != persisted BU:", len(final_vs_persisted_new), [(r["id"], r["new_final"], r["persisted_bu"]) for r in final_vs_persisted_new])
print("old final BU != persisted BU:", len(final_vs_persisted_old), [(r["id"], r["old_final"], r["persisted_bu"]) for r in final_vs_persisted_old])
print("filename-fallback product_line changed old->new:", len(fname_changed), [(r["id"], r["old_fname_pl"], r["new_fname_pl"]) for r in fname_changed])
case_pl_changed = [r for r in results if r["old_case_pl"] != r["new_case_pl"]]
print("effective case product_line inference (catalogue majority, filename fallback when <25% resolved) changed old->new:",
      len(case_pl_changed), [(r["id"], r["rows"], r["resolved"], r["old_case_pl"], r["new_case_pl"], r["persisted_pl"]) for r in case_pl_changed])
print("new effective case product_line != persisted product_line:",
      [(r["id"], r["new_case_pl"], r["persisted_pl"]) for r in results if r["new_case_pl"] != r["persisted_pl"]])


def _groups(key_bu: str):
    g: dict[str, list[int]] = defaultdict(list)
    for r in results:
        if r["superseded_by"] is not None or r["status"] in ("cancelled", "superseded"):
            continue
        g[f"{r['period']}|{r['customer']}|{r[key_bu]}"].append(r["id"])
    return {k: sorted(v) for k, v in g.items() if len(v) >= 2}


g_old = _groups("old_final")
g_new = _groups("new_final")
g_pers = _groups("persisted_bu")
print()
print("active-case collision groups (period|customer|BU, >=2 members): persisted", len(g_pers), "old", len(g_old), "new", len(g_new))
print("  persisted:", g_pers)
print("  old == new:", g_old == g_new, "| new == persisted:", g_new == g_pers)

by_id = {r["id"]: r for r in results}
pairs = [(r["id"], r["superseded_by"]) for r in results if r["superseded_by"] is not None]
print()
print("supersession pairs (loser -> winner):", len(pairs))
same = 0
for loser, winner in pairs:
    lo, wi = by_id[loser], by_id.get(winner)
    ok = wi is not None and lo["old_final"] == lo["new_final"] and wi["old_final"] == wi["new_final"]
    same += ok
    print(
        f"  {loser}->{winner}: persisted {lo['persisted_bu']}->{wi and wi['persisted_bu']} | "
        f"old {lo['old_final']}->{wi and wi['old_final']} | new {lo['new_final']}->{wi and wi['new_final']} | each member old BU == new BU: {ok}"
    )
print("pairs unchanged old -> new:", same, "of", len(pairs))
