#!/usr/bin/env python3
"""Clone proof for migration 20261101_0049 and scripts/ops/backfill_shipment_water_fields.py. Never runs on ``cip``.

On a disposable pg_dump copy of cip it checks:

1. The migration upgrades cip's head (20261023_0048) and changes nothing that was there: every table's row count
   and a fingerprint of every row of the three shipment tables (all columns except the new ones) are identical.
   Downgrade and upgrade again, with the same result. ``port_condition`` is append-only for the app role.
2. The model matches the migrated database on the three shipment tables (schema_drift_report): only the one
   deliberate difference (``fact_upsert_key`` NOT NULL on the database, nullable in the model) remains.
3. The backfill's dry run is read-only and changes nothing; ``--apply`` without ``--expect-db`` or with the wrong
   name is refused; an apply forced to fail after the write rolls everything back.
4. The apply fills the new columns: the script's per-job, per-field plan equals an independent SQL recount, every
   filled date and text equals the value computed in SQL straight from ``raw_source_row``, and every other column of
   every row (including each observation's ``source_row_hash``) is byte-identical to before.
5. A second apply plans nothing. Downgrade with the data present, upgrade, apply again: same counts.
6. One ``platform_audit_event`` holds the counts.

Usage (from apps/api; the owner login is read from PG_OWNER or CIP_CLONE_ADMIN_URL and never printed):
  python scripts/ops/prove_on_the_water_clone.py --db cip_otw --create-from cip --drop --out FILE
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.models.shipment_water import WATER_DATE_FIELDS, WATER_FIELDS  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import LINES, alembic, create_clone, db_name, drop_clone, say, swap_db  # noqa: E402

TABLES = ("shipment_evidence_line", "shipment_evidence_observation", "fact_inbound_shipment")
BACKFILL = API_ROOT / "scripts" / "ops" / "backfill_shipment_water_fields.py"
DRIFT = API_ROOT / "scripts" / "ops" / "schema_drift_report.py"
ARRAY = "ARRAY[" + ", ".join(f"'{n}'" for n in WATER_FIELDS) + "]"

# SQL read of each field straight from the raw header (an independent second reading of raw_source_row).
HEADER_SQL = {
    "on_board_date": "On-Board Date",
    "port_eta_date": "ETA Date(Est Port Arrival)",
    "port_ata_date": "ATA Date(Actual Port Arrival)",
    "shipping_method": "Shipping Method",
    "deliver_port": "Deliver Port",
}


def admin_url(settings) -> str:
    given = os.environ.get("CIP_CLONE_ADMIN_URL", "").strip()
    if given:
        return given
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url_sync.replace("+psycopg", "").replace("+asyncpg", ""))
    from app.db.sync_url import sqlalchemy_sync_engine_url

    return sqlalchemy_sync_engine_url(
        url.set(username="postgres", password=os.environ["PG_OWNER"], database="postgres").render_as_string(hide_password=False)
    )


def counts(db) -> dict[str, int]:
    from sqlalchemy import text

    tables = db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")).scalars().all()
    return {t: db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables}


def fingerprint(db) -> dict[str, str]:
    """md5 of every row of the three shipment tables, leaving out the new columns."""
    from sqlalchemy import text

    out = {}
    for t in TABLES:
        out[t] = db.execute(
            text(
                f"SELECT md5(coalesce(string_agg(md5((to_jsonb(x) - {ARRAY})::text), '' ORDER BY x.id), '')) FROM {t} x"
            )
        ).scalar()
    return out


def water_nonnull(db) -> dict[str, dict[str, int]]:
    from sqlalchemy import text

    out: dict[str, dict[str, int]] = {}
    for t in TABLES:
        row = db.execute(text("SELECT " + ", ".join(f"count({n})" for n in WATER_FIELDS) + f" FROM {t}")).one()
        out[t] = {n: int(row[i]) for i, n in enumerate(WATER_FIELDS)}
    return out


def has_water_columns(db) -> bool:
    from sqlalchemy import text

    return bool(
        db.execute(
            text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'fact_inbound_shipment' AND column_name = 'port_eta_date'")
        ).scalar()
    )


def run_backfill(env: dict[str, str], *args: str) -> tuple[int, str]:
    out = subprocess.run([sys.executable, "-X", "utf8", str(BACKFILL), *args], cwd=str(API_ROOT), env=env, capture_output=True, text=True, encoding="utf-8")
    return out.returncode, out.stdout + out.stderr


def sql_cross_check(db) -> list[str]:
    """Rows whose stored value differs from the value SQL reads from raw_source_row (expected: none)."""
    from sqlalchemy import text

    problems: list[str] = []
    for t in TABLES:
        for col, header in HEADER_SQL.items():
            raw = f"raw_source_row ->> '{header}'"
            if col in WATER_DATE_FIELDS:
                expected = (
                    f"CASE WHEN {raw} ~ '^(19|20)[0-9]{{2}}-[0-9]{{2}}-[0-9]{{2}}' THEN substring({raw} from 1 for 10)::date END"
                )
            else:
                expected = f"NULLIF(btrim({raw}), '')"
            bad = db.execute(text(f"SELECT count(*) FROM {t} WHERE {col} IS DISTINCT FROM {expected}")).scalar()
            if bad:
                problems.append(f"{t}.{col}: {bad} rows differ from the SQL reading of '{header}'")
        ship_way = (
            "coalesce(NULLIF(btrim(raw_source_row ->> 'Ship Way'), ''), NULLIF(btrim(raw_source_row ->> 'Shipway'), ''), "
            "NULLIF(btrim(raw_source_row ->> 'shipway'), ''))"
        )
        bad = db.execute(text(f"SELECT count(*) FROM {t} WHERE ship_way IS DISTINCT FROM {ship_way}")).scalar()
        if bad:
            problems.append(f"{t}.ship_way: {bad} rows differ from the SQL reading of Ship Way / shipway")
        # The ACZA "Container Number" is an internal 5-digit number, never an ISO container number.
        bad = db.execute(text(f"SELECT count(*) FROM {t} WHERE container_no IS NOT NULL")).scalar()
        if bad:
            problems.append(f"{t}.container_no: {bad} rows hold a value (the ACZA headers must leave it empty)")
    return problems


def per_job_nonnull(db, table: str) -> dict[str, dict[str, int]]:
    from sqlalchemy import text

    exprs = ", ".join(f"count({n})" for n in WATER_FIELDS)
    out = {}
    for r in db.execute(text(f"SELECT import_job_id, {exprs} FROM {table} GROUP BY 1 ORDER BY 1 NULLS FIRST")).all():
        out[str(r[0])] = {n: int(r[1 + i]) for i, n in enumerate(WATER_FIELDS) if r[1 + i]}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="disposable database to run on (never cip)")
    p.add_argument("--create-from", help="make --db as a pg_dump copy of this database first")
    p.add_argument("--drop", action="store_true", help="drop --db at the end")
    p.add_argument("--reset", action="store_true", help="rerun on an existing clone: downgrade it to cip's head first")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args()
    if args.db == "cip":
        raise SystemExit("STOP: never cip")
    settings = get_settings()
    admin = admin_url(settings)
    app_sync = swap_db(settings.database_url_sync, args.db)
    if db_name(app_sync) != args.db:
        raise SystemExit("STOP: the URL does not point at the clone")
    say(f"On the water clone proof on {args.db} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
    if args.create_from:
        create_clone(admin, args.create_from, args.db)

    os.environ["DATABASE_URL"] = swap_db(settings.database_url, args.db)
    os.environ["DATABASE_URL_SYNC"] = app_sync
    os.environ.pop("DATABASE_URL_SYNC_MIGRATE", None)
    get_settings.cache_clear()
    owner_sync = swap_db(admin, args.db)
    env_app = dict(os.environ, DATABASE_URL_SYNC=app_sync)
    env_owner = dict(os.environ, DATABASE_URL_SYNC=app_sync, DATABASE_URL_SYNC_MIGRATE=owner_sync)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.db.sync_url import sqlalchemy_sync_engine_url

    engine = create_engine(sqlalchemy_sync_engine_url(app_sync))
    db = Session(bind=engine)
    if db.scalar(text("SELECT current_database()")) != args.db:
        raise SystemExit("STOP: connected to the wrong database")
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and cond
        say(f"  {'PASS' if cond else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")

    if args.reset:
        say(f"reset: {args.db} taken back to cip's head (20261023_0048) before the proof")
        alembic(env_owner, "downgrade", "20261023_0048")
    say("\n== 1. Migration 20261101_0049")
    say(f"  before: alembic {alembic(env_owner, 'current')}")
    c0, f0 = counts(db), fingerprint(db)
    db.rollback()
    say(f"  rows: evidence lines {c0['shipment_evidence_line']:,}, observations {c0['shipment_evidence_observation']:,}, facts {c0['fact_inbound_shipment']:,}")
    alembic(env_owner, "upgrade", "head")
    c1, f1 = counts(db), fingerprint(db)
    cols1 = has_water_columns(db)
    db.rollback()
    check("after upgrade: new columns exist, every table's row count is unchanged except the new port_condition",
          cols1 and {k: v for k, v in c1.items() if k != "port_condition"} == c0 and c1.get("port_condition") == 0)
    check("after upgrade: every shipment row is byte-identical on its existing columns", f1 == f0)
    nn = water_nonnull(db)
    db.rollback()
    check("after upgrade: the new columns are all empty", all(v == 0 for t in nn.values() for v in t.values()))
    alembic(env_owner, "downgrade", "-1")
    c2, f2 = counts(db), fingerprint(db)
    gone = not has_water_columns(db)
    db.rollback()
    check("after downgrade: columns and port_condition gone, counts and fingerprints as before", gone and c2 == c0 and f2 == f0)
    alembic(env_owner, "upgrade", "head")
    c3, f3 = counts(db), fingerprint(db)
    db.rollback()
    check("after the second upgrade: as after the first", {k: v for k, v in c3.items() if k != "port_condition"} == c0 and f3 == f0)

    say("\n  port_condition is append-only for the app role (a transaction that is rolled back)")
    probe = Session(bind=engine)
    probe.execute(text("INSERT INTO port_condition (tenant_id, port_code, delay_days, note, entered_by) VALUES ('default','ZADUR',15,'proof','proof')"))
    seen = probe.execute(text("SELECT count(*) FROM port_condition")).scalar()
    refusals = []
    for stmt in ("UPDATE port_condition SET delay_days = 1", "DELETE FROM port_condition"):
        try:
            with probe.begin_nested():
                n = probe.execute(text(stmt)).rowcount
            refusals.append(f"{stmt.split()[0]} changed {n} rows")
        except Exception as exc:  # noqa: BLE001
            refusals.append(f"{stmt.split()[0]} refused ({type(exc.orig).__name__ if hasattr(exc, 'orig') else type(exc).__name__})")
    probe.rollback()
    probe.close()
    check("insert works, update and delete do nothing or are refused", seen == 1 and all("changed 0" in r or "refused" in r for r in refusals), "; ".join(refusals))

    say("\n== 2. Models against the migrated clone (the three shipment tables)")
    out = subprocess.run(
        [sys.executable, "-W", "ignore", str(DRIFT), "--url", app_sync, "--tables", ",".join(TABLES) + ",port_condition"],
        cwd=str(API_ROOT), env=env_app, capture_output=True, text=True, encoding="utf-8",
    )
    drift = [ln for ln in out.stdout.splitlines() if "\t" in ln]
    for ln in drift:
        say("    " + ln)
    check("only the deliberate difference remains", len(drift) == 1 and "fact_upsert_key" in drift[0] and "nullable" in drift[0], f"{len(drift)} difference(s)")

    say("\n== 3. Backfill guards")
    rc, text_out = run_backfill(env_app)
    after_dry = water_nonnull(db)
    f_dry = fingerprint(db)
    db.rollback()
    say("  dry run: " + text_out.splitlines()[0])
    check("dry run is read-only and changes nothing", rc == 0 and "transaction_read_only = on" in text_out and all(v == 0 for t in after_dry.values() for v in t.values()) and f_dry == f0)
    rc, text_out = run_backfill(env_app, "--apply")
    check("--apply without --expect-db is refused", rc == 2 and "refused" in text_out)
    rc, text_out = run_backfill(env_app, "--apply", "--expect-db", "cip")
    check("--apply with the wrong database name is refused", rc == 2 and "refused" in text_out)
    rc, text_out = run_backfill(env_app, "--apply", "--expect-db", args.db, "--fail-before-commit")
    forced = water_nonnull(db)
    db.rollback()
    check("an apply forced to fail after the write rolls everything back", rc == 3 and "ROLLED BACK" in text_out and all(v == 0 for t in forced.values() for v in t.values()))

    say("\n== 4. Backfill apply")
    with tempfile.TemporaryDirectory() as tmp:
        j1 = str(Path(tmp) / "run1.json")
        rc, out1 = run_backfill(env_app, "--apply", "--expect-db", args.db, "--json-out", j1)
        plan1 = json.loads(Path(j1).read_text(encoding="utf-8"))
    for ln in out1.splitlines():
        say("  " + ln)
    check("apply committed", rc == 0 and "committed" in out1)
    n1 = water_nonnull(db)
    f_after = fingerprint(db)
    c_after = counts(db)
    bad = sql_cross_check(db)
    sql_jobs = {t: per_job_nonnull(db, t) for t in TABLES}
    audit = db.execute(text("SELECT count(*), max(detail_json::text) FROM platform_audit_event WHERE action = 'shipment_water_backfill'")).one()
    db.rollback()
    say("\n  per table, per field (filled by the apply):")
    for t in TABLES:
        say(f"    {t}: " + ", ".join(f"{k} {v:,}" for k, v in n1[t].items() if v))
    check("filled counts per field equal the plan's", all({k: v for k, v in n1[t].items() if v} == dict(plan1["per_table_per_field"][t]) for t in TABLES))
    same_jobs = True
    for t in TABLES:
        planned = {j: rec["filled"] for j, rec in plan1["per_table_per_job"][t].items() if rec["filled"]}
        actual = {j: {k: v for k, v in rec.items() if v} for j, rec in sql_jobs[t].items() if rec}
        if planned != actual:
            same_jobs = False
            say(f"    per-job counts differ on {t}: plan {planned} vs SQL {actual}")
    check("per-job, per-field counts equal an independent SQL recount", same_jobs)
    check("every stored value equals the SQL reading of raw_source_row", not bad, "; ".join(bad))
    check("every other column of every shipment row is byte-identical (including source_row_hash)", f_after == f0)
    check("no table gained or lost a row", {k: v for k, v in c_after.items() if k not in ("port_condition", "platform_audit_event")} == {k: v for k, v in c0.items() if k != "platform_audit_event"})
    check("one audit event holds the counts", audit[0] == 1 and audit[1] is not None)

    say("\n  forwarder and origin hub read from each distinct Shipping Method (facts):")
    for r in db.execute(text("SELECT shipping_method, forwarder_code, origin_hub, count(*) n FROM fact_inbound_shipment WHERE shipping_method IS NOT NULL GROUP BY 1,2,3 ORDER BY 4 DESC")).all():
        say(f"    {r[3]:>6}  {r[0]!r:<34} forwarder={r[1]!r} hub={r[2]!r}")
    for r in db.execute(text("SELECT ship_way, count(*) FROM shipment_evidence_line GROUP BY 1 ORDER BY 2 DESC")).all():
        say(f"    ship_way {r[0]!r}: {r[1]:,} evidence lines")
    db.rollback()

    say("\n== 5. Idempotence and the round trip with data")
    rc, out2 = run_backfill(env_app)
    check("a second dry run plans nothing", rc == 0 and len(re.findall(r"; 0 to fill", out2)) == 3)
    rc, out3 = run_backfill(env_app, "--apply", "--expect-db", args.db)
    n2 = water_nonnull(db)
    db.rollback()
    check("a second apply changes nothing", rc == 0 and n2 == n1)
    alembic(env_owner, "downgrade", "-1")
    f_down, c_down, gone = fingerprint(db), counts(db), not has_water_columns(db)
    db.rollback()
    check("downgrade with the data present leaves every other column and row as it was", gone and f_down == f0 and {k: v for k, v in c_down.items() if k not in ("platform_audit_event",)} == {k: v for k, v in c0.items() if k != "platform_audit_event"})
    alembic(env_owner, "upgrade", "head")
    with tempfile.TemporaryDirectory() as tmp:
        j2 = str(Path(tmp) / "run2.json")
        rc, _ = run_backfill(env_app, "--apply", "--expect-db", args.db, "--json-out", j2)
        plan2 = json.loads(Path(j2).read_text(encoding="utf-8"))
    n3 = water_nonnull(db)
    db.rollback()
    check("upgrade and apply again: the same counts", rc == 0 and n3 == n1 and plan2["per_table_per_field"] == plan1["per_table_per_field"])

    db.close()
    engine.dispose()
    say(f"\nRESULT: {'ALL PASS' if ok else 'FAILED - see FAIL lines'}")
    if args.drop and args.create_from:
        drop_clone(admin, args.db)
    if args.out:
        Path(args.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
