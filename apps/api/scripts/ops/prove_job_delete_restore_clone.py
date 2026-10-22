#!/usr/bin/env python3
"""N-0112 clone proof: deleting a job that loaded over real figures gives the real figures back.

Never runs on ``cip``. On a disposable clone of cip (or, as a rehearsal, on cip_test):

1. Migration 20261022_0047 (with an owner URL): upgrade, downgrade, upgrade; superseded record
   counts and policies printed each time.
2. Sell-through: the busiest real customer's latest real load. A test load goes over it (same key
   changed, same key identical, stock-only, another site for the same week), applied with the real
   apply; then the test job is deleted through the Import Center delete. Every fact row, superseded
   record and stock position of that customer must be identical to before.
3. Distributor: the busiest real distributor load. A test load goes over it (sales lines changed,
   identical, new invoices; returns changed and identical), written by the real fact upsert, and
   deleted the same way. Every line of that distributor, its totals and its superseded records must
   be identical to before.
4. All or nothing: a delete that fails at its last step changes nothing.

The preview's counts are compared with the delete's. Output is printed; pass ``--out`` to save it.

Usage (from apps/api):
  python scripts/ops/prove_job_delete_restore_clone.py --db cip_n0112 --create-from cip --drop
  python scripts/ops/prove_job_delete_restore_clone.py --db cip_test            (rehearsal)

``--create-from`` and the migration step need ``CIP_CLONE_ADMIN_URL``: a connection URL for a role
that owns the tables and may create databases (on this machine: ``postgres``), pointing at any
database on the server. It is read from the environment and never printed. The clone is made with
``pg_dump`` / ``pg_restore``, which only read cip; nobody connected to cip is disconnected.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402

LINES: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)
    LINES.append(msg)


def swap_db(url: str, name: str) -> str:
    return re.sub(r"/[^/?]+(\?|$)", rf"/{name}\1", url, count=1) if "://" in url else url


def db_name(url: str) -> str:
    return urlparse(url.replace("+psycopg", "").replace("+asyncpg", "")).path.lstrip("/").split("?")[0]


def pg_bin(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    for base in sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin"), reverse=True):
        exe = base / f"{tool}.exe"
        if exe.exists():
            return str(exe)
    raise SystemExit(f"STOP: {tool} not found")


def pg_env(url: str) -> tuple[list[str], dict[str, str]]:
    u = urlparse(url.replace("+psycopg", "").replace("+asyncpg", ""))
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = unquote(u.password)
    args = ["-h", u.hostname or "127.0.0.1", "-p", str(u.port or 5432), "-U", unquote(u.username or "")]
    return args, env


def create_clone(admin_url: str, source: str, target: str) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(swap_db(admin_url, "postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target}).first():
            raise SystemExit(f"STOP: database {target} already exists; drop it or pick another name")
        conn.execute(text(f'CREATE DATABASE "{target}" OWNER cip'))
    eng.dispose()
    conn_args, env = pg_env(admin_url)
    with tempfile.TemporaryDirectory() as tmp:
        dump = str(Path(tmp) / "cip.dump")
        started = datetime.now(timezone.utc)
        subprocess.run([pg_bin("pg_dump"), *conn_args, "-d", source, "-Fc", "-f", dump], env=env, check=True)
        restore = subprocess.run(
            [pg_bin("pg_restore"), *conn_args, "-d", target, "-j", "4", dump], env=env, capture_output=True, text=True
        )
    say(f"clone {target} restored from a pg_dump of {source} ({(datetime.now(timezone.utc) - started).seconds} s)")
    if restore.returncode != 0:
        # pg_restore exits non-zero on warnings too (an existing public schema); the counts below decide.
        say(f"  pg_restore reported: {restore.stderr.strip().splitlines()[-3:]}")
    tables = (
        "import_job", "fact_sales_sellout", "fact_returns", "fact_inventory_distributor", "fact_customer_sellthrough",
        "fact_customer_sellthrough_superseded", "fact_distributor_line_superseded", "customer_stock_position",
        "import_distributor_si_staging_line", "import_customer_sellthrough_staging_line", "dim_customer",
    )
    counts = {}
    for name in (source, target):
        eng = create_engine(swap_db(admin_url, name))
        with eng.connect() as conn:
            counts[name] = [conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables]
            conn.rollback()
        eng.dispose()
    say(f"  row counts {source} vs {target}: " + ", ".join(f"{t} {a}/{b}" for t, a, b in zip(tables, counts[source], counts[target])))
    if counts[source] != counts[target]:
        raise SystemExit("STOP: the clone does not match its source")


def drop_clone(admin_url: str, target: str) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(swap_db(admin_url, "postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(
            text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"),
            {"n": target},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target}"'))
    eng.dispose()
    say(f"clone {target} dropped")


def alembic(target_env: dict[str, str], *args: str) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=str(API_ROOT), env=target_env, capture_output=True, text=True
    )
    if out.returncode != 0:
        raise SystemExit(f"STOP: alembic {' '.join(args)} failed:\n{out.stderr[-2000:]}")
    return (out.stdout + out.stderr).strip().splitlines()[-1] if (out.stdout + out.stderr).strip() else ""


# --------------------------------------------------------------------------------------- snapshots
def superseded_shape(db) -> tuple:
    from sqlalchemy import text

    return (
        db.scalar(text("SELECT count(*) FROM fact_customer_sellthrough_superseded")),
        db.scalar(text("SELECT count(*) FROM fact_distributor_line_superseded")),
        tuple(
            sorted(
                tuple(r)
                for r in db.execute(
                    text(
                        "SELECT tablename, cmd FROM pg_policies WHERE tablename IN "
                        "('fact_customer_sellthrough_superseded', 'fact_distributor_line_superseded')"
                    )
                ).all()
            )
        ),
    )


def st_snapshot(db, tenant: str, customer: int) -> dict[str, Any]:
    from sqlalchemy import text

    rows = {
        r[0]: (float(r[1]), None if r[2] is None else float(r[2]), None if r[3] is None else float(r[3]),
               None if r[4] is None else float(r[4]), json.dumps(r[5], sort_keys=True), r[6])
        for r in db.execute(
            text(
                "SELECT source_key, units_sold, reported_soh, in_transit_units, on_order_units, figure_import_jobs, "
                "import_job_id FROM fact_customer_sellthrough WHERE tenant_id = :t AND customer_id = :c"
            ),
            {"t": tenant, "c": customer},
        ).all()
    }
    records = sorted(
        tuple(str(x) for x in r)
        for r in db.execute(
            text(
                "SELECT fact_id, source_key, superseded_by_import_job_id, reason, figures, units_sold, reported_soh "
                "FROM fact_customer_sellthrough_superseded WHERE tenant_id = :t AND customer_id = :c"
            ),
            {"t": tenant, "c": customer},
        ).all()
    )
    positions = sorted(
        tuple(str(x) for x in r)
        for r in db.execute(
            text(
                "SELECT product_id, period_grain, period_start_date, reported_on_hand, units_sold, receipts_units, "
                "expected_on_hand, gap_units, status, report_import_job_id FROM customer_stock_position "
                "WHERE tenant_id = :t AND customer_id = :c"
            ),
            {"t": tenant, "c": customer},
        ).all()
    )
    units = sum(v[0] for v in rows.values())
    soh = sum(v[1] or 0 for v in rows.values())
    return {"rows": rows, "records": records, "positions": positions, "units": round(units, 4), "soh": round(soh, 4)}


def dsi_snapshot(db, distributor: int) -> dict[str, Any]:
    from sqlalchemy import text

    sell = {
        r[0]: tuple(None if x is None else str(x) for x in r[1:])
        for r in db.execute(
            text(
                "SELECT source_key, units, revenue, unit_sellout_price_ex_tax_amount, reported_revenue_amount, "
                "computed_revenue_amount, currency_code, source_import_job_id, staging_line_id "
                "FROM fact_sales_sellout WHERE distributor_id = :d"
            ),
            {"d": distributor},
        ).all()
    }
    ret = {
        r[0]: tuple(None if x is None else str(x) for x in r[1:])
        for r in db.execute(
            text(
                "SELECT source_key, return_quantity, unit_price, import_job_id, staging_line_id "
                "FROM fact_returns WHERE distributor_id = :d"
            ),
            {"d": distributor},
        ).all()
    }
    records = sorted(
        tuple(str(x) for x in r)
        for r in db.execute(
            text(
                "SELECT fact_table, source_key, previous_import_job_id, superseded_by_import_job_id, figures "
                "FROM fact_distributor_line_superseded WHERE distributor_id = :d"
            ),
            {"d": distributor},
        ).all()
    )
    units = sum(float(v[0]) for v in sell.values())
    returned = sum(float(v[0]) for v in ret.values())
    return {"sell": sell, "ret": ret, "records": records, "units": round(units, 4), "returns": round(returned, 4)}


def diff(name: str, before: dict, after: dict) -> bool:
    same = True
    for key in before:
        if before[key] != after[key]:
            same = False
            if isinstance(before[key], dict):
                changed = [k for k in set(before[key]) | set(after[key]) if before[key].get(k) != after[key].get(k)]
                say(f"  DIFF {name}.{key}: {len(changed)} keys differ, e.g. {changed[:3]}")
                for k in changed[:3]:
                    say(f"    {k}: before {before[key].get(k)} after {after[key].get(k)}")
            elif isinstance(before[key], list):
                say(f"  DIFF {name}.{key}: {len(before[key])} -> {len(after[key])} entries")
            else:
                say(f"  DIFF {name}.{key}: {before[key]} -> {after[key]}")
    return same


# --------------------------------------------------------------------------------------- scenarios
def st_test_load(db, tenant: str, customer: int, real_job: int) -> int:
    from sqlalchemy import text

    from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
    from app.models.ingestion import ImportJob
    from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

    real = [
        dict(r)
        for r in db.execute(
            text(
                """
                SELECT * FROM fact_customer_sellthrough
                WHERE tenant_id = :t AND customer_id = :c AND import_job_id = :j AND units_sold > 0
                  AND reported_soh IS NOT NULL
                ORDER BY period_start_date DESC, product_id LIMIT 23
                """
            ),
            {"t": tenant, "c": customer, "j": real_job},
        ).mappings()
    ]
    if len(real) < 23:
        raise SystemExit(f"STOP: customer {customer} job {real_job} has only {len(real)} rows with units and on-hand")
    source = db.scalar(text("SELECT source_id FROM import_job WHERE id = :j"), {"j": real_job})
    job = ImportJob(
        tenant_id=tenant, source_id=source, template_slug="customer_sell_through", import_mode="apply",
        status="completed", stage="staged", file_name="N0112 clone proof sell-through test load.xlsx", staged_metadata={},
    )
    db.add(job)
    db.flush()
    plan = (
        [("changed", r) for r in real[0:10]]
        + [("identical", r) for r in real[10:15]]
        + [("stock_only", r) for r in real[15:20]]
        + [("other_site", r) for r in real[20:23]]
    )
    for n, (kind, r) in enumerate(plan, 1):
        units, soh, site, loc = float(r["units_sold"]), float(r["reported_soh"]), r["site_label"], r["customer_location_id"]
        if kind == "changed":
            units, soh = units + 3, soh + 5
        elif kind == "stock_only":
            units, soh = None, soh + 7
        elif kind == "other_site":
            site, loc = f"{site or ''} N0112-TEST-SITE".strip(), None
        db.add(
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id, source_row_number=n, raw_row_payload={"n0112": n, "kind": kind},
                resolved_customer_id=customer, resolved_product_id=r["product_id"], resolved_location_id=loc,
                period_start_date=r["period_start_date"], period_type=r["period_type"], period_grain=r["period_grain"],
                period_week=r["period_week"], period_year=r["period_year"], week_start_date=r["week_start_date"],
                site_label=site, units_sold=units, reported_soh=soh, resolution_status="resolved",
            )
        )
    db.flush()
    summary = apply_customer_sellthrough_staging(db, int(job.id), recompute_stock_gap=True)
    if summary.errors:
        raise SystemExit(f"STOP: test sell-through apply errors {summary.errors[:3]}")
    job.stage, job.status = "loaded", "completed"
    db.commit()
    say(f"  test load job {job.id}: applied {summary.applied}, superseded rows {summary.superseded_rows}, "
        f"partly superseded {summary.superseded_partial_rows}, figures {summary.superseded_figures}")
    return int(job.id)


def dsi_test_load(db, distributor: int, real_job: int) -> int:
    from sqlalchemy import text

    from app.models.import_distributor_si import ImportDistributorSiStagingLine
    from app.models.ingestion import ImportJob
    from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

    sells = [
        dict(r)
        for r in db.execute(
            text("SELECT * FROM fact_sales_sellout WHERE source_import_job_id = :j AND distributor_id = :d ORDER BY id LIMIT 15"),
            {"j": real_job, "d": distributor},
        ).mappings()
    ]
    rets = [
        dict(r)
        for r in db.execute(
            text("SELECT * FROM fact_returns WHERE import_job_id = :j AND distributor_id = :d ORDER BY id LIMIT 5"),
            {"j": real_job, "d": distributor},
        ).mappings()
    ]
    if len(sells) < 15:
        raise SystemExit(f"STOP: job {real_job} has only {len(sells)} sell-out rows")
    source = db.scalar(text("SELECT source_id FROM import_job WHERE id = :j"), {"j": real_job})
    job = ImportJob(
        tenant_id="default", source_id=source, template_slug="distributor_inventory", import_mode="apply",
        status="pending", stage="validated", file_name="N0112 clone proof distributor test load.xlsx", staged_metadata={},
    )
    db.add(job)
    db.flush()
    n = 0

    def line(r: dict, qty: float, invoice: str, kind: str, **figs: Any) -> None:
        nonlocal n
        n += 1
        db.add(
            ImportDistributorSiStagingLine(
                import_job_id=job.id, source_row_number=n, raw_row_payload={"n0112": n, "kind": kind},
                resolved_distributor_id=r["distributor_id"], resolved_customer_id=r["customer_id"],
                resolved_product_id=r["product_id"], resolution_status="resolved", transaction_date=r["transaction_date"],
                invoice_no=invoice, quantity_sold=qty, **figs,
            )
        )

    for i, r in enumerate(sells):
        same = {
            "unit_sellout_price_ex_tax_amount": r["unit_sellout_price_ex_tax_amount"],
            "reported_revenue_amount": r["reported_revenue_amount"],
            "computed_revenue_amount": r["computed_revenue_amount"],
            "currency_code": r["currency_code"],
        }
        if i < 8:
            line(r, float(r["units"]) + 2, r["invoice_no"], "changed", currency_code=r["currency_code"])
        elif i < 12:
            line(r, float(r["units"]), r["invoice_no"], "identical", **same)
        else:
            line(r, 1, f"{r['invoice_no']}-N0112T", "new_invoice", currency_code=r["currency_code"])
    for i, r in enumerate(rets):
        qty = float(r["return_quantity"]) + (1 if i < 3 else 0)
        line(r, -qty, r["invoice_no"], "changed" if i < 3 else "identical", unit_sellout_price_ex_tax_amount=r["unit_price"])
    db.flush()
    sell, _inv, ret, errors = upsert_dsi_facts_for_staging_job(db, job)
    if errors:
        raise SystemExit(f"STOP: test distributor upsert errors {errors[:3]}")
    job.stage, job.status = "loaded", "completed"
    db.commit()
    meta = (job.staged_metadata or {}).get("distributor_si", {})
    say(f"  test load job {job.id}: sell-out lines {sell}, returns {ret}, superseded lines {meta.get('superseded_lines')}")
    return int(job.id)


def seed_real_loads(db) -> list[int]:
    """Rehearsal only (a database with no loads of its own): one sell-through and one distributor load."""
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
    from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
    from app.models.import_distributor_si import ImportDistributorSiStagingLine
    from app.models.ingestion import ImportJob, SourceDefinition
    from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging
    from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

    source = db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1))
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    distributor = db.scalar(select(DimDistributor.id).order_by(DimDistributor.id).limit(1))
    products = list(db.scalars(select(DimProduct.id).order_by(DimProduct.id).limit(23)).all())
    if None in (source, customer, distributor) or not products:
        raise SystemExit("STOP: rehearsal needs a source, a customer, a distributor and a product")
    st = ImportJob(tenant_id="default", source_id=source, template_slug="customer_sell_through", import_mode="apply",
                   status="completed", stage="loaded", file_name="N0112 rehearsal real sell-through.xlsx", staged_metadata={})
    db.add(st)
    db.flush()
    for n in range(1, 24):
        db.add(ImportCustomerSellthroughStagingLine(
            import_job_id=st.id, source_row_number=n, raw_row_payload={"seed": n}, resolved_customer_id=customer,
            resolved_product_id=products[n % len(products)], period_start_date=date(2025, 1, 6) + timedelta(weeks=n),
            period_type="weekly", period_grain="week", site_label="S1", units_sold=10 + n, reported_soh=40 + n,
            resolution_status="resolved"))
    db.flush()
    apply_customer_sellthrough_staging(db, int(st.id), recompute_stock_gap=True)
    dsi = ImportJob(tenant_id="default", source_id=source, template_slug="distributor_inventory", import_mode="apply",
                    status="completed", stage="loaded", file_name="N0112 rehearsal real distributor.xlsx", staged_metadata={})
    db.add(dsi)
    db.flush()
    for n in range(1, 21):
        db.add(ImportDistributorSiStagingLine(
            import_job_id=dsi.id, source_row_number=n, raw_row_payload={"seed": n}, resolved_distributor_id=distributor,
            resolved_customer_id=customer, resolved_product_id=products[n % len(products)], resolution_status="resolved",
            transaction_date=date(2024, 6, 3), invoice_no=f"N0112-SEED-{n}",
            quantity_sold=(n if n <= 15 else -n), reported_revenue_amount=(10 * n if n <= 15 else None),
            unit_sellout_price_ex_tax_amount=(None if n <= 15 else 10)))
    db.flush()
    upsert_dsi_facts_for_staging_job(db, dsi)
    db.commit()
    say(f"  rehearsal seed: real-style sell-through load {st.id} and distributor load {dsi.id}")
    return [int(st.id), int(dsi.id)]


def preview_then_delete(db, job_id: int) -> tuple[dict, dict]:
    from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs, preview_import_job_bulk_delete

    preview = preview_import_job_bulk_delete(db, [job_id])
    db.rollback()
    out = bulk_delete_import_jobs(db, [job_id], delete_semantic_artifacts=False, user=None)
    db.commit()
    shown = Counter(preview["jobs"][0]["counts"])
    done = Counter(out["data"]["per_job"].get(job_id, {}))
    same = all(shown.get(k, 0) == v for k, v in done.items())
    say(f"  preview for job {job_id}: {dict(sorted(preview['jobs'][0]['counts'].items()))}")
    say(f"  delete  for job {job_id}: {dict(sorted(done.items()))}; recomputed {out['data']['totals'].get('customers_recomputed', 0)} "
        f"customers, {out['data']['totals'].get('distributors_recomputed', 0)} distributors")
    say(f"  preview counts equal the delete's: {'YES' if same else 'NO'}")
    return preview, out


def all_or_nothing(db, job_id: int, snap_fn, *args) -> bool:
    """A delete that fails at its last step (the audit write) leaves everything as it was."""
    import app.services.platform_audit as audit

    before = snap_fn(db, *args)
    original = audit.record_platform_audit_sync

    def boom(*_a, **_k):
        raise RuntimeError("forced failure after the data was restored")

    audit.record_platform_audit_sync = boom
    try:
        from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs

        try:
            bulk_delete_import_jobs(db, [job_id], delete_semantic_artifacts=False)
            db.commit()
            return False
        except RuntimeError:
            db.rollback()
    finally:
        audit.record_platform_audit_sync = original
    from app.models.ingestion import ImportJob

    after = snap_fn(db, *args)
    still = db.get(ImportJob, job_id) is not None
    ok = still and before == after
    say(f"  forced failure: job {job_id} still there {still}; figures unchanged {before == after}")
    return ok


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="disposable database to run on (never cip)")
    p.add_argument("--create-from", help="make --db as a pg_dump copy of this database first (needs CIP_CLONE_ADMIN_URL)")
    p.add_argument("--drop", action="store_true", help="drop --db at the end (only when this run created it)")
    p.add_argument("--out", help="also write the report to this file")
    p.add_argument("--seed-real", action="store_true", help="rehearsal on a database with no loads: make the real loads first")
    args = p.parse_args()
    if args.db == "cip":
        raise SystemExit("STOP: never cip")
    if args.seed_real and args.create_from:
        raise SystemExit("STOP: --seed-real is for a rehearsal database, not a clone of cip")
    admin = os.environ.get("CIP_CLONE_ADMIN_URL", "").strip() or None
    if args.create_from and not admin:
        raise SystemExit("STOP: --create-from needs CIP_CLONE_ADMIN_URL")
    settings = get_settings()
    app_sync = swap_db(settings.database_url_sync, args.db)
    if db_name(app_sync) != args.db or args.db == "cip":
        raise SystemExit("STOP: the URL does not point at the clone")
    say(f"N-0112 clone proof on {args.db} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")

    if args.create_from:
        create_clone(admin, args.create_from, args.db)

    # Everything below talks to the clone only, including anything that opens its own session.
    os.environ["DATABASE_URL"] = swap_db(settings.database_url, args.db)
    os.environ["DATABASE_URL_SYNC"] = app_sync
    os.environ.pop("DATABASE_URL_SYNC_MIGRATE", None)
    get_settings.cache_clear()

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.db.sync_url import sqlalchemy_sync_engine_url

    engine = create_engine(sqlalchemy_sync_engine_url(app_sync))
    db = Session(bind=engine)
    if db.scalar(text("SELECT current_database()")) != args.db:
        raise SystemExit("STOP: connected to the wrong database")
    say(f"connected as the app role to {db.scalar(text('SELECT current_database()'))}")

    say("\n== 1. Migration 20261022_0047")
    if admin:
        env = dict(os.environ, DATABASE_URL_SYNC=app_sync, DATABASE_URL_SYNC_MIGRATE=swap_db(admin, args.db))
        say(f"  before: alembic {alembic(env, 'current')}; superseded (st, dsi, policies) {superseded_shape(db)}")
        db.rollback()
        alembic(env, "upgrade", "head")
        up1 = superseded_shape(db)
        db.rollback()
        alembic(env, "downgrade", "-1")
        down = superseded_shape(db)
        db.rollback()
        alembic(env, "upgrade", "head")
        up2 = superseded_shape(db)
        db.rollback()
        say(f"  upgrade   {up1}\n  downgrade {down}\n  upgrade   {up2}")
        say(f"  record counts unchanged through the round trip: {'YES' if up1[:2] == down[:2] == up2[:2] else 'NO'}")
    else:
        say(f"  no owner URL: not run here; superseded (st, dsi, policies) {superseded_shape(db)}")
        db.rollback()

    ok = True
    seeded = seed_real_loads(db) if args.seed_real else []
    say("\n== 2. Sell-through: real figures, a test load over them, the test load deleted")
    pick = db.execute(
        text(
            """
            SELECT tenant_id, customer_id, max(import_job_id) FROM fact_customer_sellthrough
            WHERE import_job_id IS NOT NULL GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1
            """
        )
    ).first()
    tenant, customer, real_job = str(pick[0]), int(pick[1]), int(pick[2])
    name = db.scalar(text("SELECT name FROM dim_customer WHERE id = :c"), {"c": customer})
    db.rollback()
    before = st_snapshot(db, tenant, customer)
    say(f"  customer {customer} ({name}), real load {real_job}: {len(before['rows'])} rows, units {before['units']}, "
        f"on-hand {before['soh']}, superseded records {len(before['records'])}, stock positions {len(before['positions'])}")
    test_job = st_test_load(db, tenant, customer, real_job)
    loaded = st_snapshot(db, tenant, customer)
    say(f"  after the test load: {len(loaded['rows'])} rows, units {loaded['units']}, on-hand {loaded['soh']}, "
        f"superseded records {len(loaded['records'])}")
    ok &= all_or_nothing(db, test_job, st_snapshot, tenant, customer)
    preview_then_delete(db, test_job)
    after = st_snapshot(db, tenant, customer)
    say(f"  after the delete: {len(after['rows'])} rows, units {after['units']}, on-hand {after['soh']}, "
        f"superseded records {len(after['records'])}, stock positions {len(after['positions'])}")
    same = diff("sell-through", before, after)
    say(f"  real figures identical to before: {'YES' if same else 'NO'}")
    ok &= same

    say("\n== 3. Distributor: real lines, a test load over them, the test load deleted")
    pick = db.execute(
        text(
            """
            SELECT f.source_import_job_id, f.distributor_id FROM fact_sales_sellout f
            WHERE f.source_import_job_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM fact_returns r WHERE r.import_job_id = f.source_import_job_id)
            GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1
            """
        )
    ).first()
    real_job, distributor = int(pick[0]), int(pick[1])
    name = db.scalar(text("SELECT name FROM dim_distributor WHERE id = :d"), {"d": distributor})
    db.rollback()
    before = dsi_snapshot(db, distributor)
    say(f"  distributor {distributor} ({name}), real load {real_job}: sell-out lines {len(before['sell'])} "
        f"({before['units']} units), returns lines {len(before['ret'])} ({before['returns']} units), "
        f"superseded records {len(before['records'])}")
    test_job = dsi_test_load(db, distributor, real_job)
    loaded = dsi_snapshot(db, distributor)
    say(f"  after the test load: sell-out lines {len(loaded['sell'])} ({loaded['units']} units), returns "
        f"{len(loaded['ret'])} ({loaded['returns']} units), superseded records {len(loaded['records'])}")
    ok &= all_or_nothing(db, test_job, dsi_snapshot, distributor)
    preview_then_delete(db, test_job)
    after = dsi_snapshot(db, distributor)
    say(f"  after the delete: sell-out lines {len(after['sell'])} ({after['units']} units), returns "
        f"{len(after['ret'])} ({after['returns']} units), superseded records {len(after['records'])}")
    same = diff("distributor", before, after)
    say(f"  real figures identical to before: {'YES' if same else 'NO'}")
    ok &= same

    if seeded:
        from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs

        bulk_delete_import_jobs(db, seeded, delete_semantic_artifacts=False)
        db.commit()
        left = db.scalar(
            text("SELECT count(*) FROM fact_sales_sellout WHERE source_import_job_id = ANY(:j)"), {"j": seeded}
        )
        say(f"\n  rehearsal seed jobs {seeded} deleted again (sell-out rows left: {left})")
    db.close()
    engine.dispose()
    say(f"\nCLONE PROOF {'PASS' if ok else 'FAIL'}")
    if args.drop and args.create_from:
        drop_clone(admin, args.db)
    if args.out:
        Path(args.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
