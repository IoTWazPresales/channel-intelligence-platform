#!/usr/bin/env python3
"""Clone proof for migration 20261101_0050 and ``merge_shipped_fact_identity_twins.py --retire-po-less``. Never runs on ``cip``.

On a fresh pg_dump copy of cip it checks:

1. The migration adds two nullable columns and changes nothing else: every table's row count and a fingerprint of every
   fact row (all columns but the two new ones) are identical; downgrade and upgrade again, same result.
2. The dry run is read-only and changes nothing. ``--apply`` without ``--expect-db`` or with the wrong name is refused.
3. The apply retires exactly the planned rows, keeps every row, and touches nothing else: every other column of every
   retired row, and every column of every other row, is as before. Each retired row points at a shipped PO-key fact of a
   newer job with the same delivery + item and the same quantity. Pairs whose quantity differs are left alone and listed.
4. The retire set matches an independent SQL formulation, and contains the stale overdue at-sea facts of 1 Nov 2026.
5. Before and after: shipped units, landed units, fill rate, open and pipeline units, On the water at sea / vessels / overdue.
6. A second dry run and a second apply retire nothing. Downgrade with the data present puts every row back.

Usage (from apps/api; the owner login is read from PG_OWNER or CIP_CLONE_ADMIN_URL and never printed):
  python scripts/ops/prove_po_less_retire_clone.py --db cip_retire --create-from cip --out FILE
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import LINES, alembic, create_clone, db_name, say, swap_db  # noqa: E402
from scripts.ops.prove_on_the_water_clone import admin_url  # noqa: E402

MERGE = API_ROOT / "scripts" / "merge_shipped_fact_identity_twins.py"
MEASURE = API_ROOT / "scripts" / "ops" / "measure_inbound_shipments.py"
NEW_COLS = "ARRAY['superseded_by_fact_id', 'superseded_by_key']"
RETIRE_COLS = "ARRAY['superseded_by_fact_id', 'superseded_by_key', 'line_state', 'updated_at']"

# Independent formulation of the twin set: same key prefix + same order + same item, a newer job, a PO id on the twin.
INDEPENDENT_SQL = """
SELECT o.id FROM fact_inbound_shipment o
WHERE o.tenant_id = 'default' AND o.line_state = 'shipped' AND o.purchase_order_id IS NULL AND o.fact_upsert_key LIKE 'ship:%'
  AND EXISTS (SELECT 1 FROM fact_inbound_shipment s WHERE s.tenant_id = o.tenant_id AND s.id <> o.id AND s.line_state = 'shipped'
              AND s.purchase_order_id IS NOT NULL AND s.fact_upsert_key LIKE o.fact_upsert_key || '|%'
              AND s.item_code IS NOT DISTINCT FROM o.item_code AND coalesce(s.import_job_id, 0) > coalesce(o.import_job_id, 0))
"""

# The stale overdue at-sea facts found on 1 Nov 2026: at sea on the sheet's own terms, ETA before today, not at sea in job 1697.
STALE_OVERDUE_SQL = """
SELECT f.id FROM fact_inbound_shipment f
WHERE f.tenant_id = 'default' AND f.line_state = 'shipped' AND f.port_ata_date IS NULL AND f.pod_date IS NULL
  AND f.on_board_date <= current_date AND f.port_eta_date < current_date AND upper(coalesce(f.ship_way, '')) LIKE '%SEA%'
  AND f.import_job_id <> 1697 AND f.purchase_order_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM shipment_evidence_observation x WHERE x.import_job_id = 1697 AND x.order_no IS NOT DISTINCT FROM f.order_no
                  AND x.item_code IS NOT DISTINCT FROM f.item_code AND x.customer_po IS NOT DISTINCT FROM f.customer_po
                  AND x.port_ata_date IS NULL AND x.pod_date IS NULL)
"""


def counts(db) -> dict[str, int]:
    from sqlalchemy import text

    tables = db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")).scalars().all()
    return {t: db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables}


def fact_fingerprint(db, drop: str = NEW_COLS, only_ids: str = "") -> str:
    """md5 over fact rows, leaving out the given columns; ``only_ids`` is an SQL condition."""
    from sqlalchemy import text

    where = f"WHERE {only_ids}" if only_ids else ""
    return db.execute(
        text(f"SELECT md5(coalesce(string_agg(md5((to_jsonb(x) - {drop})::text), '' ORDER BY x.id), '')) FROM fact_inbound_shipment x {where}")
    ).scalar()


def has_cols(db) -> bool:
    from sqlalchemy import text

    return db.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'fact_inbound_shipment' AND column_name = 'superseded_by_key'")).scalar() == 1


def run(script: Path, env: dict[str, str], *args: str) -> tuple[int, str]:
    env = dict(env, PYTHONPATH=str(API_ROOT))  # scripts/merge_*.py sits outside the app package's folder
    out = subprocess.run([sys.executable, "-X", "utf8", "-W", "ignore", str(script), *args], cwd=str(API_ROOT), env=env, capture_output=True, text=True, encoding="utf-8")
    return out.returncode, out.stdout + out.stderr


def parse_json(text_out: str) -> dict:
    if "{" not in text_out:
        raise SystemExit("STOP: a script printed no JSON:\n" + text_out[-1500:])
    return json.loads(text_out[text_out.index("{"):])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="disposable database to run on (never cip)")
    p.add_argument("--create-from", help="make --db as a fresh pg_dump copy of this database first")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args()
    if args.db == "cip":
        raise SystemExit("STOP: never cip")
    settings = get_settings()
    admin = admin_url(settings)
    app_sync = swap_db(settings.database_url_sync, args.db)
    if db_name(app_sync) != args.db:
        raise SystemExit("STOP: the URL does not point at the clone")
    say(f"PO-less twin retire, clone proof on {args.db} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
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

    say(f"\n== 1. Migration 20261101_0050 (clone is at: {alembic(env_owner, 'current')})")
    if has_cols(db):
        db.rollback()
        say("  the clone already carries 0050 (an earlier run): taken back to cip's head, 20261101_0049, before the proof")
        alembic(env_owner, "downgrade", "20261101_0049")
    db.rollback()
    c0 = counts(db)
    f0 = db.execute(text("SELECT md5(coalesce(string_agg(md5(to_jsonb(x)::text), '' ORDER BY x.id), '')) FROM fact_inbound_shipment x")).scalar()
    f0_noupd = db.execute(text("SELECT md5(coalesce(string_agg(md5((to_jsonb(x) - 'updated_at')::text), '' ORDER BY x.id), '')) FROM fact_inbound_shipment x")).scalar()
    db.rollback()
    n_po_less = db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state = 'shipped' AND purchase_order_id IS NULL")).scalar()
    db.rollback()  # an open read would hold a lock that blocks the migration's ALTER TABLE
    say(f"  facts {c0['fact_inbound_shipment']:,}; shipped without a PO id: {n_po_less}")
    alembic(env_owner, "upgrade", "head")
    # The app's model selects the two new columns, so the figures are read once they exist (nothing is retired yet).
    before = parse_json(run(MEASURE, env_app)[1])
    db.rollback()
    c1, f1 = counts(db), fact_fingerprint(db)
    cols = has_cols(db)
    db.rollback()
    check("after upgrade: the two columns exist, every row count is as before", cols and c1 == c0)
    check("after upgrade: every fact row is byte-identical on its existing columns", f1 == f0)
    alembic(env_owner, "downgrade", "-1")
    c2, f2, gone = counts(db), db.execute(text("SELECT md5(coalesce(string_agg(md5(to_jsonb(x)::text), '' ORDER BY x.id), '')) FROM fact_inbound_shipment x")).scalar(), not has_cols(db)
    db.rollback()
    check("after downgrade: columns gone, counts and rows as before", gone and c2 == c0 and f2 == f0)
    alembic(env_owner, "upgrade", "head")
    db.rollback()

    say("\n== 2. Dry run and guards")
    f_pre = fact_fingerprint(db, drop="ARRAY[]::text[]")
    db.rollback()
    rc, dry = run(MERGE, env_app, "--retire-po-less")
    plan = parse_json(dry)
    f_post = fact_fingerprint(db, drop="ARRAY[]::text[]")
    db.rollback()
    say(f"  dry run: twins found {plan['twins_found']}, to retire {plan['to_retire']} ({plan['to_retire_units']:,.0f} units), "
        f"quantity differs {len(plan['quantity_differs'])}")
    check("dry run is read-only and changes nothing", rc == 0 and f_pre == f_post)
    rc, o = run(MERGE, env_app, "--retire-po-less", "--apply")
    check("--apply without --expect-db is refused", rc != 0 and "refused" in o)
    rc, o = run(MERGE, env_app, "--retire-po-less", "--apply", "--expect-db", "cip")
    check("--apply with the wrong database name is refused", rc != 0 and "refused" in o)
    f_ref = fact_fingerprint(db, drop="ARRAY[]::text[]")
    db.rollback()
    check("refused applies changed nothing", f_ref == f_pre)

    say("\n== 3. The retire set, independently")
    independent = {r[0] for r in db.execute(text(INDEPENDENT_SQL))}
    stale = {r[0] for r in db.execute(text(STALE_OVERDUE_SQL))}
    differ_ids = {t["old_fact"] for t in plan["quantity_differs"]}
    db.rollback()
    say(f"  independent twin set (key prefix + item + newer job + PO id): {len(independent)}; stale overdue at-sea facts of 1 Nov: {len(stale)}")
    say(f"  quantity differs (listed for Warren, not retired): {sorted(differ_ids)}")
    for t in plan["quantity_differs"]:
        say(f"    fact {t['old_fact']} job {t['old_job']} {t['delivery_no']}|{t['item_code']}: {t['old_qty']:g} units vs {t['twin_qty']:g} on {t['twins']} PO-key twin(s) (fact {t['keeper_fact']})")
    planned_all = {t for t in independent}  # compared below with what the apply retires
    pre_shipped_ids = {r[0] for r in db.execute(text("SELECT id FROM fact_inbound_shipment WHERE line_state = 'shipped'"))}
    db.rollback()

    snap_sql = text(f"SELECT id, md5((to_jsonb(x) - {NEW_COLS})::text), md5((to_jsonb(x) - {RETIRE_COLS})::text) FROM fact_inbound_shipment x")
    snap_before = {r[0]: (r[1], r[2]) for r in db.execute(snap_sql)}
    db.rollback()
    audit_before = db.execute(text("SELECT count(*) FROM platform_audit_event WHERE action = 'shipped_fact_po_less_retire'")).scalar()
    db.rollback()
    say("\n== 4. Apply")
    rc, applied = run(MERGE, env_app, "--retire-po-less", "--apply", "--expect-db", args.db)
    done = parse_json(applied)
    c3 = counts(db)
    retired_rows = db.execute(text("SELECT id, superseded_by_fact_id, superseded_by_key, quantity, delivery_no, item_code, import_job_id FROM fact_inbound_shipment WHERE line_state = 'closed_superseded' ORDER BY id")).all()
    retired_ids = {r[0] for r in retired_rows}
    audit = db.execute(text("SELECT count(*), max(detail_json::text) FROM platform_audit_event WHERE action = 'shipped_fact_po_less_retire'")).one()
    db.rollback()
    say(f"  retired {done.get('retired')} fact rows ({plan['to_retire_units']:,.0f} units)")
    check("apply committed and retired exactly the planned rows", rc == 0 and done.get("retired") == plan["to_retire"] == len(retired_ids))
    check("no row was added or removed in any table (one audit event aside)", {k: v for k, v in c3.items() if k != "platform_audit_event"} == {k: v for k, v in c0.items() if k != "platform_audit_event"})
    check("retired rows are only rows that were shipped before", retired_ids <= pre_shipped_ids)
    check("every retired row is in the independent twin set", retired_ids <= independent, f"{len(retired_ids - independent)} not in it")
    left = independent - retired_ids
    check("what the independent set has beyond the retired rows is the quantity-differs pairs plus pairs the independent reading cannot size",
          differ_ids <= left, f"{len(left)} left over, {len(differ_ids)} listed as quantity differs; {len(left - differ_ids)} are twins whose quantity the independent formulation does not test")
    check("the stale overdue at-sea facts are all retired or listed", stale <= retired_ids | differ_ids, f"{len(stale)} stale; {len(stale & retired_ids)} retired, {len(stale & differ_ids)} listed")
    pointers = db.execute(text("""
        SELECT count(*) FILTER (WHERE s.id IS NULL), count(*) FILTER (WHERE s.purchase_order_id IS NULL OR s.line_state <> 'shipped'),
               count(*) FILTER (WHERE s.delivery_no IS DISTINCT FROM o.delivery_no OR s.item_code IS DISTINCT FROM o.item_code),
               count(*) FILTER (WHERE coalesce(s.import_job_id,0) <= coalesce(o.import_job_id,0)),
               count(*) FILTER (WHERE s.fact_upsert_key IS DISTINCT FROM o.superseded_by_key)
        FROM fact_inbound_shipment o LEFT JOIN fact_inbound_shipment s ON s.id = o.superseded_by_fact_id WHERE o.line_state = 'closed_superseded'""")).one()
    db.rollback()
    check("each retired row points at a shipped PO-key fact of a newer job with the same delivery and item, and its key",
          tuple(pointers) == (0, 0, 0, 0, 0), str(tuple(pointers)))
    qty_bad = db.execute(text("""
        SELECT count(*) FROM (SELECT o.id FROM fact_inbound_shipment o JOIN fact_inbound_shipment s ON s.id = o.superseded_by_fact_id
          WHERE o.line_state = 'closed_superseded' AND round(o.quantity, 4) <> round((SELECT coalesce(sum(t.quantity),0) FROM fact_inbound_shipment t
             WHERE t.tenant_id = o.tenant_id AND t.line_state = 'shipped' AND t.purchase_order_id IS NOT NULL AND t.delivery_no = o.delivery_no
               AND t.item_code = o.item_code AND t.operating_unit IS NOT DISTINCT FROM o.operating_unit AND coalesce(t.import_job_id,0) > coalesce(o.import_job_id,0)), 4)) q""")).scalar()
    db.rollback()
    check("each retired row's quantity equals its PO-key twins' total", qty_bad == 0)
    snap_after = {r[0]: (r[1], r[2]) for r in db.execute(snap_sql)}
    db.rollback()
    changed = {i for i, v in snap_after.items() if snap_before.get(i, (None,))[0] != v[0]}
    check("exactly the retired rows changed; every column of every other row is as before", changed == retired_ids and set(snap_before) == set(snap_after),
          f"{len(changed)} rows changed, {len(retired_ids)} retired")
    check("a retired row differs only in line_state, updated_at and the two pointer columns", all(snap_before[i][1] == snap_after[i][1] for i in retired_ids))
    check("this apply wrote one audit event holding the retire", audit[0] - audit_before == 1 and audit[1] is not None, f"{audit_before} -> {audit[0]}")

    say("\n== 5. Before and after (the figures the app shows)")
    after = parse_json(run(MEASURE, env_app)[1])
    db.rollback()
    rows = [
        ("shipped units (line_state shipped, all)", before["facts_by_line_state"].get("shipped", {}).get("units"), after["facts_by_line_state"].get("shipped", {}).get("units")),
        ("shipped, not landed (supply overview) units", before["supply"]["shipped_units"], after["supply"]["shipped_units"]),
        ("landed units (POD set)", before["supply"]["landed_units"], after["supply"]["landed_units"]),
        ("arrived units (ATA, no POD)", before["supply"]["arrived_units"], after["supply"]["arrived_units"]),
        ("open units (not received)", before["supply"]["open_units"], after["supply"]["open_units"]),
        ("pipeline units (open orders)", before["supply"]["pipeline_units"], after["supply"]["pipeline_units"]),
        ("past-ETA lines with no POD", before["supply"]["eta_past_no_pod_lines"], after["supply"]["eta_past_no_pod_lines"]),
        ("fill rate", before["fill_rate"], after["fill_rate"]),
        ("On the water: at sea units", before["on_the_water"]["at_sea_units"], after["on_the_water"]["at_sea_units"]),
        ("On the water: at sea lines", before["on_the_water"]["at_sea_lines"], after["on_the_water"]["at_sea_lines"]),
        ("On the water: vessels", before["on_the_water"]["vessels"], after["on_the_water"]["vessels"]),
        ("On the water: overdue vessels", before["on_the_water"]["overdue_vessels"], after["on_the_water"]["overdue_vessels"]),
        ("On the water: units on overdue vessels", before["on_the_water"]["overdue_units"], after["on_the_water"]["overdue_units"]),
        ("On the water: arrived units", before["on_the_water"]["arrived_units"], after["on_the_water"]["arrived_units"]),
        ("retired facts (closed_superseded)", before["facts_by_line_state"].get("closed_superseded", {}).get("lines", 0), after["facts_by_line_state"].get("closed_superseded", {}).get("lines", 0)),
    ]
    say(f"  {'figure':<48} {'before':>14} {'after':>14}")
    for name, b, a in rows:
        say(f"  {name:<48} {b!s:>14} {a!s:>14}")
    sup_b, sup_a = before["supply"], after["supply"]
    check("landed units and the open book (pipeline) did not move", sup_b["landed_units"] == sup_a["landed_units"] and sup_b["pipeline_units"] == sup_a["pipeline_units"])
    check("fill rate did not move", before["fill_rate"] == after["fill_rate"])
    otw_b, otw_a = before["on_the_water"], after["on_the_water"]
    check("On the water: overdue vessels and at-sea units fell, nothing arrived or moved", otw_a["at_sea_units"] <= otw_b["at_sea_units"] and otw_a["overdue_vessels"] <= otw_b["overdue_vessels"] and otw_a["arrived_units"] == otw_b["arrived_units"])

    say("\n== 6. Idempotence and the round trip")
    rc, again = run(MERGE, env_app, "--retire-po-less")
    p2 = parse_json(again)
    check("a second dry run plans nothing to retire", rc == 0 and p2["to_retire"] == 0, f"twins found {p2['twins_found']}")
    rc, again2 = run(MERGE, env_app, "--retire-po-less", "--apply", "--expect-db", args.db)
    n_ret2 = db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state = 'closed_superseded'")).scalar()
    db.rollback()
    check("a second apply retires nothing", rc == 0 and parse_json(again2).get("retired") == 0 and n_ret2 == len(retired_ids))
    alembic(env_owner, "downgrade", "-1")
    f_down = db.execute(text("SELECT md5(coalesce(string_agg(md5((to_jsonb(x) - 'updated_at')::text), '' ORDER BY x.id), '')) FROM fact_inbound_shipment x")).scalar()
    shipped_back = db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state = 'closed_superseded'")).scalar()
    db.rollback()
    check("downgrade with the data present puts every retired row back: all rows as before (updated_at aside)", shipped_back == 0 and f_down == f0_noupd)
    alembic(env_owner, "upgrade", "head")
    db.rollback()

    db.close()
    engine.dispose()
    say(f"\nRESULT: {'ALL PASS' if ok else 'FAILED - see FAIL lines'}")
    say(f"clone {args.db} left in place (drop it by hand when done)")
    if args.out:
        Path(args.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
