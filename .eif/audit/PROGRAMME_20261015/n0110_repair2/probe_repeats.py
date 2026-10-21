"""N-0110 repair 2, read-only: which source columns differ inside a repeated (one-site) group.

usage: python probe_repeats.py <dbname>
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402

import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0])
    rows = conn.execute(
        """
        select f.id, f.customer_id, f.units_sold, f.reported_soh, s.raw_row_payload, s.units_sold, s.reported_soh, s.raw_period_ref,
               coalesce(s.site_label, s.raw_location_token, '')
        from fact_customer_sellthrough f
        join import_customer_sellthrough_staging_line s on s.fact_sellthrough_row_id = f.id and s.import_job_id = f.import_job_id
        where s.apply_status = 'applied'
          and f.id in (select fact_sellthrough_row_id from import_customer_sellthrough_staging_line
                       where apply_status = 'applied' group by fact_sellthrough_row_id, import_job_id having count(*) > 1)
        order by f.id, s.id
        """
    ).fetchall()
    groups: dict[int, list] = {}
    for r in rows:
        groups.setdefault(r[0], []).append(r)
    diff_keys: Counter = Counter()
    soh_same = soh_diff = 0
    shown: set[int] = set()
    for fid, g in groups.items():
        if len({x[8] for x in g}) > 1:
            continue  # site-merged, not a repeat
        keys = set().union(*(x[4].keys() for x in g))
        differing = tuple(sorted(k for k in keys if not k.startswith("_") and len({repr(x[4].get(k)) for x in g}) > 1))
        diff_keys[(g[0][1], differing)] += 1
        sohs = {x[6] for x in g if x[6] is not None}
        if sohs:
            if len(sohs) == 1:
                soh_same += 1
            else:
                soh_diff += 1
        if g[0][1] not in shown:
            shown.add(g[0][1])
            print(f"customer {g[0][1]} fact {fid} stored units {g[0][2]} soh {g[0][3]}")
            for x in g:
                print("   units", x[5], "soh", x[6], "ref", x[7], {k: x[4].get(k) for k in differing})
    print("differing columns by customer:")
    for (cust, cols), n in diff_keys.most_common():
        print(f"   customer {cust}: {n} groups differ in {cols}")
    print("on-hand within a group: same", soh_same, "different", soh_diff)
