"""N-0039 scratch copy for the repair proof.

User ``cip`` has no CREATEDB privilege, so ``cip_n0039_clone`` cannot be created
(``permission denied to create database``, see clone_create.log). Fallback per the node:
``cip_test``, isolated in its own schema ``n0039`` so cip_test's ``public`` is untouched.

The schema is built from a schema-only ``pg_dump`` of just the needed tables in cip and
the rows from a data-only ``pg_dump`` of the same tables (``public.`` rewritten to
``n0039.``). cip is only read (pg_dump). ``drop`` removes the scratch schema.

Usage: python clone_db.py create | drop
"""
import os
import re
import subprocess
import sys
import tempfile

import psycopg

TARGET_DB = "cip_test"
SCHEMA = "n0039"
TABLES = ["customer_listing", "listing_observation", "dim_product"]
BIN = r"C:\Program Files\PostgreSQL\18\bin"
CONN = dict(host="localhost", port=5432, user="cip", password="cip")
ENV = {**os.environ, "PGPASSWORD": CONN["password"]}
BASE = ["-h", "localhost", "-p", "5432", "-U", "cip"]


def target():
    c = psycopg.connect(dbname=TARGET_DB, autocommit=True, **CONN)
    db = c.execute("select current_database()").fetchone()[0]
    print("target current_database() =", db)
    assert db == TARGET_DB, db
    return c


def _dump(kind: str, out: str) -> None:
    tflags = [x for t in TABLES for x in ("-t", f"public.{t}")]
    subprocess.run(
        [os.path.join(BIN, "pg_dump.exe"), *BASE, "-d", "cip", "-Fp", f"--{kind}-only",
         "--no-owner", "--no-privileges", *tflags, "-f", out],
        check=True, env=ENV,
    )


def _psql(path: str) -> None:
    r = subprocess.run(
        [os.path.join(BIN, "psql.exe"), *BASE, "-d", TARGET_DB, "-q", "-f", path],
        env=ENV, capture_output=True, text=True,
    )
    errs = [ln for ln in r.stderr.splitlines() if "ERROR" in ln]
    print(f"  psql {os.path.basename(path)}: exit {r.returncode}; {len(errs)} ERROR lines")
    for ln in errs[:12]:
        print("   ", ln[:220])


def create() -> None:
    with target() as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        c.execute(f'CREATE SCHEMA "{SCHEMA}"')
    tmp = tempfile.mkdtemp(prefix="n0039_")
    schema_sql, data_sql = os.path.join(tmp, "schema.sql"), os.path.join(tmp, "data.sql")
    _dump("schema", schema_sql)
    _dump("data", data_sql)
    with open(schema_sql, encoding="utf-8") as f:
        s = f.read()
    # Retarget every object to the scratch schema; FKs to tables not copied
    # (e.g. dim_customer) then fail and are reported below, which is expected.
    s = s.replace("public.", f"{SCHEMA}.")
    s = re.sub(r"^CREATE SCHEMA .*$", "", s, flags=re.M)
    with open(schema_sql, "w", encoding="utf-8") as f:
        f.write(s)
    with open(data_sql, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    lines = [
        ln.replace("public.", f"{SCHEMA}.", 1)
        if ln.startswith("COPY public.") or ln.startswith("SELECT pg_catalog.setval('public.")
        else ln
        for ln in lines
    ]
    with open(data_sql, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("schema-only dump ->", SCHEMA)
    _psql(schema_sql)
    print("data-only dump ->", SCHEMA)
    _psql(data_sql)
    with target() as c:
        for t in TABLES:
            print(f"  {SCHEMA}.{t}:", c.execute(f'select count(*) from "{SCHEMA}".{t}').fetchone()[0])
        print("  public.customer_listing (untouched):", c.execute("select count(*) from public.customer_listing").fetchone()[0])


def drop() -> None:
    with target() as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        n = c.execute("select count(*) from pg_namespace where nspname = %s", (SCHEMA,)).fetchone()[0]
        print(f"dropped schema {SCHEMA} in {TARGET_DB}; remaining matches = {n}")


if __name__ == "__main__":
    {"create": create, "drop": drop}[sys.argv[1]]()
