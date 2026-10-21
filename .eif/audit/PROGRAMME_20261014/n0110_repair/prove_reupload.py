"""N-0110 repair clone proof: re-uploading the same file leaves sell-through totals unchanged
except where the old load under-counted.

Clone cip -> cip_n0110p, alembic round trip for 20261015_0038, then re-upload one pre-change
file twice through the real pipeline (process + apply). Prints per-customer unit totals before,
after the first and after the second re-upload, and each difference with its reason.
Writes N0110_REUPLOAD_PROOF.md beside this file and drops the clone.

usage: python prove_reupload.py <old_job_id> [<old_job_id> ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = [sys.executable, str(HERE.parent / "n0110" / "dbrun.py")]
CLONE = "cip_n0110p"
lines: list[str] = []


def log(text: str) -> None:
    print(text, flush=True)
    lines.append(text)


def run(db: str, *cmd: str) -> str:
    out = subprocess.run(RUN + [db, "--", *cmd], capture_output=True, text=True)
    for ln in out.stdout.splitlines():
        if ln.startswith("current_database()"):
            log(f"  [{ln}]")
    if out.returncode != 0:
        raise SystemExit(f"failed {cmd}: {out.stdout[-2000:]} {out.stderr[-2000:]}")
    return out.stdout


def totals(db: str) -> dict[str, list]:
    out = run(db, "python", str(HERE / "reupload.py"), "totals")
    return json.loads([ln for ln in out.splitlines() if ln.startswith("{")][-1])


def superseded(db: str) -> list:
    code = (
        "from app.db.session_sync import SessionLocal\nfrom sqlalchemy import text\nimport json\n"
        "with SessionLocal() as s:\n"
        "    print('current_database()=' + s.execute(text('select current_database()')).scalar())\n"
        "    r = s.execute(text('select superseded_by_import_job_id, import_job_id, customer_id, count(*), sum(units_sold), "
        "count(distinct period_start_date) from fact_customer_sellthrough_superseded group by 1,2,3 order by 1,2,3')).all()\n"
        "    print(json.dumps([[a, b, c, d, float(e), f] for a, b, c, d, e, f in r]))\n"
    )
    out = run(db, "python", "-c", code)
    return json.loads([ln for ln in out.splitlines() if ln.startswith("[")][-1])


BREAKDOWN = """
with new_rows as (
    select product_id, period_start_date p, count(*) n, sum(units_sold) u
    from fact_customer_sellthrough where import_job_id = :job group by 1, 2
), old_rows as (
    select product_id, period_start_date p, count(*) n, sum(units_sold) u
    from fact_customer_sellthrough_superseded where superseded_by_import_job_id = :job group by 1, 2
), staged_old as (
    -- what the old load read: its resolved source rows, by product and the period it stored them under
    select f.product_id, f.period_start_date p, sum(s.units_sold) u
    from fact_customer_sellthrough_superseded f
    join import_customer_sellthrough_staging_line s on s.import_job_id = f.import_job_id
         and s.resolved_product_id = f.product_id and s.period_start_date = f.period_start_date
         and s.resolution_status = 'resolved' and s.units_sold is not null
    where f.superseded_by_import_job_id = :job group by 1, 2
)
select
  coalesce(sum(case when o.p is not null and n.p is not null then n.u - o.u end), 0) as same_period_more_rows,
  coalesce(sum(case when o.p is not null and n.p is not null and n.n > o.n then n.n - o.n end), 0) as extra_site_rows,
  coalesce(sum(case when o.p is null then n.u end), 0) as period_not_stored_before,
  coalesce(sum(case when n.p is null then -o.u end), 0) as old_period_not_restated,
  coalesce((select sum(u) from staged_old), 0) as old_load_read_units,
  coalesce((select sum(u) from old_rows), 0) as old_load_stored_units
from new_rows n full outer join old_rows o on o.product_id = n.product_id and o.p = n.p
"""


def breakdown(db: str, job: int) -> None:
    code = (
        "from app.db.session_sync import SessionLocal\n"
        "from sqlalchemy import text\n"
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "from prove_reupload import BREAKDOWN\n"
        "with SessionLocal() as s:\n"
        "    print('current_database()=' + s.execute(text('select current_database()')).scalar())\n"
        "    r = s.execute(text(BREAKDOWN), {'job': %d}).one()\n"
        "    print(json.dumps([float(x) for x in r]))\n"
    ) % (str(HERE), job)
    out = run(db, "python", "-c", code)
    a, b, c, d, e, f = json.loads([ln for ln in out.splitlines() if ln.startswith("[")][-1])
    log(
        f"  reason for job {job}: same week and product, now one row per site: {a:+g} units "
        f"({b:g} more rows); weeks the old load did not store: {c:+g}; old weeks not restated: {d:+g}. "
        f"The old load read {e:g} units from its resolved source rows and stored {f:g} (last row per key won)."
    )


def show(label: str, t: dict) -> None:
    rows = sum(v[0] for v in t.values())
    units = sum(v[1] for v in t.values())
    log(f"- {label}: fact rows {rows}, units {units:g}, per customer {{" + ", ".join(f"{k}: {v[1]:g}" for k, v in t.items()) + "}")


def diff(a: dict, b: dict) -> dict[str, tuple[float, float, int, int]]:
    out = {}
    for k in sorted(set(a) | set(b), key=int):
        ua, ub = (a.get(k) or [0, 0.0]), (b.get(k) or [0, 0.0])
        if ua[1] != ub[1] or ua[0] != ub[0]:
            out[k] = (ua[1], ub[1], ua[0], ub[0])
    return out


def main() -> int:
    jobs = [int(a) for a in sys.argv[1:]]
    subprocess.run([sys.executable, str(HERE / "clone.py"), "make", CLONE], check=True)
    run(CLONE, "python", "-m", "alembic", "upgrade", "head")
    run(CLONE, "python", "-m", "alembic", "downgrade", "-1")
    run(CLONE, "python", "-m", "alembic", "upgrade", "head")
    log("- alembic on clone: upgrade head, downgrade -1, upgrade head: ok")
    before = totals(CLONE)
    show("before", before)
    ok = True
    for old in jobs:
        prev = totals(CLONE)
        out1 = run(CLONE, "python", str(HERE / "reupload.py"), "apply", str(old))
        first = json.loads([ln for ln in out1.splitlines() if ln.startswith("{")][-1])
        log("  first re-upload " + json.dumps(first))
        breakdown(CLONE, int(first["new_job"]))
        after1 = totals(CLONE)
        show(f"after first re-upload of job {old}", after1)
        out2 = run(CLONE, "python", str(HERE / "reupload.py"), "apply", str(old))
        log("  second re-upload " + [ln for ln in out2.splitlines() if ln.startswith("{")][-1])
        after2 = totals(CLONE)
        show(f"after second re-upload of job {old}", after2)
        d1 = diff(prev, after1)
        d2 = diff(after1, after2)
        for k, (ua, ub, ra, rb) in d1.items():
            log(f"  difference customer {k}: units {ua:g} -> {ub:g} ({ub - ua:+g}), rows {ra} -> {rb}")
        log(f"  second re-upload changed: {d2 or 'nothing'}")
        ok = ok and not d2
    for s in superseded(CLONE):
        log(
            f"  superseded by job {s[0]}: from job {s[1]}, customer {s[2]}, rows {s[3]}, units {s[4]:g}, "
            f"periods {s[5]}"
        )
    subprocess.run([sys.executable, str(HERE / "clone.py"), "drop", CLONE], check=True)
    log("- clone dropped. REUPLOAD_PROOF " + ("PASS" if ok else "FAIL"))
    (HERE / "N0110_REUPLOAD_PROOF.md").write_text(
        "# N-0110 repair: re-upload proof (clone of cip)\n\n" + "\n".join(lines) + "\n", encoding="utf-8"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
