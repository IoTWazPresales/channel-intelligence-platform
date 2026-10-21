"""N-0110 repair 2, read-only: site-merged rows, repeated rows and wrong-year rows.

usage: python measure.py <dbname> [--json]

A stored fact row is measured against the source rows of the load that last wrote it
(staging lines with fact_sellthrough_row_id = the row and import_job_id = its job).
Source identity = raw_row_payload without "_" meta keys, plus period ref, units and on-hand.

- site-merged: the row holds source rows of two or more sites.
- repeated: the row holds two or more source rows of one site. Identical copies count once,
  differing rows are summed (D-0091).
- wrong-year: the row's period starts after the day its load was created.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402

import psycopg  # noqa: E402

GROUPS = """
with l as (
  select s.fact_sellthrough_row_id fid, s.import_job_id jid,
         coalesce(s.site_label, s.raw_location_token, '') site,
         md5(coalesce((select jsonb_object_agg(k, v) from jsonb_each(s.raw_row_payload) e(k, v) where left(k, 1) <> '_'), '{}'::jsonb)::text
             || '|' || coalesce(s.raw_period_ref, '') || '|' || coalesce(s.units_sold::text, '') || '|' || coalesce(s.reported_soh::text, '')) ident,
         s.units_sold u, s.reported_soh soh
  from import_customer_sellthrough_staging_line s
  where s.apply_status = 'applied' and s.fact_sellthrough_row_id is not null
), d as (  -- one row per distinct source identity
  select fid, jid, site, ident, max(u) u, max(soh) soh, count(*) copies from l group by 1, 2, 3, 4
), g as (
  select f.id, f.customer_id, f.units_sold stored, f.reported_soh stored_soh,
         count(distinct d.site) sites, sum(d.copies) lines, count(*) idents,
         sum(d.u) source_units, sum(d.soh) source_soh
  from fact_customer_sellthrough f join d on d.fid = f.id and d.jid = f.import_job_id
  group by 1, 2, 3, 4
)
select id, customer_id, stored, stored_soh, sites, lines, idents, source_units, source_soh from g where lines >= 2
"""

WRONG_YEAR = """
select f.customer_id, f.period_start_date, f.import_job_id, j.created_at::date loaded, count(*), sum(f.units_sold)
from fact_customer_sellthrough f join import_job j on j.id = f.import_job_id
where f.period_start_date > j.created_at::date
group by 1, 2, 3, 4 order by 1, 2, 3
"""


def measure(db: str) -> dict:
    with psycopg.connect(url_for(db)) as conn:
        conn.read_only = True
        out: dict = {"current_database": conn.execute("select current_database()").fetchone()[0]}
        rows = conn.execute(GROUPS).fetchall()
        site = {"rows": 0, "stored_units": 0.0, "source_units": 0.0, "by_customer": {}}
        rep_ident = {"rows": 0, "stored_units": 0.0, "source_units": 0.0, "extra_copies": 0, "by_customer": {}}
        rep_diff = {"rows": 0, "stored_units": 0.0, "source_units": 0.0, "with_on_hand": 0, "by_customer": {}}
        for fid, cust, stored, _ssoh, sites, lines, idents, src, ssoh in rows:
            stored, src = float(stored or 0), float(src or 0)
            if sites >= 2:
                bucket = site
            elif idents == 1:
                bucket = rep_ident
                bucket["extra_copies"] += int(lines) - 1
            else:
                bucket = rep_diff
                if ssoh is not None:
                    bucket["with_on_hand"] += 1
            bucket["rows"] += 1
            bucket["stored_units"] += stored
            bucket["source_units"] += src
            c = bucket["by_customer"].setdefault(str(cust), [0, 0.0, 0.0])
            c[0] += 1
            c[1] += stored
            c[2] += src
        out["site_merged"] = site
        out["repeated_identical"] = rep_ident
        out["repeated_differing"] = rep_diff
        wy = conn.execute(WRONG_YEAR).fetchall()
        out["wrong_year"] = {
            "rows": sum(int(r[4]) for r in wy),
            "units": sum(float(r[5] or 0) for r in wy),
            "groups": [[r[0], r[1].isoformat(), r[2], r[3].isoformat(), int(r[4]), float(r[5] or 0)] for r in wy],
        }
        tot = conn.execute(
            "select customer_id, count(*), sum(units_sold), sum(reported_soh) from fact_customer_sellthrough group by 1 order by 1"
        ).fetchall()
        out["totals"] = {str(c): [int(n), float(u or 0), float(s or 0)] for c, n, u, s in tot}
        out["superseded_table_rows"] = conn.execute("select count(*) from fact_customer_sellthrough_superseded").fetchone()[0]
        return out


def main() -> None:
    res = measure(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(res))
        return
    print("current_database()", res["current_database"])
    for k in ("site_merged", "repeated_identical", "repeated_differing"):
        b = res[k]
        extra = {x: b[x] for x in ("extra_copies", "with_on_hand") if x in b}
        print(f"{k}: rows {b['rows']} stored units {b['stored_units']:g} source units {b['source_units']:g} "
              f"(+{b['source_units'] - b['stored_units']:g}) {extra}")
        for c, (n, st, sr) in sorted(b["by_customer"].items(), key=lambda kv: int(kv[0])):
            print(f"   customer {c}: rows {n} stored {st:g} source {sr:g}")
    wy = res["wrong_year"]
    print(f"wrong_year: rows {wy['rows']} units {wy['units']:g}")
    for g in wy["groups"]:
        print("   customer {} period {} job {} loaded {} rows {} units {:g}".format(*g))
    print("totals (customer: rows, units, on-hand)", res["totals"])
    print("superseded table rows", res["superseded_table_rows"])


if __name__ == "__main__":
    main()
