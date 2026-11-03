"""READ-ONLY 2c step 4: simulate the shipment decision-reuse pass over the stored needs_review shipment candidates.

RE-IMPLEMENTATION (nothing from the application is called). It copies, in read-only Python/SQL:
  * score_shipment_customer_token_candidate / score_shipment_distributor_candidate
    (apps/api/app/services/imports/shipment_evidence_resolution_plan.py:259-448)
  * the reuse filter in _reuse_earlier_*_alias_decisions
    (apps/api/app/services/imports/shipment_evidence_import.py:466-502 and 679-720)
  * the preconditions inside _apply_map_shipment_*_without_commit
    (apps/api/app/services/imports/shipment_evidence_steward_ops.py:233-286 and 452-511)
    and append_shipment_customer_aliases_scoped (shipment_customer_alias_scope.py)
No write is made. Candidate rows are the STORED ones (the real pass first deletes and rebuilds them from the lines).
"""
import json
from collections import Counter, defaultdict

from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/2c_ship_sim.out.json"


def norm_key(s):  # copy of distributor_sales_inventory._norm_key (strip, lower, collapse whitespace)
    import re
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())


def follow(start, parent):
    cur = int(start)
    seen = set()
    for _ in range(32):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = parent.get(cur)
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


def src_match(alias_src, cand_src):  # shipment_evidence_resolution_plan._alias_source_match
    if cand_src is not None:
        return alias_src is None or alias_src == cand_src
    return alias_src is None


async def work(db):
    out = {}
    # visibility check (row-level security can hide lines); report both
    out["lines_visible_default"] = (await q(db, "select count(*) n from shipment_evidence_line"))[0]["n"]
    await db.execute(__import__("sqlalchemy").text("select set_config('cip.product_lines','*',true), set_config('cip.editable_product_lines','*',true)"))
    out["lines_visible_after_all_product_lines_guc"] = (await q(db, "select count(*) n from shipment_evidence_line"))[0]["n"]

    cands = await q(db, """select id, import_job_id, entity_type, normalized_key, source_definition_id, row_count, status,
        match_reason, suggested_entity_id, context, sample_raw_values
        from import_entity_mapping_candidate where status='needs_review' and entity_type in ('shipment_customer_token','shipment_distributor')""")
    jobs = sorted({c["import_job_id"] for c in cands})
    jobinfo = {r["id"]: r for r in await q(db, "select id, file_name, status, stage, import_mode, to_char(created_at,'YYYY-MM') as month, archived_at is not null as archived from import_job where id = any(:j)", j=jobs)}

    caliases = await q(db, "select id, normalized_token, customer_id, source_definition_id, distributor_id, status from customer_source_token_alias")
    daliases = await q(db, "select id, normalized_token, distributor_id, source_definition_id, status from distributor_source_token_alias")
    out["alias_status_counts"] = {
        "customer": Counter(a["status"] for a in caliases), "distributor": Counter(a["status"] for a in daliases)}
    cust = {r["id"]: r for r in await q(db, "select id, merged_into_customer_id, customer_status from dim_customer")}
    dist = {r["id"]: r for r in await q(db, "select id, code, name, merged_into_distributor_id, distributor_status from dim_distributor")}
    cparent = {i: r["merged_into_customer_id"] for i, r in cust.items()}
    dparent = {i: r["merged_into_distributor_id"] for i, r in dist.items()}
    credir = {i: follow(i, cparent) for i in cust}
    dredir = {i: follow(i, dparent) for i in dist}

    ca_appr = [a for a in caliases if a["status"] == "approved"]
    da_appr = [a for a in daliases if a["status"] == "approved"]

    # lines
    lines = await q(db, "select id, import_job_id, customer_resolution_status, distributor_resolution_status, distributor_id, customer_id from shipment_evidence_line where import_job_id = any(:j)", j=jobs)
    line_by_id = {l["id"]: l for l in lines}

    # earlier decisions on OTHER candidates with the same key (any job), for "why not"
    earlier = await q(db, """select entity_type, normalized_key, import_job_id, status, suggested_entity_id, id
        from import_entity_mapping_candidate where entity_type in ('shipment_customer_token','shipment_distributor') and status <> 'needs_review'""")
    earlier_by = defaultdict(list)
    for e in earlier:
        earlier_by[(e["entity_type"], e["normalized_key"])].append(e)

    rows = []
    for c in cands:
        ctx = c["context"] if isinstance(c["context"], dict) else {}
        et = c["entity_type"]
        src = c["source_definition_id"]
        line_ids = []
        for x in ctx.get("line_ids") or []:
            try:
                line_ids.append(int(x))
            except (TypeError, ValueError):
                pass
        found = [line_by_id[i] for i in line_ids if i in line_by_id and line_by_id[i]["import_job_id"] == c["import_job_id"]]
        r = {"id": c["id"], "job": c["import_job_id"], "entity": et, "key": c["normalized_key"], "rows": c["row_count"],
             "month": jobinfo[c["import_job_id"]]["month"], "stored_match_reason": c["match_reason"],
             "special_category": ctx.get("special_category"), "n_line_ids": len(line_ids), "n_lines_found_in_job": len(found)}
        if et == "shipment_customer_token":
            stale = bool(found) and all(l["customer_resolution_status"] == "resolved" for l in found)
        else:
            stale = bool(found) and all(l["distributor_id"] is not None for l in found)
        r["all_lines_already_resolved"] = stale

        # ---------- scoring (re-implementation) ----------
        if et == "shipment_customer_token":
            toks = []
            for x in ctx.get("source_tokens") or []:
                if isinstance(x, str) and x.strip():
                    nk = norm_key(x.strip())
                    if nk and nk not in toks:
                        toks.append(nk)
            if not toks and (c["normalized_key"] or "").strip():
                toks.append(c["normalized_key"].strip())
            r["n_tokens"] = len(toks)
            if not toks:
                r["score"] = "no_tokens"
            else:
                sets = []
                for nt in toks:
                    ids = {credir.get(a["customer_id"], a["customer_id"]) for a in ca_appr if a["normalized_token"] == nt and src_match(a["source_definition_id"], src)}
                    sets.append(ids)
                nonempty = [s for s in sets if s]
                if nonempty:
                    if any(len(s) > 1 for s in nonempty):
                        r["score"] = "alias_multiple_targets_for_token"
                    elif len({next(iter(s)) for s in nonempty}) > 1:
                        r["score"] = "alias_conflicting_across_tokens"
                    elif len(nonempty) < len(toks):
                        r["score"] = "alias_partial_coverage_across_tokens"
                    else:
                        r["score"] = "alias_map"
                        r["target"] = next(iter(nonempty[0]))
                else:
                    dsets = []
                    for nt in toks:
                        ids = {credir.get(i) for i, d in cust.items() if False}
                        dsets.append(ids)
                    r["score"] = "no_alias"  # dim exact match computed below (needs names/codes)
        else:
            nt = (c["normalized_key"] or "").strip()
            ids = []
            for a in da_appr:
                if a["normalized_token"] == nt and src_match(a["source_definition_id"], src):
                    t = dredir.get(a["distributor_id"], a["distributor_id"])
                    if t not in ids:
                        ids.append(t)
            r["n_tokens"] = 1
            if len(ids) == 1:
                r["score"] = "alias_map"
                r["target"] = ids[0]
            elif len(ids) > 1:
                r["score"] = "alias_multiple_targets_for_token"
            else:
                r["score"] = "no_alias"
        r["_toks"] = None
        rows.append((c, ctx, r))

    # exact dim code/name matches for no_alias candidates (strict equality on lower/strip, then collapse)
    cust_names = await q(db, "select id, lower(btrim(code)) code, lower(btrim(name)) name from dim_customer")
    dist_names = [{"id": i, "code": (d["code"] or "").strip().lower(), "name": (d["name"] or "").strip().lower()} for i, d in dist.items()]
    for c, ctx, r in rows:
        if r["score"] != "no_alias":
            continue
        if r["entity"] == "shipment_customer_token":
            toks = []
            for x in ctx.get("source_tokens") or []:
                if isinstance(x, str) and x.strip():
                    nk = norm_key(x.strip())
                    if nk and nk not in toks:
                        toks.append(nk)
            if not toks:
                toks = [(c["normalized_key"] or "").strip()]
            sets = []
            for nt in toks:
                s = {credir.get(n["id"], n["id"]) for n in cust_names if nt and (n["code"] == nt.lower() or n["name"] == nt.lower())}
                sets.append(s)
            ne = [s for s in sets if s]
            if ne:
                if any(len(s) > 1 for s in ne):
                    r["score"] = "dim_exact_multiple"
                elif len({next(iter(s)) for s in ne}) > 1:
                    r["score"] = "dim_exact_conflicting"
                elif len(ne) < len(toks):
                    r["score"] = "dim_exact_partial"
                else:
                    r["score"] = "dim_exact_single_not_alias"
        else:
            nt = (c["normalized_key"] or "").strip().lower()
            s = {dredir.get(d["id"], d["id"]) for d in dist_names if nt and (d["code"] == nt or d["name"] == nt)}
            if len(s) == 1:
                r["score"] = "dim_exact_single_not_alias"
            elif len(s) > 1:
                r["score"] = "dim_exact_multiple"

    # ---------- preconditions for alias_map ----------
    for c, ctx, r in rows:
        r["verdict"] = None
        sc = r["score"]
        et = r["entity"]
        src = c["source_definition_id"]
        if sc != "alias_map":
            r["verdict"] = "not_cleared:" + sc
            # earlier decisions on same key in other jobs
            ev = earlier_by.get((et, c["normalized_key"]), [])
            if ev:
                sts = Counter(e["status"] for e in ev)
                tg = {e["suggested_entity_id"] for e in ev if e["status"] == "resolved" and e["suggested_entity_id"] is not None}
                r["earlier_same_key"] = {"statuses": dict(sts), "distinct_resolved_targets": len(tg)}
            continue
        target = r["target"]
        if r["n_line_ids"] == 0:
            r["verdict"] = "not_cleared:apply_rejects_no_line_ids"
        elif r["n_lines_found_in_job"] < len(set(ctx.get("line_ids") or [])) and r["n_lines_found_in_job"] != r["n_line_ids"]:
            r["verdict"] = "not_cleared:apply_rejects_lines_not_in_job_scope"
        elif et == "shipment_customer_token":
            toks = []
            for x in ctx.get("source_tokens") or []:
                if isinstance(x, str) and x.strip():
                    t = x.strip()[:512]
                    if t not in toks:
                        toks.append(t)
            if not toks:
                s0 = (c["sample_raw_values"] or [None])[0] if isinstance(c["sample_raw_values"], list) else None
                toks = [s0 or c["normalized_key"] or ""]
            verdict = "WOULD_CLEAR"
            for raw in toks:
                nt = norm_key(raw.strip()[:512])[:512]
                if not nt:
                    continue
                ex = [a for a in ca_appr if a["normalized_token"] == nt and (a["source_definition_id"] if a["source_definition_id"] is not None else -1) == (src if src is not None else -1)
                      and (a["distributor_id"] if a["distributor_id"] is not None else -1) == -1]
                if ex and ex[0]["customer_id"] != target:
                    # apply compares the stored alias customer_id to the (already collapsed) target without following merges
                    if credir.get(ex[0]["customer_id"]) == target:
                        verdict = "not_cleared:apply_rejects_alias_points_to_merged_away_master"
                    else:
                        verdict = "not_cleared:apply_rejects_alias_points_to_different_customer"
                    break
            r["verdict"] = verdict
        else:
            raw = ""
            sv = c["sample_raw_values"] if isinstance(c["sample_raw_values"], list) else []
            for s in sv:
                if isinstance(s, str) and s.strip():
                    raw = s.strip()[:512]
                    break
            raw = raw or (c["normalized_key"] or "")
            nt = norm_key(raw)
            if not nt:
                r["verdict"] = "not_cleared:apply_rejects_empty_token"
            else:
                clash = [a for a in da_appr if a["normalized_token"] == nt[:512] and (a["source_definition_id"] if a["source_definition_id"] is not None else -1) == (src if src is not None else -1)]
                if clash:
                    r["verdict"] = "not_cleared:apply_insert_hits_unique_alias_index_409"
                else:
                    r["verdict"] = "WOULD_CLEAR"
        if r["verdict"] == "WOULD_CLEAR" and r["all_lines_already_resolved"]:
            r["verdict_note"] = "lines already resolved (rebuild would not recreate this candidate at all)"

    # ---------- summarise ----------
    summ = defaultdict(Counter)
    for c, ctx, r in rows:
        summ[r["entity"]][r["verdict"]] += 1
    out["verdicts_by_entity"] = {k: dict(v) for k, v in summ.items()}
    out["totals_by_entity"] = {k: sum(v.values()) for k, v in summ.items()}
    sc2 = defaultdict(Counter)
    for c, ctx, r in rows:
        sc2[r["entity"]][r["score"]] += 1
    out["score_by_entity"] = {k: dict(v) for k, v in sc2.items()}
    stale = Counter((r["entity"], r["all_lines_already_resolved"]) for _, _, r in rows)
    out["lines_already_resolved"] = {f"{k[0]}|{k[1]}": v for k, v in stale.items()}
    ln = Counter((r["entity"], "no_line_ids" if r["n_line_ids"] == 0 else ("all_found" if r["n_lines_found_in_job"] == r["n_line_ids"] else "some_missing")) for _, _, r in rows)
    out["line_scope"] = {f"{k[0]}|{k[1]}": v for k, v in ln.items()}
    out["special_category"] = dict(Counter((r["entity"], r["special_category"]) for _, _, r in rows if r["special_category"]).most_common()) if False else {
        f"{k[0]}|{k[1]}": v for k, v in Counter((r["entity"], r["special_category"]) for _, _, r in rows if r["special_category"]).items()}
    # stored vs re-scored reason
    out["stored_vs_rescored"] = {f"{r['entity']}|{r['stored_match_reason']} -> {r['score']}": v for r, v in []}
    cmp = Counter((r["entity"], r["stored_match_reason"], r["score"]) for _, _, r in rows)
    out["stored_vs_rescored"] = [{"entity": k[0], "stored": k[1], "rescored": k[2], "n": v} for k, v in sorted(cmp.items())]
    # earlier same-key decisions among not-cleared
    ek = Counter()
    for _, _, r in rows:
        if r["verdict"] != "WOULD_CLEAR":
            e = r.get("earlier_same_key")
            if not e:
                ek[(r["entity"], "no earlier decision on same key (any job)")] += 1
            else:
                ek[(r["entity"], "earlier same-key candidate statuses " + json.dumps(e["statuses"], sort_keys=True) + f" targets={e['distinct_resolved_targets']}")] += 1
    out["not_cleared_earlier_same_key"] = [{"entity": k[0], "earlier": k[1], "n": v} for k, v in sorted(ek.items())]
    # profile by job/month
    prof = defaultdict(Counter)
    for _, _, r in rows:
        prof[(r["entity"], r["job"], r["month"])][("clear" if r["verdict"] == "WOULD_CLEAR" else "not")] += 1
    out["by_job"] = [{"entity": k[0], "job": k[1], "month": k[2], "file_name": jobinfo[k[1]]["file_name"], "job_status": jobinfo[k[1]]["status"], "stage": jobinfo[k[1]]["stage"], "mode": jobinfo[k[1]]["import_mode"], **dict(v)} for k, v in sorted(prof.items())]
    # top not-cleared tokens by rows (data rows only)
    top = sorted([r for _, _, r in rows if r["verdict"] != "WOULD_CLEAR"], key=lambda x: -(x["rows"] or 0))[:15]
    out["top_not_cleared_tokens"] = [{"entity": r["entity"], "job": r["job"], "key": r["key"], "rows": r["rows"], "verdict": r["verdict"]} for r in top]
    out["would_clear_detail"] = [{"id": r["id"], "entity": r["entity"], "job": r["job"], "rows": r["rows"], "stored": r["stored_match_reason"], "special": r["special_category"]} for _, _, r in rows if r["verdict"] == "WOULD_CLEAR"]
    out["row_count_sum_by_verdict"] = {f"{e}|{v}": s for (e, v), s in Counter({(r["entity"], r["verdict"]): 0 for _, _, r in rows}).items()}
    sums = defaultdict(int)
    for _, _, r in rows:
        sums[f"{r['entity']}|{r['verdict']}"] += int(r["rows"] or 0)
    out["row_count_sum_by_verdict"] = dict(sums)
    out["alias_hit_has_distributor_scope"] = sum(1 for a in ca_appr if a["distributor_id"] is not None)
    out["customer_aliases_approved"] = len(ca_appr)
    out["distributor_aliases_approved"] = len(da_appr)
    out["customer_aliases_to_merged_loser"] = sum(1 for a in ca_appr if credir.get(a["customer_id"]) != a["customer_id"])
    out["distributor_aliases_to_merged_loser"] = sum(1 for a in da_appr if dredir.get(a["distributor_id"]) != a["distributor_id"])
    json.dump(out, open(OUT, "w"), indent=1, default=str)


run_ro(work)
