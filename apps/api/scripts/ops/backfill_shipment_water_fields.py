#!/usr/bin/env python3
"""On the water: fill the new voyage columns on existing shipment rows from ``raw_source_row``.

The columns come from migration 20261101_0049 and are empty on every row loaded before it. This reads each
row's own ``raw_source_row`` with the mapping its job was loaded with (``import_job.field_mapping``, so the
headers are the ones the operator confirmed) plus the mapping layer's header aliases for the new fields
(the saved mappings predate them), and parses the cells the way a fresh import does
(``services/imports/shipment_voyage.py``). It fills a column only where it is NULL: nothing already set is
changed, and a second run plans nothing.

Covers ``shipment_evidence_observation`` and ``fact_inbound_shipment`` (D4: not the evidence line). An
observation's hash does not cover these columns (``_OBSERVATION_HASH_COLS``), so no observation is re-keyed.

  python scripts/ops/backfill_shipment_water_fields.py                      dry run: read-only, prints the plan
  python scripts/ops/backfill_shipment_water_fields.py --apply --expect-db cip_test

``--apply`` needs ``--expect-db`` equal to ``current_database()``. It runs in ONE transaction: each table's
filled count per field is checked against the plan, one ``platform_audit_event`` (admin,
``shipment_water_backfill``) records the per-job and per-field counts, and any difference rolls everything back.
The database is the one in DATABASE_URL_SYNC. Never run it on ``cip`` before Warren says "run against cip".
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402

from app.models.shipment_water import WATER_DATE_FIELDS, WATER_FIELDS  # noqa: E402

# D4 (20261103_0052): the evidence line no longer carries the payload, so it is not a target; the observation is.
TABLES = ("shipment_evidence_observation", "fact_inbound_shipment")
BATCH = 2000
SQL_TYPE = {name: ("date" if name in WATER_DATE_FIELDS else "text") for name in WATER_FIELDS}


class JobMapping:
    """canonical -> file header for one job: its saved mapping, plus the aliases for the new fields."""

    def __init__(self, saved: dict[str, Any] | None, headers: list[str], tenant_id: str) -> None:
        from app.services.imports.shipment_evidence_import import _src_to_canonical_rev
        from app.services.imports.shipment_field_mapping import build_initial_shipment_field_mapping
        from app.services.imports.shipment_voyage import tenant_shipping_method_pattern

        rev = dict(_src_to_canonical_rev(dict(saved or {})) or {})
        for header, target in build_initial_shipment_field_mapping(headers, None).items():
            if target in WATER_FIELDS and target not in rev:
                rev[target] = header
        self.header_by_canonical = rev
        self.pattern = tenant_shipping_method_pattern(tenant_id)

    def fields(self, raw: dict[str, Any]) -> dict[str, Any]:
        from app.services.imports.shipment_evidence_import import _parse_date
        from app.services.imports.shipment_voyage import voyage_fields

        picked: dict[str, Any] = {name: raw.get(self.header_by_canonical.get(name, "")) for name in WATER_FIELDS}
        legacy = self.header_by_canonical.get("shipway")
        picked["shipway"] = raw.get(legacy) if legacy else None
        return voyage_fields(picked, parse_date=_parse_date, pattern=self.pattern)


def jobs_of(conn, table: str) -> list[tuple[int | None, int]]:
    return [
        (r[0], r[1])
        for r in conn.execute(
            text(f"SELECT import_job_id, count(*) FROM {table} GROUP BY 1 ORDER BY 1 NULLS FIRST")
        ).all()
    ]


def job_info(conn, job_id: int | None) -> tuple[dict[str, Any], str, str]:
    if job_id is None:
        return {}, "default", "(no job)"
    row = conn.execute(
        text("SELECT field_mapping, tenant_id, file_name FROM import_job WHERE id = :j"), {"j": job_id}
    ).first()
    if row is None:
        return {}, "default", "(job removed)"
    return dict(row[0] or {}), str(row[1] or "default"), str(row[2])


def plan_table(conn, table: str, only_job: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(updates, report). An update is {id, <field>: value} holding only the fields to fill on that row."""
    updates: list[dict[str, Any]] = []
    per_job: dict[str, Any] = {}
    cols = ", ".join(WATER_FIELDS)
    for job_id, n in jobs_of(conn, table):
        if only_job is not None and job_id != only_job:
            continue
        saved, tenant, file_name = job_info(conn, job_id)
        where = "import_job_id IS NULL" if job_id is None else "import_job_id = :j"
        params = {} if job_id is None else {"j": job_id}
        headers = [
            r[0]
            for r in conn.execute(
                text(f"SELECT DISTINCT jsonb_object_keys(raw_source_row) FROM {table} WHERE {where}"), params
            ).all()
        ]
        mapping = JobMapping(saved, headers, tenant)
        filled: dict[str, int] = defaultdict(int)
        differs: dict[str, int] = defaultdict(int)
        rows_touched = 0
        # Per statement: Connection.execution_options() would stay on the connection and turn the later UPDATE
        # into a server-side cursor too.
        result = conn.execute(
            text(f"SELECT id, raw_source_row, {cols} FROM {table} WHERE {where}"),
            params,
            execution_options={"stream_results": True, "max_row_buffer": BATCH},
        )
        for row in result:
            current = {name: row[2 + i] for i, name in enumerate(WATER_FIELDS)}
            computed = mapping.fields(row[1] if isinstance(row[1], dict) else {})
            change: dict[str, Any] = {}
            for name in WATER_FIELDS:
                new, old = computed[name], current[name]
                if new is None:
                    continue
                if old is None:
                    change[name] = new
                    filled[name] += 1
                elif old != new:
                    differs[name] += 1  # already set to something else: left alone, and counted
            if change:
                rows_touched += 1
                updates.append({"id": row[0], **change})
        per_job[f"{job_id}"] = {
            "file": file_name,
            "rows": n,
            "rows_filled": rows_touched,
            "filled": dict(sorted(filled.items())),
            "already_set_and_different": dict(sorted(differs.items())),
        }
    return updates, per_job


def apply_updates(conn, table: str, updates: list[dict[str, Any]]) -> None:
    for start in range(0, len(updates), BATCH):
        chunk = updates[start : start + BATCH]
        sets = ", ".join(f"{n} = COALESCE(t.{n}, v.{n})" for n in WATER_FIELDS)
        arrays = ", ".join(f"CAST(:a_{n} AS {SQL_TYPE[n]}[])" for n in WATER_FIELDS)
        names = ", ".join(WATER_FIELDS)
        params: dict[str, Any] = {"ids": [u["id"] for u in chunk]}
        for n in WATER_FIELDS:
            params[f"a_{n}"] = [u.get(n) for u in chunk]
        conn.execute(
            text(
                f"UPDATE {table} t SET {sets} FROM unnest(CAST(:ids AS integer[]), {arrays}) "
                f"AS v(id, {names}) WHERE t.id = v.id"
            ),
            params,
        )


def non_null_counts(conn, table: str) -> dict[str, int]:
    exprs = ", ".join(f"count({n})" for n in WATER_FIELDS)
    row = conn.execute(text(f"SELECT {exprs} FROM {table}")).one()
    return {n: int(row[i]) for i, n in enumerate(WATER_FIELDS)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="write the plan (needs --expect-db)")
    p.add_argument("--expect-db", default=None, help="required with --apply; must equal current_database()")
    p.add_argument("--job", type=int, default=None, help="only this import job (rehearsal)")
    p.add_argument("--out", default=None, help="also write the report to this file")
    p.add_argument("--json-out", default=None, help="write the per-table, per-job, per-field counts to this JSON file")
    p.add_argument("--fail-before-commit", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    lines: list[str] = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        lines.append(msg)

    from app.db.session_sync import sync_engine

    code = 0
    with sync_engine.connect() as conn:
        if not args.apply:
            conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            conn.commit()
        db = conn.execute(text("SELECT current_database()")).scalar()
        role = conn.execute(text("SELECT current_user")).scalar()
        ro = conn.execute(text("SHOW transaction_read_only")).scalar()
        say(f"current_database() = {db}; role {role}; transaction_read_only = {ro}; "
            f"{'APPLY' if args.apply else 'dry run, nothing is changed'}")
        if args.apply and args.expect_db != db:
            say(f"refused: --apply needs --expect-db {db!r} (got {args.expect_db!r})")
            return 2
        if not args.apply and ro != "on":
            say("STOP: the dry run is not read-only")
            return 2
        has_cols = conn.execute(
            text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'fact_inbound_shipment' AND column_name = 'port_eta_date'")
        ).scalar()
        if not has_cols:
            say("STOP: migration 20261101_0049 is not applied to this database")
            return 2

        plans: dict[str, list[dict[str, Any]]] = {}
        report: dict[str, Any] = {}
        before: dict[str, dict[str, int]] = {}
        for table in TABLES:
            before[table] = non_null_counts(conn, table)
            plans[table], report[table] = plan_table(conn, table, args.job)

        total: dict[str, dict[str, int]] = {}
        for table in TABLES:
            say(f"\n{table}: {sum(j['rows'] for j in report[table].values()):,} rows; "
                f"{len(plans[table]):,} to fill")
            total[table] = defaultdict(int)  # type: ignore[assignment]
            for job, rec in report[table].items():
                if not rec["rows_filled"] and not rec["already_set_and_different"]:
                    say(f"  job {job} ({rec['file']}): {rec['rows']:,} rows, nothing to fill")
                    continue
                per = ", ".join(f"{k} {v:,}" for k, v in rec["filled"].items())
                say(f"  job {job} ({rec['file']}): {rec['rows']:,} rows, {rec['rows_filled']:,} filled: {per}")
                if rec["already_set_and_different"]:
                    say(f"      left alone, already set to another value: {rec['already_set_and_different']}")
                for k, v in rec["filled"].items():
                    total[table][k] += v
            say(f"  {table} per field to fill: " + (", ".join(f"{k} {v:,}" for k, v in sorted(total[table].items())) or "none"))

        if args.json_out:
            import json

            Path(args.json_out).write_text(
                json.dumps({"database": db, "per_table_per_job": report, "per_table_per_field": {t: dict(v) for t, v in total.items()}}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        if args.apply:
            try:
                for table in TABLES:
                    apply_updates(conn, table, plans[table])
                for table in TABLES:
                    after = non_null_counts(conn, table)
                    for n in WATER_FIELDS:
                        got = after[n] - before[table][n]
                        want = total[table].get(n, 0)
                        if got != want:
                            raise RuntimeError(f"{table}.{n}: filled {got}, plan says {want}")
                    say(f"  {table}: counts after the write equal the plan")
                from sqlalchemy.orm import Session

                from app.services.platform_audit import record_platform_audit_sync

                with Session(bind=conn) as session:
                    record_platform_audit_sync(
                        session,
                        None,
                        area="admin",
                        action="shipment_water_backfill",
                        target_type="shipment_tables",
                        target_id="20261101_0049",
                        actor_label="scripts/ops/backfill_shipment_water_fields.py",
                        detail={"per_table_per_job": report, "per_table_per_field": {t: dict(v) for t, v in total.items()}},
                    )
                    session.flush()
                if args.fail_before_commit:
                    raise RuntimeError("forced failure before commit (rehearsal)")
                conn.commit()
                say("committed")
            except Exception as exc:  # noqa: BLE001 - any failure rolls everything back
                conn.rollback()
                say(f"ROLLED BACK, nothing changed: {exc}")
                code = 3
        else:
            conn.rollback()
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
