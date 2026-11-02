#!/usr/bin/env python3
"""Clone proof for the Shipped-sheet source key (a line not invoiced yet keeps its order in the key). Never runs on ``cip``.

Runs on the clone the twin-retirement proof used (``prove_po_less_retire_clone.py``): applies the twin retirement, then
re-processes job 1697 (the 27 Oct report) with the fixed loader (``reprocess_shipment_job.py``), and shows before and after.

Checks: the guards of the re-process; the evidence lines of job 1697 equal the workbook's rows once rows that share the full
new key are counted once; the 27 Oct at-sea position (ship-confirmed, on board on or before 27 Oct, no ATA, sea) is 169 lines /
14,278 units; facts of every other job are unchanged; surviving facts of job 1697 keep their product, distributor, customer and
PO; no PO-less twin is left to retire; the invoice graduation finds nothing new; a second re-process changes nothing.

  python scripts/ops/prove_loader_order_grain_clone.py --db cip_retire --out FILE
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import LINES, db_name, say, swap_db  # noqa: E402
from scripts.ops.prove_po_less_retire_clone import MEASURE, MERGE, counts, parse_json, run  # noqa: E402

REPROCESS = API_ROOT / "scripts" / "ops" / "reprocess_shipment_job.py"
JOB = 1697
REPORT = date(2026, 10, 27)
AS_OF = date.today()
RAW = API_ROOT / "storage" / "uploads" / "imports" / "f8a61716696045269dce5769323418eb" / "ACZA Shipped Unshipped 20261027.xlsx"
SNAP_COLS = "product_id, distributor_id, customer_id, purchase_order_id, resolved_customer_id, resolved_distributor_id"


def norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def as_date(v):
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else None)


def raw_sheet():
    """The workbook's Shipped rows, read once (read-only)."""
    import openpyxl

    wb = openpyxl.load_workbook(RAW, read_only=True, data_only=True)
    it = wb["Shipped"].iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    ix = {h: i for i, h in enumerate(hdr)}
    rows = []
    for r in it:
        if not any(v is not None for v in r):
            continue
        g = lambda n, r=r: r[ix[n]] if n in ix else None  # noqa: E731
        rows.append({"q": float(g("Qty") or 0), "sc": as_date(g("Ship Confirm Date")), "ob": as_date(g("On-Board Date")), "ata": as_date(g("ATA Date(Actual Port Arrival)")),
                     "pod": as_date(g("POD")), "way": str(g("Ship Way") or "").upper(),
                     "full_key": (norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Item")), norm(g("Order No.")) if not norm(g("Invoice Line")) else "",
                                  norm(g("Order Line")) if not norm(g("Invoice Line")) else "")})
    wb.close()
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="the clone the twin proof used (never cip)")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args()
    if args.db == "cip":
        raise SystemExit("STOP: never cip")
    settings = get_settings()
    app_sync = swap_db(settings.database_url_sync, args.db)
    if db_name(app_sync) != args.db:
        raise SystemExit("STOP: the URL does not point at the clone")
    os.environ["DATABASE_URL"] = swap_db(settings.database_url, args.db)
    os.environ["DATABASE_URL_SYNC"] = app_sync
    os.environ.pop("DATABASE_URL_SYNC_MIGRATE", None)
    get_settings.cache_clear()
    env_app = dict(os.environ, DATABASE_URL_SYNC=app_sync)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.db.sync_url import sqlalchemy_sync_engine_url
    from app.services.imports.shipment_invoice_graduation import discover_invoice_graduation_lineages
    from app.services.imports.shipment_shipped_fact_identity_twin_merge import plan_po_less_shipped_twins

    engine = create_engine(sqlalchemy_sync_engine_url(app_sync))
    db = Session(bind=engine)
    if db.scalar(text("SELECT current_database()")) != args.db:
        raise SystemExit("STOP: connected to the wrong database")
    db.rollback()
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and cond
        say(f"  {'PASS' if cond else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")

    say(f"Loader proof (Shipped-sheet source key) on {args.db} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
    raw = raw_sheet()
    raw_units = sum(r["q"] for r in raw)
    new_keys = Counter(r["full_key"] for r in raw)
    raw_user = [r for r in raw if r["sc"] and r["ob"] and r["ob"] <= REPORT and not r["ata"] and "SEA" in r["way"]]
    raw_cip = [r for r in raw if r["sc"] and r["ob"] and r["ob"] <= AS_OF and not r["ata"] and not r["pod"] and "SEA" in r["way"]]
    say(f"workbook, Shipped sheet: {len(raw):,} rows, {raw_units:,.0f} units; distinct rows under the new key: {len(new_keys):,}")
    say(f"  the 27 Oct position (ship-confirmed, on board <= 27 Oct, no ATA, sea): {len(raw_user)} lines {sum(r['q'] for r in raw_user):,.0f} units")
    say(f"  at sea by cip's rule as of {AS_OF} (shipped, on board <= today, no ATA, no POD, sea): {len(raw_cip)} lines {sum(r['q'] for r in raw_cip):,.0f} units")

    say("\n== 1. The twin retirement first (the same clone)")
    rc, o = run(MERGE, env_app, "--retire-po-less", "--apply", "--expect-db", args.db)
    twin = parse_json(o)
    n_retired = db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state = 'closed_superseded'")).scalar()
    db.rollback()
    say(f"  retired now: {n_retired} (this run retired {twin.get('retired')})")
    check("the twin retirement is in place", rc == 0 and n_retired > 0)

    def facts_snapshot() -> dict:
        rows = db.execute(text(f"SELECT fact_upsert_key, quantity, line_state, import_job_id, {SNAP_COLS}, pod_date FROM fact_inbound_shipment WHERE import_job_id = :j"), {"j": JOB}).all()
        db.rollback()
        return {r[0]: r[1:] for r in rows}

    def job_counts() -> dict:
        d = {
            "evidence lines (all sheets)": db.execute(text("SELECT count(*) FROM shipment_evidence_line WHERE import_job_id = :j"), {"j": JOB}).scalar(),
            "evidence lines (Shipped)": db.execute(text("SELECT count(*) FROM shipment_evidence_line WHERE import_job_id = :j AND source_sheet = 'Shipped'"), {"j": JOB}).scalar(),
            "evidence units (Shipped)": float(db.execute(text("SELECT coalesce(sum(quantity),0) FROM shipment_evidence_line WHERE import_job_id = :j AND source_sheet = 'Shipped'"), {"j": JOB}).scalar()),
            "observations (all sheets)": db.execute(text("SELECT count(*) FROM shipment_evidence_observation WHERE import_job_id = :j"), {"j": JOB}).scalar(),
            "facts written by the job": db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE import_job_id = :j"), {"j": JOB}).scalar(),
            "fact units of the job": float(db.execute(text("SELECT coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE import_job_id = :j"), {"j": JOB}).scalar()),
        }
        db.rollback()
        return d

    def evidence_position():
        rows = db.execute(text("""SELECT quantity, ship_confirm_date, on_board_date, port_ata_date, pod_date, upper(coalesce(ship_way,'')) FROM shipment_evidence_line
                                  WHERE import_job_id = :j AND source_sheet = 'Shipped' AND line_state = 'shipped'"""), {"j": JOB}).all()
        db.rollback()
        user = [r for r in rows if r[1] and r[2] and r[2] <= REPORT and not r[3] and "SEA" in r[5]]
        cipr = [r for r in rows if r[1] and r[2] and r[2] <= AS_OF and not r[3] and not r[4] and "SEA" in r[5]]
        return (len(user), sum(float(r[0] or 0) for r in user)), (len(cipr), sum(float(r[0] or 0) for r in cipr))

    def graduation():
        with Session(bind=engine) as s:
            v = discover_invoice_graduation_lineages(s)
            c = Counter(x.outcome for x in v)
            s.rollback()
        return dict(c)

    def twin_plan():
        plan = plan_po_less_shipped_twins(db)
        db.rollback()
        return len([t for t in plan if t.qty_match]), len([t for t in plan if not t.qty_match])

    say("\n== 2. Before (twins retired, old loader output for job 1697)")
    m_before = parse_json(run(MEASURE, env_app)[1])
    jc_before = job_counts()
    pos_before = evidence_position()
    snap_before = facts_snapshot()
    grad_before = graduation()
    twins_before = twin_plan()
    other_before = {r[0]: r[1] for r in db.execute(text("SELECT id, md5((to_jsonb(x) - ARRAY['superseded_by_fact_id','updated_at'])::text) FROM fact_inbound_shipment x WHERE import_job_id IS DISTINCT FROM :j"), {"j": JOB})}
    c_before = counts(db)
    db.rollback()
    for k, v in jc_before.items():
        say(f"  {k:<32} {v:>12,.0f}")
    say(f"  27 Oct position in the evidence lines: {pos_before[0][0]} lines {pos_before[0][1]:,.0f} units")
    say(f"  invoice graduation: {grad_before}; PO-less twins left to retire / quantity differs: {twins_before}")

    say("\n== 3. Guards of the re-process")
    rc, o = run(REPROCESS, env_app, "--job", str(JOB))
    check("dry run reads the workbook and writes nothing", rc == 0 and counts(db) == c_before, o.strip().splitlines()[-1][:160])
    db.rollback()
    rc, o = run(REPROCESS, env_app, "--job", str(JOB), "--apply")
    check("--apply without --expect-db is refused", rc == 2 and "refused" in o)
    rc, o = run(REPROCESS, env_app, "--job", str(JOB), "--apply", "--expect-db", "cip")
    check("--apply with the wrong database name is refused", rc == 2 and "refused" in o)
    rc, o = run(REPROCESS, env_app, "--job", str(JOB), "--apply", "--expect-db", args.db, "--fail-before-commit")
    c_failed = counts(db)
    jc_failed = job_counts()
    db.rollback()
    check("a re-process forced to fail after the writes rolls everything back", rc == 3 and "ROLLED BACK" in o and jc_failed == jc_before and c_failed == c_before)

    say("\n== 4. Re-process job 1697 with the fixed loader")
    rc, o = run(REPROCESS, env_app, "--job", str(JOB), "--apply", "--expect-db", args.db)
    say("  " + (o.strip().splitlines()[-1] if o.strip() else ""))
    check("re-process committed", rc == 0 and "committed" in o)
    m_after = parse_json(run(MEASURE, env_app)[1])
    jc_after = job_counts()
    pos_after = evidence_position()
    snap_after = facts_snapshot()
    grad_after = graduation()
    twins_after = twin_plan()
    other_after = {r[0]: r[1] for r in db.execute(text("SELECT id, md5((to_jsonb(x) - ARRAY['superseded_by_fact_id','updated_at'])::text) FROM fact_inbound_shipment x WHERE import_job_id IS DISTINCT FROM :j"), {"j": JOB})}
    c_after = counts(db)
    dangling = db.execute(text("SELECT count(*) FROM fact_inbound_shipment o LEFT JOIN fact_inbound_shipment s ON s.id = o.superseded_by_fact_id WHERE o.line_state = 'closed_superseded' AND s.id IS NULL")).scalar()
    retired_after = db.execute(text("SELECT count(*) FROM fact_inbound_shipment WHERE line_state = 'closed_superseded'")).scalar()
    db.rollback()
    for k, v in jc_after.items():
        say(f"  {k:<32} {jc_before[k]:>12,.0f} -> {v:>12,.0f}")

    say("\n== 5. Checks")
    check("evidence lines of the Shipped sheet equal the workbook's rows counted once per new key", jc_after["evidence lines (Shipped)"] == len(new_keys),
          f"{jc_after['evidence lines (Shipped)']:,} lines vs {len(new_keys):,} distinct new keys ({len(raw):,} rows)")
    lost_after = raw_units - jc_after["evidence units (Shipped)"]
    check("the Shipped-sheet units rose to the workbook's, less only rows that repeat a full new key", jc_after["evidence units (Shipped)"] > jc_before["evidence units (Shipped)"] and lost_after >= -1.0 and (len(raw) - len(new_keys) > 0 or abs(lost_after) < 1.0),
          f"{jc_before['evidence units (Shipped)']:,.0f} -> {jc_after['evidence units (Shipped)']:,.0f} loaded vs {raw_units:,.0f} in the file ({len(raw) - len(new_keys)} rows repeat a full key)")
    check("the 27 Oct position is 169 lines / 14,278 units", pos_after[0] == (169, 14278.0), f"{pos_after[0]}")
    say(f"  by cip's rule as of {AS_OF}: evidence {pos_after[1]}, workbook {(len(raw_cip), sum(r['q'] for r in raw_cip))}")
    check("facts of every other job are unchanged (pointers and updated_at aside)", other_before == other_after)
    keep = [k for k in snap_before if k in snap_after]
    moved = [k for k in keep if snap_before[k][2:-1] != snap_after[k][2:-1] and snap_before[k][1] != "closed_superseded"]
    lost_pod = [k for k in keep if snap_before[k][-1] is not None and snap_after[k][-1] is None]
    say(f"  facts of the job that had a POD before and none now: {len(lost_pod)} ({sum(float(snap_before[k][0] or 0) for k in lost_pod):,.0f} units)")
    check("a surviving fact keeps its product, distributor, customer, PO and state", not moved, f"{len(moved)} changed of {len(keep):,}")
    grew = [k for k in keep if float(snap_after[k][0] or 0) > float(snap_before[k][0] or 0)]
    say(f"  facts that now hold more units (lines of the same delivery + item + PO added up): {len(grew)}; new facts: {len([k for k in snap_after if k not in snap_before]):,}; "
        f"facts no longer written: {len([k for k in snap_before if k not in snap_after])}")
    check("no PO-less twin is left to retire", twins_after[0] == 0, f"{twins_before} -> {twins_after}")
    check("the retired facts are still retired and every pointer resolves", retired_after >= n_retired and dangling == 0, f"{retired_after} retired, {dangling} dangling")
    check("the invoice graduation finds nothing new", grad_after.get("full", 0) <= grad_before.get("full", 0) and grad_after.get("partial", 0) <= grad_before.get("partial", 0), f"{grad_before} -> {grad_after}")
    changed_tables = {k: (c_before.get(k), c_after.get(k)) for k in set(c_before) | set(c_after) if c_before.get(k) != c_after.get(k)}
    say(f"  tables whose row count changed: {changed_tables}")

    say("\n== 6. Before and after (the figures the app shows)")
    rows = [
        ("shipped units (line_state shipped, all)", m_before["facts_by_line_state"].get("shipped", {}).get("units"), m_after["facts_by_line_state"].get("shipped", {}).get("units")),
        ("shipped, not landed units (supply overview)", m_before["supply"]["shipped_units"], m_after["supply"]["shipped_units"]),
        ("landed units (POD set)", m_before["supply"]["landed_units"], m_after["supply"]["landed_units"]),
        ("arrived units (ATA, no POD)", m_before["supply"]["arrived_units"], m_after["supply"]["arrived_units"]),
        ("open units (not received)", m_before["supply"]["open_units"], m_after["supply"]["open_units"]),
        ("pipeline units (open orders)", m_before["supply"]["pipeline_units"], m_after["supply"]["pipeline_units"]),
        ("fill rate", m_before["fill_rate"], m_after["fill_rate"]),
        ("On the water: at sea units", m_before["on_the_water"]["at_sea_units"], m_after["on_the_water"]["at_sea_units"]),
        ("On the water: at sea lines (facts)", m_before["on_the_water"]["at_sea_lines"], m_after["on_the_water"]["at_sea_lines"]),
        ("On the water: vessels", m_before["on_the_water"]["vessels"], m_after["on_the_water"]["vessels"]),
        ("On the water: overdue vessels", m_before["on_the_water"]["overdue_vessels"], m_after["on_the_water"]["overdue_vessels"]),
        ("On the water: units on overdue vessels", m_before["on_the_water"]["overdue_units"], m_after["on_the_water"]["overdue_units"]),
        ("On the water: arrived units", m_before["on_the_water"]["arrived_units"], m_after["on_the_water"]["arrived_units"]),
    ]
    say(f"  {'figure':<48} {'before':>14} {'after':>14}")
    for name, b, a in rows:
        say(f"  {name:<48} {b!s:>14} {a!s:>14}")
    say(f"  at sea expected from the workbook by cip's rule: {sum(r['q'] for r in raw_cip):,.0f} units in {len(raw_cip)} rows")
    differs = [t["old_fact"] for t in twin.get("quantity_differs", [])]
    listed_at_sea = float(db.execute(text("""SELECT coalesce(sum(quantity), 0) FROM fact_inbound_shipment WHERE id = ANY(:ids) AND line_state = 'shipped'
                                            AND port_ata_date IS NULL AND pod_date IS NULL AND on_board_date <= :d AND upper(coalesce(ship_way,'')) LIKE '%SEA%'"""),
                                    {"ids": differs, "d": AS_OF}).scalar())
    db.rollback()
    sea_units = float(m_after["on_the_water"]["at_sea_units"])
    check("On the water at-sea units equal the workbook's, plus only the listed quantity-differs facts that stay at sea", abs(sea_units - listed_at_sea - sum(r["q"] for r in raw_cip)) < 1.0,
          f"{sea_units:,.0f} = {sum(r['q'] for r in raw_cip):,.0f} (workbook) + {listed_at_sea:,.0f} (listed, not retired)")
    check("arrived units equal the workbook's (ATA set, no POD)", abs(float(m_after["on_the_water"]["arrived_units"]) - sum(r["q"] for r in raw if r["sc"] and r["ob"] and r["ata"] and not r["pod"] and "SEA" in r["way"])) < 1.0,
          f"{m_after['on_the_water']['arrived_units']} vs {sum(r['q'] for r in raw if r['sc'] and r['ob'] and r['ata'] and not r['pod'] and 'SEA' in r['way']):,.0f}")
    say(f"  lines: {len(raw_cip)} evidence lines at sea; {m_after['on_the_water']['at_sea_lines']} facts (a fact adds up the rows of one delivery + item + PO)")
    landed_b, landed_a = m_before["supply"]["landed_units"], m_after["supply"]["landed_units"]
    check("landed units did not move", landed_b == landed_a, f"{landed_b:,.0f} -> {landed_a:,.0f}")

    say("\n== 7. Idempotence")
    max_obs = db.execute(text("SELECT max(id) FROM shipment_evidence_observation")).scalar()
    db.rollback()
    rc, o = run(REPROCESS, env_app, "--job", str(JOB), "--apply", "--expect-db", args.db)
    jc_again = job_counts()
    new_obs = db.execute(text("SELECT id, line_identity_key, to_jsonb(o) AS j FROM shipment_evidence_observation o WHERE id > :m AND import_job_id = :j ORDER BY id LIMIT 400"), {"m": max_obs, "j": JOB}).all()
    differing = Counter()
    for _id, lik, j in new_obs:
        prev = db.execute(text("SELECT to_jsonb(o) FROM shipment_evidence_observation o WHERE id < :m AND import_job_id = :j AND line_identity_key = :k ORDER BY id DESC LIMIT 1"), {"m": max_obs + 1, "j": JOB, "k": lik}).scalar()
        if prev:
            differing.update(k for k in j if k not in ("id", "created_at", "updated_at") and j.get(k) != prev.get(k))
    db.rollback()
    say(f"  observations added by the second pass: {len(new_obs)} (first 400 compared); columns that differ from the earlier observation of the same line: {dict(differing)}")
    snap_again = facts_snapshot()
    check("a second re-process changes no evidence line and no fact", rc == 0 and {k: v for k, v in jc_again.items() if k != "observations (all sheets)"} == {k: v for k, v in jc_after.items() if k != "observations (all sheets)"} and snap_again == snap_after)
    say(f"  observations (append-only history): {jc_after['observations (all sheets)']:,} -> {jc_again['observations (all sheets)']:,}")

    db.close()
    engine.dispose()
    say(f"\nRESULT: {'ALL PASS' if ok else 'FAILED - see FAIL lines'}")
    say(f"clone {args.db} left in place (drop it by hand when done)")
    if args.out:
        Path(args.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
