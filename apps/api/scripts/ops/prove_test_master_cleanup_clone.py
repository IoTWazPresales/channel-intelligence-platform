#!/usr/bin/env python3
"""Clone proof for scripts/ops/cleanup_test_masters.py. Never runs on ``cip``.

On a disposable pg_dump copy of cip, runs the cleanup script itself (as the app role, the way it would run
on cip) and checks:

1. The dry run changes nothing and its plan equals the plan ``--expect-plan`` names (the one read on cip).
2. ``--apply`` without ``--expect-db``, or with the wrong name, is refused and changes nothing.
3. All or nothing: an apply forced to fail after its last delete and the audit write changes nothing.
4. The apply removes exactly the planned rows: every table's count drops by the plan's count for it and no
   other table changes; every other row of the tables it touches, and of every table pointing at a
   customer, distributor or product, is byte-identical; removed records are gone, kept ones are still there.
5. The audit event holds every removed row in full, equal to the row before the delete.
6. A second dry run finds nothing more to remove and keeps the same records.

Usage (from apps/api, with CIP_CLONE_ADMIN_URL set to an owner URL; it is never printed):
  python scripts/ops/prove_test_master_cleanup_clone.py --db cip_tmc --create-from cip --drop --expect-plan <plan> --out FILE
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import LINES, create_clone, db_name, drop_clone, say, swap_db  # noqa: E402

SCRIPT = API_ROOT / "scripts" / "ops" / "cleanup_test_masters.py"


def run_cleanup(env: dict[str, str], *args: str) -> tuple[int, str]:
    out = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(API_ROOT), env=env, capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def plan_of(output: str) -> str | None:
    m = re.search(r"\(plan ([0-9a-f]{16})\)", output)
    return m.group(1) if m else None


def summary(output: str) -> list[str]:
    return [ln for ln in output.splitlines() if re.match(r"\s+(customers|distributors|products): remove", ln)]


def table_counts(db) -> dict[str, int]:
    from sqlalchemy import text

    tables = db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
    ).scalars().all()
    return {t: db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables}


def fingerprints(db, tables: list[str], pk: dict[str, str], skip: dict[str, list]) -> dict[str, str]:
    """md5 over every row of each table, leaving out the rows the plan removes."""
    from sqlalchemy import text

    out = {}
    for t in tables:
        out[t] = db.execute(
            text(
                f'SELECT md5(coalesce(string_agg(md5(x::text), \'\' ORDER BY x."{pk[t]}"), \'\')) '
                f'FROM "{t}" x WHERE NOT (x."{pk[t]}" = ANY(:ids))'
            ),
            {"ids": skip.get(t) or []},
        ).scalar()
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="disposable database to run on (never cip)")
    p.add_argument("--create-from", help="make --db as a pg_dump copy of this database first (needs CIP_CLONE_ADMIN_URL)")
    p.add_argument("--drop", action="store_true", help="drop --db at the end")
    p.add_argument("--expect-plan", help="the plan the dry run printed on cip; the clone's must match")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args()
    if args.db == "cip":
        raise SystemExit("STOP: never cip")
    admin = os.environ.get("CIP_CLONE_ADMIN_URL", "").strip() or None
    if args.create_from and not admin:
        raise SystemExit("STOP: --create-from needs CIP_CLONE_ADMIN_URL")
    settings = get_settings()
    app_sync = swap_db(settings.database_url_sync, args.db)
    if db_name(app_sync) != args.db:
        raise SystemExit("STOP: the URL does not point at the clone")
    say(f"Test master cleanup clone proof on {args.db} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
    if args.create_from:
        create_clone(admin, args.create_from, args.db)

    env = {k: v for k, v in os.environ.items() if k not in ("CIP_CLONE_ADMIN_URL", "DATABASE_URL_SYNC_MIGRATE")}
    env.update(DATABASE_URL=swap_db(settings.database_url, args.db), DATABASE_URL_SYNC=app_sync)

    from sqlalchemy import create_engine, text

    from app.db.sync_url import sqlalchemy_sync_engine_url

    engine = create_engine(sqlalchemy_sync_engine_url(app_sync))
    ok = True
    try:
        with engine.connect() as db:
            if db.execute(text("SELECT current_database()")).scalar() != args.db:
                raise SystemExit("STOP: connected to the wrong database")
            say(f"connected as {db.execute(text('SELECT current_user')).scalar()} to {args.db}")
            db.rollback()

            say("\n== 1. Dry run")
            before = table_counts(db)
            db.rollback()
            code, out = run_cleanup(env)
            plan = plan_of(out)
            say(f"  exit {code}; plan {plan}; " + "; ".join(s.strip() for s in summary(out)))
            same = table_counts(db) == before
            db.rollback()
            say(f"  nothing changed: {'YES' if same else 'NO'}")
            ok &= same and code == 0
            if args.expect_plan:
                match = plan == args.expect_plan
                say(f"  plan equals the one read on cip ({args.expect_plan}): {'YES' if match else 'NO'}")
                ok &= match

            # The plan's rows and the tables to fingerprint, read the way the script reads them.
            from scripts.ops.cleanup_test_masters import MASTERS, Plan

            pl = Plan(db)
            doomed_rows = {k: r.data for k, r in pl.doomed.items()}
            by_table: dict[str, list] = {}
            for t, pk in pl.doomed:
                by_table.setdefault(t, []).append(pk)
            kept = sorted(pl.blocked)
            removed_records = sorted(pl.removable)
            watched = sorted(
                {t for t in by_table}
                | {r.child for r in pl.schema.refs if r.parent in MASTERS}
            )
            prints_before = fingerprints(db, watched, pl.schema.pk, by_table)
            db.rollback()
            say(f"  plan rows: {sum(len(v) for v in by_table.values())} in {len(by_table)} tables; "
                f"fingerprinting {len(watched)} tables (every table that points at a master, and every table touched)")

            say("\n== 2. Refusals")
            for label, extra in (("no --expect-db", ["--apply"]), ("--expect-db cip", ["--apply", "--expect-db", "cip"])):
                code, out = run_cleanup(env, *extra)
                same = table_counts(db) == before
                db.rollback()
                refused = code == 2 and "refused" in out
                say(f"  {label}: refused {'YES' if refused else 'NO'} (exit {code}); nothing changed: {'YES' if same else 'NO'}")
                ok &= refused and same

            say("\n== 3. All or nothing")
            code, out = run_cleanup(env, "--apply", "--expect-db", args.db, "--fail-before-commit")
            same = table_counts(db) == before
            db.rollback()
            rolled = code == 3 and "ROLLED BACK" in out
            say(f"  forced failure after the deletes and the audit write: rolled back {'YES' if rolled else 'NO'} "
                f"(exit {code}); nothing changed: {'YES' if same else 'NO'}")
            ok &= rolled and same

            say("\n== 4. Apply")
            audit_before = db.execute(text("SELECT coalesce(max(id), 0) FROM platform_audit_event")).scalar()
            db.rollback()
            code, out = run_cleanup(env, "--apply", "--expect-db", args.db)
            say(f"  exit {code}; " + next((ln for ln in out.splitlines() if ln.startswith("removed:")), "no removed line"))
            ok &= code == 0 and "committed" in out
            after = table_counts(db)
            expected = {t: n - len(by_table.get(t, [])) for t, n in before.items()}
            expected["platform_audit_event"] = before["platform_audit_event"] + 1
            diffs = {t: (before[t], after.get(t), expected[t]) for t in before if after.get(t) != expected[t]}
            say(f"  every table's count is before minus the plan (audit +1): {'YES' if not diffs else 'NO ' + str(diffs)}")
            ok &= not diffs
            prints_after = fingerprints(db, watched, pl.schema.pk, by_table)
            changed = [t for t in watched if prints_before[t] != prints_after[t]]
            say(f"  every other row of the {len(watched)} watched tables identical: {'YES' if not changed else 'NO ' + str(changed)}")
            ok &= not changed
            gone = all(
                db.execute(text(f"SELECT count(*) FROM {t} WHERE id = :i"), {"i": i}).scalar() == 0 for t, i in removed_records
            )
            still = all(
                db.execute(text(f"SELECT count(*) FROM {t} WHERE id = :i"), {"i": i}).scalar() == 1 for t, i in kept
            )
            say(f"  {len(removed_records)} removed records gone: {'YES' if gone else 'NO'}; "
                f"{len(kept)} kept records still there: {'YES' if still else 'NO'}")
            ok &= gone and still

            say("\n== 5. Audit event")
            ev = db.execute(
                text("SELECT id, area, action, actor, detail_json FROM platform_audit_event WHERE id > :a ORDER BY id"),
                {"a": audit_before},
            ).all()
            db.rollback()
            if len(ev) != 1:
                say(f"  expected one new event, found {len(ev)}")
                ok = False
            else:
                e = ev[0]
                rows = e.detail_json["rows_removed"]
                n = sum(len(v) for v in rows.values())
                full = all(
                    json.dumps(r, sort_keys=True, default=str)
                    == json.dumps(doomed_rows[(t, r[pl.schema.pk[t]])], sort_keys=True, default=str)
                    for t, rs in rows.items()
                    for r in rs
                )
                say(f"  event {e.id} ({e.area}/{e.action}, actor {e.actor}): {n} rows in {len(rows)} tables; "
                    f"equals the plan: {'YES' if n == len(doomed_rows) else 'NO'}; every row in full, as before the "
                    f"delete: {'YES' if full else 'NO'}; kept records listed: {len(e.detail_json['kept_records'])}")
                ok &= n == len(doomed_rows) and full and len(e.detail_json["kept_records"]) == len(kept)

            say("\n== 6. Second dry run")
            code, out = run_cleanup(env)
            s = summary(out)
            nothing = all(re.search(r"remove 0,", ln) for ln in s)
            kept_again = len(re.findall(r"-> KEEP", out))
            say(f"  exit {code}; " + "; ".join(x.strip() for x in s))
            say(f"  nothing more to remove: {'YES' if nothing else 'NO'}; same records kept ({kept_again} of {len(kept)}): "
                f"{'YES' if kept_again == len(kept) else 'NO'}")
            ok &= code == 0 and nothing and kept_again == len(kept)
    finally:
        engine.dispose()
        if args.drop and args.create_from:
            drop_clone(admin, args.db)

    say(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    if args.out:
        Path(args.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
