"""Offline viewer for 3_jobs.out.json (no database access)."""
import json

d = json.load(open(".eif/audit/OVERNIGHT_20261102/queries/3_jobs.out.json"))
for j in d["jobs"]:
    r = d["reasons_by_job"].get(str(j["job_id"]))
    print(
        j["job_id"], "cust", j["staged_cust_ids"], j["status"], j["stage"], "ARCH" if j["archived"] else "",
        "|", j["file_name"][:60], "| created", str(j["created_at"])[:10],
        "| staged", j["staged_rows"], "applied", j["applied_rows"], "facts_owned", j["fact_rows_owned"],
        "with_fact_id", j["lines_with_fact_id"], "| units", j["staged_units"], "unappl", j["unapplied_units"],
        "|", j["d_min"], j["d_max"], "dates", j["n_dates"], "sites", j["n_sites"],
        "| yc", j["year_confirmed"], "| err", (j["error_summary"] or "")[:80], "|", r,
    )
