"""Census of test-run data on cip (READ ONLY). Prints current_database() first and stops unless it is cip.

Every transaction is read-only (SET SESSION CHARACTERISTICS ... READ ONLY), so this cannot write.

A test job is an import_job whose file name equals a ``filename=`` value in apps/api/tests, or whose
raw file storage key starts ``imports/test/``. Jobs whose name only matches a ``file_name=`` value or
an upload tuple in the tests are listed separately: those names are common and may be real uploads.

Usage (from apps/api):
  python scripts/ops/cip_test_leak_census.py                  full census
  python scripts/ops/cip_test_leak_census.py --ids            the test job ids only, comma-separated
  python scripts/ops/cip_test_leak_census.py --jobs 1675,1679 what the Import Center delete does with each row
                                                              (the delete's own preview gives exact counts)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from app.db.session_sync import sync_engine  # noqa: E402
from app.services.customer_test_fixtures import is_test_fixture_customer  # noqa: E402

TESTS = API_ROOT / "tests"
FILENAME_RE = re.compile(r"""\bfilename\s*=\s*["']([^"'{}]+)["']""")
OTHER_NAME_RES = (
    re.compile(r"""\bfile_name\s*=\s*["']([^"'{}]+)["']"""),
    re.compile(r"""\(\s*["']([^"'{}]+\.(?:csv|xlsx|xls))["']\s*,"""),
)
# Codes and names Warren listed, plus the customer names the leaking DSI tests send.
FIXTURE_CUSTOMER_CODES = ("CUST-1001",)
FIXTURE_CUSTOMER_NAMES = (
    "Metro Market Group",
    "Jane Doe - STAFF",
    "John Roe - STAFF",
    "Nobody Known Ltd",
    "ACME WIDGETS (PTY) LTD",
)
FIXTURE_CUSTOMER_NAME_PREFIXES = ("steward map dealer",)
FIXTURE_DISTRIBUTOR_CODES = ("DIST-01",)
FIXTURE_DISTRIBUTOR_NAMES = ("Summit Supply Co.",)
# test_distributor_sales_inventory_import.py mints "Novel Disti NOVEL-DIST-<hex>" provisional distributors.
FIXTURE_DISTRIBUTOR_NAME_PREFIXES = ("Novel Disti ",)
FIXTURE_PRODUCT_SKUS = ("SKU-ALPHA-01",)

NAMED_TABLES = (
    "fact_sales_sellout",
    "fact_returns",
    "fact_inventory_distributor",
    "fact_customer_sellthrough",
    "customer_stock_position",
    "fact_customer_sellthrough_superseded",
    "fact_distributor_line_superseded",
)


def test_file_names() -> tuple[set[str], set[str]]:
    primary: set[str] = set()
    other: set[str] = set()
    for path in TESTS.rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        primary.update(FILENAME_RE.findall(src))
        for rx in OTHER_NAME_RES:
            other.update(rx.findall(src))
    return primary, other - primary


def job_columns(conn: Connection) -> list[tuple[str, str]]:
    """(table, column) for every column that holds an import_job id: real FKs plus the superseded tables."""
    fks = conn.execute(
        text(
            """
            SELECT cl.relname, a.attname
            FROM pg_constraint con
            JOIN pg_class cl ON cl.oid = con.conrelid
            JOIN pg_class rf ON rf.oid = con.confrelid
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
            WHERE con.contype = 'f' AND rf.relname = 'import_job'
            """
        )
    ).all()
    loose = conn.execute(
        text(
            """
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name LIKE '%import_job_id'
            """
        )
    ).all()
    return sorted({(t, c) for t, c in [*fks, *loose]})


# What import_job_bulk_delete.bulk_delete_import_jobs does with each column, by explicit statement.
BULK_DELETE_REMOVES = {
    ("fact_sales_sellout", "source_import_job_id"),
    ("fact_inventory_distributor", "source_import_job_id"),
    ("fact_competitor_price", "source_job_id"),
    ("entity_mapping_queue", "job_id"),
    ("shipment_evidence_line", "import_job_id"),
    ("import_distributor_si_staging_line", "import_job_id"),
    ("import_entity_mapping_candidate", "import_job_id"),
    ("import_row_result", "job_id"),
    ("raw_file_metadata", "job_id"),
    ("historical_lineup_import_header", "import_job_id"),
}
BULK_DELETE_ALIASES = {
    "customer_source_token_alias",
    "channel_source_token_alias",
    "region_source_token_alias",
    "distributor_source_token_alias",
}
BULK_DELETE_CLEARS = {("commercial_lineup_case", "import_job_id"), ("catalog_product", "last_import_job_id")}
# N-0112: the delete removes these, or gives each row back the figures of the newest load that stays.
BULK_DELETE_RESTORES = {
    ("fact_returns", "import_job_id"),
    ("fact_customer_sellthrough", "import_job_id"),
    ("fact_inbound_shipment", "import_job_id"),
    ("fact_customer_sellthrough_superseded", "import_job_id"),
    ("fact_customer_sellthrough_superseded", "superseded_by_import_job_id"),
    ("fact_distributor_line_superseded", "previous_import_job_id"),
    ("fact_distributor_line_superseded", "superseded_by_import_job_id"),
}
# N-0112: recomputed for every customer or distributor the delete touches.
BULK_DELETE_RECOMPUTES = {
    "customer_stock_position",
    "fact_customer_velocity",
    "fact_dsi_forecast",
    "fact_inventory_reconciliation",
    "weeks_of_cover_observation",
    "customer_cst_report_slot",
}
# Kept on purpose, job link cleared (import_job_delete_figures.KEPT_LINKS).
BULK_DELETE_KEEPS = {"cpor_claim_evidence_line", "cpor_payment_evidence", "cst_listing_seed", "customer_sellthrough_layout"}
FK_ON_DELETE = {"c": "cascade", "n": "set null", "d": "set default", "a": "no action", "r": "restrict"}


def fk_actions(conn: Connection) -> dict[tuple[str, str], str]:
    rows = conn.execute(
        text(
            """
            SELECT cl.relname, a.attname, con.confdeltype
            FROM pg_constraint con
            JOIN pg_class cl ON cl.oid = con.conrelid
            JOIN pg_class rf ON rf.oid = con.confrelid
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
            WHERE con.contype = 'f' AND rf.relname = 'import_job'
            """
        )
    ).all()
    return {(t, c): FK_ON_DELETE.get(k, k) for t, c, k in rows}


def job_delete_check(conn: Connection, job_ids: list[int]) -> None:
    """Every row pointing at these jobs, and what the Import Center delete (with N-0112) does with it."""
    found = set(conn.execute(text("SELECT id FROM import_job WHERE id = ANY(:ids)"), {"ids": job_ids}).scalars())
    print(f"\n== Delete check for jobs {', '.join(map(str, job_ids))} (found: {', '.join(map(str, sorted(found))) or 'none'})")
    actions = fk_actions(conn)
    views = set(
        conn.execute(text("SELECT table_name FROM information_schema.views WHERE table_schema = 'public'")).scalars()
    )
    pairs = sorted(set(job_columns(conn)) | {("fact_competitor_price", "source_job_id"), ("entity_mapping_queue", "job_id")})
    left_behind = 0
    for table, col in pairs:
        if col not in columns(conn, table):
            continue
        for jid, n in conn.execute(
            text(f"SELECT {col}, count(*) FROM {table} WHERE {col} = ANY(:ids) GROUP BY 1 ORDER BY 1"), {"ids": job_ids}
        ):
            fk = actions.get((table, col))
            if table in views:
                verdict = "a view over other tables: follows them"
            elif (table, col) in BULK_DELETE_REMOVES:
                verdict = "removed (or, for a fact row, given back the figures of the newest load that stays)"
            elif (table, col) in BULK_DELETE_RESTORES:
                verdict = "removed, or given back the figures of the newest load that stays"
            elif table in BULK_DELETE_RECOMPUTES:
                verdict = "recomputed for the customers and distributors touched"
            elif table in BULK_DELETE_ALIASES:
                verdict = "kept unless 'also delete learned aliases' is ticked (job link cleared)"
            elif (table, col) in BULK_DELETE_CLEARS or table in BULK_DELETE_KEEPS:
                verdict = "row kept, job link cleared"
            elif fk == "cascade":
                verdict = "removed (cascade when the job row goes)"
            elif fk == "set null":
                verdict = "LEFT BEHIND: row kept, job link set to null"
                left_behind += n
            elif fk in ("no action", "restrict"):
                verdict = "BLOCKS the delete (foreign key, not removed first)"
                left_behind += n
            else:
                verdict = "LEFT BEHIND: no foreign key, row keeps pointing at a deleted job"
                left_behind += n
            print(f"  job {jid}: {table}.{col} = {n:<5} -> {verdict}")
    print(f"  rows the delete would leave or trip on: {left_behind}")


def entity_refs(conn: Connection, target: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        text(
            """
            SELECT cl.relname, a.attname
            FROM pg_constraint con
            JOIN pg_class cl ON cl.oid = con.conrelid
            JOIN pg_class rf ON rf.oid = con.confrelid
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
            WHERE con.contype = 'f' AND rf.relname = :t
            """
        ),
        {"t": target},
    ).all()
    return sorted(set(rows))


def columns(conn: Connection, table: str) -> set[str]:
    return set(
        conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:t"),
            {"t": table},
        ).scalars()
    )


# The fact tables a real load writes, with the column that names the load.
FACT_JOB_COLUMN = {
    "fact_sales_sellout": "source_import_job_id",
    "fact_returns": "import_job_id",
    "fact_inventory_distributor": "source_import_job_id",
    "fact_customer_sellthrough": "import_job_id",
    "customer_stock_position": "report_import_job_id",
}


def real_fact_refs(conn: Connection, entity_col: str, ids: list[int], test_ids: list[int]) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = defaultdict(dict)
    if not ids:
        return out
    for table, job_col in FACT_JOB_COLUMN.items():
        if entity_col not in columns(conn, table):
            continue
        q = text(
            f"""
            SELECT {entity_col}, count(*) FILTER (WHERE {job_col} IS NOT NULL AND NOT ({job_col} = ANY(:test))),
                   count(*) FILTER (WHERE {job_col} IS NULL)
            FROM {table} WHERE {entity_col} = ANY(:ids) GROUP BY 1
            """
        )
        for eid, real, nojob in conn.execute(q, {"ids": ids, "test": test_ids or [0]}):
            if real:
                out[eid][table] = real
            if nojob:
                out[eid][f"{table} (no load recorded)"] = nojob
    return out


def main(argv: list[str]) -> int:
    ids_only = "--ids" in argv
    check_jobs: list[int] = []
    if "--jobs" in argv:
        check_jobs = [int(x) for x in argv[argv.index("--jobs") + 1].split(",") if x.strip()]
    with sync_engine.connect() as conn:
        # The session setting applies from the next transaction, so end the one the SET opened.
        conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.commit()
        read_only = conn.execute(text("SHOW transaction_read_only")).scalar()
        db = conn.execute(text("SELECT current_database()")).scalar()
        print(f"current_database() = {db}; transaction_read_only = {read_only}")
        if read_only != "on":
            print("STOP: the session is not read-only.")
            return 2
        if db != "cip":
            print("STOP: not cip.")
            return 2

        if check_jobs:
            job_delete_check(conn, check_jobs)
            conn.rollback()
            return 0

        primary, other = test_file_names()
        storage_jobs = set(
            conn.execute(text("SELECT DISTINCT job_id FROM raw_file_metadata WHERE storage_key LIKE 'imports/test/%'")).scalars()
        )
        jobs = conn.execute(
            text(
                """
                SELECT j.id, j.template_slug, j.import_mode, j.stage, j.status, j.file_name, j.created_at,
                       (SELECT min(r.storage_key) FROM raw_file_metadata r WHERE r.job_id = j.id) AS storage_key
                FROM import_job j
                WHERE j.file_name = ANY(:names) OR j.file_name = ANY(:other) OR j.id = ANY(:storage)
                ORDER BY j.id
                """
            ),
            {"names": sorted(primary), "other": sorted(other), "storage": sorted(storage_jobs) or [0]},
        ).all()
        test_jobs = [j for j in jobs if j.file_name in primary or j.id in storage_jobs]
        maybe_jobs = [j for j in jobs if j not in test_jobs]
        test_ids = [j.id for j in test_jobs]
        if ids_only:
            print(f"{len(test_ids)} test jobs:")
            print(",".join(map(str, test_ids)))
            print(f"{len(maybe_jobs)} name-only jobs (not in the list above):")
            print(",".join(str(j.id) for j in maybe_jobs))
            conn.rollback()
            return 0

        print(f"\n== 1. Import jobs from tests: {len(test_jobs)} "
              f"({len(primary)} filename= values in apps/api/tests; {len(storage_jobs)} jobs with an imports/test/ key)")
        for j in test_jobs:
            why = "name+key" if (j.file_name in primary and j.id in storage_jobs) else ("name" if j.file_name in primary else "key")
            print(f"  job {j.id:>5}  {j.template_slug or '-':<32} {j.import_mode:<8} {j.stage:<22} {j.status:<12} "
                  f"{j.created_at:%Y-%m-%d %H:%M}  {j.file_name}  [{why}] {j.storage_key or ''}")
        for must in (1672, 1673, 1674, 1675):
            if must not in test_ids:
                print(f"  NOTE: job {must} is not in this list")
        print(f"\n   Jobs whose name only matches a file_name= value or upload tuple in tests (may be real): {len(maybe_jobs)}")
        for j in maybe_jobs:
            print(f"  job {j.id:>5}  {j.template_slug or '-':<32} {j.import_mode:<8} {j.stage:<22} {j.status:<12} "
                  f"{j.created_at:%Y-%m-%d %H:%M}  {j.file_name}  {j.storage_key or ''}")

        print("\n== 2. Rows per test job (every column that holds an import_job id)")
        per_job: dict[int, dict[str, int]] = defaultdict(dict)
        totals: dict[str, int] = defaultdict(int)
        for table, col in job_columns(conn):
            q = text(f"SELECT {col}, count(*) FROM {table} WHERE {col} = ANY(:ids) GROUP BY 1")
            for jid, n in conn.execute(q, {"ids": test_ids or [0]}):
                label = table if col in ("import_job_id", "source_import_job_id", "job_id") else f"{table}.{col}"
                per_job[jid][label] = per_job[jid].get(label, 0) + n
                totals[label] += n
        for jid in test_ids:
            row = per_job.get(jid, {})
            print(f"  job {jid}: " + (", ".join(f"{k}={v}" for k, v in sorted(row.items())) or "no rows anywhere"))
        print("  totals: " + (", ".join(f"{k}={v}" for k, v in sorted(totals.items())) or "none"))
        missing = [t for t in NAMED_TABLES if not any(k.startswith(t) for k in totals)]
        print("  zero rows from test jobs in: " + ", ".join(missing))

        print("\n== 3. Masters and aliases created by tests")
        test_job_customers = set()
        test_job_distributors = set()
        for table, job_col in FACT_JOB_COLUMN.items():
            cols = columns(conn, table)
            for ent, bucket in (("customer_id", test_job_customers), ("distributor_id", test_job_distributors)):
                if ent in cols:
                    bucket.update(
                        conn.execute(
                            text(f"SELECT DISTINCT {ent} FROM {table} WHERE {job_col} = ANY(:ids) AND {ent} IS NOT NULL"),
                            {"ids": test_ids or [0]},
                        ).scalars()
                    )
        cust_rows = conn.execute(
            text("SELECT id, code, name, customer_status, created_at, merged_into_customer_id FROM dim_customer")
        ).all()
        name_set = {n.lower() for n in FIXTURE_CUSTOMER_NAMES}
        flagged = {}
        for r in cust_rows:
            reasons = []
            if r.code in FIXTURE_CUSTOMER_CODES:
                reasons.append("fixture code")
            nm = (r.name or "").strip().lower()
            if nm in name_set or nm.startswith(FIXTURE_CUSTOMER_NAME_PREFIXES):
                reasons.append("fixture name")
            if is_test_fixture_customer(r.code, r.name):
                reasons.append("is_test_fixture_customer")
            if r.id in test_job_customers:
                reasons.append("in test-job facts")
            if reasons:
                flagged[r.id] = (r, reasons)
        refs = real_fact_refs(conn, "customer_id", list(flagged), test_ids)
        print(f"  dim_customer: {len(flagged)} rows flagged")
        for cid, (r, reasons) in sorted(flagged.items()):
            rr = refs.get(cid, {})
            print(f"    {cid:>6} {r.code or '-':<20} {(r.name or '')[:40]:<40} {r.customer_status or '-':<11} "
                  f"{r.created_at:%Y-%m-%d}  [{', '.join(reasons)}]  real-load rows: "
                  + (", ".join(f"{k}={v}" for k, v in sorted(rr.items())) or "0"))

        dist_rows = conn.execute(text("SELECT id, code, name, created_at FROM dim_distributor")).all()
        dflag = {
            r.id: r
            for r in dist_rows
            if r.code in FIXTURE_DISTRIBUTOR_CODES
            or (r.name or "") in FIXTURE_DISTRIBUTOR_NAMES
            or (r.name or "").startswith(FIXTURE_DISTRIBUTOR_NAME_PREFIXES)
            or r.id in test_job_distributors
        }
        drefs = real_fact_refs(conn, "distributor_id", list(dflag), test_ids)
        print(f"  dim_distributor: {len(dflag)} rows flagged (fixture code/name or in test-job facts)")
        for did, r in sorted(dflag.items()):
            rr = drefs.get(did, {})
            print(f"    {did:>6} {r.code or '-':<20} {(r.name or '')[:40]:<40} {r.created_at:%Y-%m-%d}  real-load rows: "
                  + (", ".join(f"{k}={v}" for k, v in sorted(rr.items())) or "0"))

        prod = conn.execute(
            text("SELECT id, sku, created_at FROM dim_product WHERE sku = ANY(:s)"), {"s": list(FIXTURE_PRODUCT_SKUS)}
        ).all()
        prefs = real_fact_refs(conn, "product_id", [p.id for p in prod], test_ids)
        print(f"  dim_product: {len(prod)} rows with fixture SKUs")
        for p in prod:
            rr = prefs.get(p.id, {})
            print(f"    {p.id:>6} {p.sku:<20} {p.created_at:%Y-%m-%d}  real-load rows: "
                  + (", ".join(f"{k}={v}" for k, v in sorted(rr.items())) or "0"))

        alias_tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                "AND table_name LIKE '%alias%' AND table_type='BASE TABLE' ORDER BY 1"
            )
        ).scalars().all()
        print("  alias tables (rows learned from a test job | rows pointing at a flagged customer):")
        for t in alias_tables:
            cols = columns(conn, t)
            job_col = next((c for c in ("created_from_import_job_id", "import_job_id", "job_id") if c in cols), None)
            by_job = (
                conn.execute(text(f"SELECT count(*) FROM {t} WHERE {job_col} = ANY(:ids)"), {"ids": test_ids or [0]}).scalar()
                if job_col
                else None
            )
            by_cust = (
                conn.execute(text(f"SELECT count(*) FROM {t} WHERE customer_id = ANY(:ids)"), {"ids": list(flagged) or [0]}).scalar()
                if "customer_id" in cols
                else None
            )
            print(f"    {t:<40} from test job: {'-' if by_job is None else by_job:<6} to flagged customer: "
                  f"{'-' if by_cust is None else by_cust}")
            if by_job:
                target = "customer_id" if "customer_id" in cols else ("distributor_id" if "distributor_id" in cols else None)
                dim = {"customer_id": "dim_customer", "distributor_id": "dim_distributor"}.get(target or "")
                token_col = next((c for c in ("raw_token", "source_token", "token", "normalized_token", "alias") if c in cols), None)
                rows = conn.execute(
                    text(
                        f"SELECT a.id, a.{job_col} AS job, {('a.' + token_col) if token_col else 'NULL'} AS token, "
                        f"{('a.' + target) if target else 'NULL'} AS target, "
                        f"{'d.code, d.name' if dim else 'NULL AS code, NULL AS name'} "
                        f"FROM {t} a {f'LEFT JOIN {dim} d ON d.id = a.{target}' if dim else ''} "
                        f"WHERE a.{job_col} = ANY(:ids) ORDER BY a.id"
                    ),
                    {"ids": test_ids},
                ).all()
                for r in rows:
                    kind = "test fixture" if (target == "customer_id" and r.target in flagged) else (
                        "fixture" if r.code in FIXTURE_DISTRIBUTOR_CODES else "REAL?")
                    real = real_fact_refs(conn, target, [r.target], test_ids).get(r.target, {}) if target and r.target else {}
                    print(f"      alias {r.id} from job {r.job}: {r.token!r} -> {target} {r.target} {r.code} {r.name!r} "
                          f"[{kind}; real-load rows {sum(real.values())}]")

        print("  entities behind the fact rows test jobs left:")
        for table, job_col in FACT_JOB_COLUMN.items():
            cols = columns(conn, table)
            ents = [c for c in ("distributor_id", "customer_id", "product_id") if c in cols]
            if not ents:
                continue
            rows = conn.execute(
                text(
                    f"SELECT {job_col} AS job, {', '.join(ents)}, count(*) AS n, min(transaction_date) AS d0, "
                    f"max(transaction_date) AS d1 FROM {table} WHERE {job_col} = ANY(:ids) "
                    f"GROUP BY {job_col}, {', '.join(ents)} ORDER BY 1"
                )
                if "transaction_date" in cols
                else text(
                    f"SELECT {job_col} AS job, {', '.join(ents)}, count(*) AS n FROM {table} "
                    f"WHERE {job_col} = ANY(:ids) GROUP BY {job_col}, {', '.join(ents)} ORDER BY 1"
                ),
                {"ids": test_ids},
            ).mappings().all()
            for r in rows:
                print(f"    {table}: " + ", ".join(f"{k}={v}" for k, v in r.items()))

        print("\n== 4. Did a test job supersede figures from a real job?")
        cst = conn.execute(
            text(
                "SELECT superseded_by_import_job_id, import_job_id, count(*) FROM fact_customer_sellthrough_superseded "
                "WHERE superseded_by_import_job_id = ANY(:ids) GROUP BY 1, 2 ORDER BY 1, 2"
            ),
            {"ids": test_ids or [0]},
        ).all()
        dsi = conn.execute(
            text(
                "SELECT superseded_by_import_job_id, previous_import_job_id, fact_table, count(*) "
                "FROM fact_distributor_line_superseded WHERE superseded_by_import_job_id = ANY(:ids) "
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
            ),
            {"ids": test_ids or [0]},
        ).all()
        test_set = set(test_ids)
        real_hit = [r for r in cst if r[1] not in test_set] + [r for r in dsi if r[1] not in test_set]
        for r in cst:
            print(f"  sell-through: test job {r[0]} superseded {r[2]} rows of job {r[1]} ({'TEST' if r[1] in test_set else 'REAL'})")
        for r in dsi:
            print(f"  distributor {r[2]}: test job {r[0]} superseded {r[3]} lines of job {r[1]} ({'TEST' if r[1] in test_set else 'REAL'})")
        print("  verdict: " + ("YES, see REAL rows above" if real_hit else "no real job's figures were superseded by a test job"))
        rev = conn.execute(
            text(
                "SELECT count(*) FROM fact_customer_sellthrough_superseded WHERE import_job_id = ANY(:ids) "
                "AND NOT (superseded_by_import_job_id = ANY(:ids))"
            ),
            {"ids": test_ids or [0]},
        ).scalar()
        rev2 = conn.execute(
            text(
                "SELECT count(*) FROM fact_distributor_line_superseded WHERE previous_import_job_id = ANY(:ids) "
                "AND NOT (superseded_by_import_job_id = ANY(:ids))"
            ),
            {"ids": test_ids or [0]},
        ).scalar()
        print(f"  reverse: real jobs superseded test-job figures: sell-through {rev}, distributor {rev2}")
        conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
