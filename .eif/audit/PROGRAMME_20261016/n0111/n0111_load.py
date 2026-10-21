"""N-0111 synthetic 2-year history load on a CLONE of cip (run through dbrun.py <clone>).

Customer sell-through (Amazon 299, Takealot 20) goes through the real pipeline: job + raw file ->
process_import_job_sync (parse, resolve, apply, stock positions). Pinnacle (distributor 29) goes
through the real DSI fact upsert (upsert_dsi_facts_for_staging_job) from resolved staging lines;
the DSI column-mapping workflow is not scripted.

Refuses to run unless current_database() starts with cip_n0111. Prints per-customer units and
on-hand before / after / after re-running the whole set.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.ingestion.pipeline import process_import_job_sync  # noqa: E402
from app.models.fact_customer_sellthrough import FactCustomerSellthrough  # noqa: E402
from app.models.import_distributor_si import ImportDistributorSiStagingLine  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

START = date(2023, 1, 2)  # Monday; 104 weeks to 2024-12-29
WEEKS = 104
GAP_WEEK = 20  # no file at all: "no on-hand reported"
WEEKNO_WEEK = 30  # only in the week-number file (2023-W31)
CORRECTION_WEEKS = (60, 61)
Z = START + timedelta(weeks=WEEKS)  # 2024-12-30: sales-only then stock-only
Z1 = Z + timedelta(weeks=1)  # 2025-01-06: stock-only then sales-only
CUSTOMERS = {299: ("Amazon", 21), 20: ("Takealot", 18)}
PINNACLE, OPEN_CHANNEL, DSI_SOURCE = 29, 1, 12
OUT: list[str] = []


def log(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


def units_for(day: date, k: int) -> int:
    return (day.toordinal() * (k + 3)) % 4  # 0..3, deterministic


def stock_series(k: int) -> dict[date, int]:
    """On-hand at the end of each day: 100, restock +40 every fourth Monday, minus daily sales."""
    out, soh = {}, 100
    for i in range(WEEKS * 7):
        d = START + timedelta(days=i)
        if d.weekday() == 0 and (i // 7) % 4 == 0 and i:
            soh += 40
        soh -= units_for(d, k)
        out[d] = soh
    return out


def csv(rows: list[list]) -> bytes:
    return ("\n".join(",".join(str(c) for c in r) for r in rows) + "\n").encode()


def customer_files(skus: list[str]) -> list[tuple[str, bytes, dict]]:
    """(file name, bytes, upload flags) in upload order."""
    stocks = [stock_series(k) for k in range(len(skus))]

    def day_lines(year: int | None = None, weeks=None, bump: int = 0) -> bytes:
        rows = [["Sale Date", "SKU", "Units Sold", "SOH"]]
        for w in range(WEEKS):
            if w in (GAP_WEEK, WEEKNO_WEEK) or (weeks is not None and w not in weeks):
                continue
            for i in range(7):
                d = START + timedelta(weeks=w, days=i)
                if year is not None and d.year != year:
                    continue
                for k, sku in enumerate(skus):
                    rows.append([d.isoformat(), sku, units_for(d, k) + bump, stocks[k][d] - bump])
        return csv(rows)

    wk = START + timedelta(weeks=WEEKNO_WEEK)
    week_rows = [["Week", "SKU", "Units Sold", "SOH"]]
    for k, sku in enumerate(skus):
        sold = sum(units_for(wk + timedelta(days=i), k) for i in range(7))
        week_rows.append([f"W{wk.isocalendar()[1]}", sku, sold, stocks[k][wk + timedelta(days=6)]])
    last = START + timedelta(weeks=WEEKS, days=-1)

    def week_file(start: date, *, units: bool, soh: bool, delta: int) -> bytes:
        head = ["Week", "SKU"] + (["Units Sold"] if units else []) + (["SOH"] if soh else [])
        rows = [head]
        for k, sku in enumerate(skus):
            row = [start.isoformat(), sku]
            if units:
                row.append(5 + k + delta)
            if soh:
                row.append(stocks[k][last] - 5 - k - delta)
            rows.append(row)
        return csv(rows)

    return [
        ("history 2023.csv", day_lines(2023), {}),
        ("history 2024.csv", day_lines(2024), {}),
        (f"W{wk.isocalendar()[1]}.csv", csv(week_rows), {"_year_step": True}),
        ("sales week Z.csv", week_file(Z, units=True, soh=False, delta=0), {"cst_sales_only": True}),
        ("stock week Z.csv", week_file(Z, units=False, soh=True, delta=0), {"cst_stock_only": True}),
        ("stock week Z1.csv", week_file(Z1, units=False, soh=True, delta=1), {"cst_stock_only": True}),
        ("sales week Z1.csv", week_file(Z1, units=True, soh=False, delta=1), {"cst_sales_only": True}),
        ("history 2024.csv", day_lines(2024), {"_reupload": True}),
        ("correction weeks 61-62.csv", day_lines(None, weeks=CORRECTION_WEEKS, bump=1), {}),
    ]


def new_cst_job(db, customer: int, source: int, name: str, data: bytes, flags: dict) -> int:
    meta = {"customer_id": customer, "report_structure_type": "flat", "cst_batch_filenames": [name]}
    meta.update({k: v for k, v in flags.items() if not k.startswith("_")})
    job = ImportJob(source_id=source, template_slug="customer_sell_through", import_mode="apply", status="pending",
                    stage="uploaded", file_name=name, tenant_id="default", staged_metadata=meta)
    db.add(job)
    db.flush()
    key = f"imports/n0111-proof/{uuid.uuid4().hex}/{name}"
    get_storage_backend().save(key, data, "text/csv")
    db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(data), checksum=None))
    db.commit()
    process_import_job_sync(db, job.id)
    db.commit()
    return int(job.id)


def cst_numbers(db, customer: int, product_ids: list[int]) -> dict:
    f = FactCustomerSellthrough
    window = (f.customer_id == customer, f.product_id.in_(product_ids))
    units = db.scalar(select(func.coalesce(func.sum(f.units_sold), 0)).where(*window))
    rows = db.scalar(select(func.count()).select_from(f).where(*window))
    latest = Decimal("0")
    for pid in product_ids:
        v = db.scalar(select(f.reported_soh).where(f.customer_id == customer, f.product_id == pid,
                                                  f.reported_soh.isnot(None)).order_by(f.period_start_date.desc()).limit(1))
        latest += Decimal(str(v or 0))
    soh_sum = db.scalar(select(func.coalesce(func.sum(f.reported_soh), 0)).where(*window))
    all_units = db.scalar(select(func.coalesce(func.sum(f.units_sold), 0)).where(f.customer_id == customer))
    kept = db.execute(text(
        "select count(*), count(*) filter (where figures is not null) from fact_customer_sellthrough_superseded "
        "where customer_id = :c and product_id = any(:p)"), {"c": customer, "p": product_ids}).one()
    pos = dict(db.execute(text(
        "select status, count(*) from customer_stock_position where customer_id = :c and product_id = any(:p) group by 1"),
        {"c": customer, "p": product_ids}).all())
    return {"units": float(units), "latest_on_hand": float(latest), "on_hand_rows_sum": float(soh_sum), "rows": rows,
            "customer_all_units": float(all_units), "superseded_records": kept[0], "with_figures": kept[1],
            "positions": pos}


def week_figures(db, customer: int, product_ids: list[int], start: date) -> tuple[float, float]:
    f = FactCustomerSellthrough
    u, s = db.execute(select(func.coalesce(func.sum(f.units_sold), 0), func.coalesce(func.sum(f.reported_soh), 0)).where(
        f.customer_id == customer, f.product_id.in_(product_ids), f.period_start_date == start)).one()
    return float(u), float(s)


def run_customer(db, customer: int, source: int, skus: list[str], pids: list[int], round_no: int) -> None:
    label = CUSTOMERS[customer][0]
    for name, data, flags in customer_files(skus):
        if flags.get("_year_step") and round_no == 1:
            jid = new_cst_job(db, customer, source, name, data, flags)
            job = db.get(ImportJob, jid)
            meta = job.staged_metadata or {}
            applied = db.scalar(select(func.count()).select_from(FactCustomerSellthrough).where(FactCustomerSellthrough.import_job_id == jid))
            log(f"  {label} {name}: no year confirmed -> status {job.status}, stage {job.stage}, "
                f"year_required {json.dumps(meta.get('cst_year_required'))}, fact rows from this load {applied}")
            log(f"    message: {job.error_summary}")
            # The confirm-year endpoint: record the year, parse again.
            meta = dict(meta)
            meta["cst_confirmed_year"] = 2023
            job.staged_metadata = meta
            db.commit()
            process_import_job_sync(db, jid)
            db.commit()
            applied = db.scalar(select(func.count()).select_from(FactCustomerSellthrough).where(FactCustomerSellthrough.import_job_id == jid))
            wk = START + timedelta(weeks=WEEKNO_WEEK)
            log(f"  {label} {name}: year 2023 confirmed -> fact rows {applied}, week {wk} units/on-hand {week_figures(db, customer, pids, wk)}")
            continue
        if flags.get("_year_step"):
            flags = dict(flags, cst_confirmed_year=2023)
        before_z = {s: week_figures(db, customer, pids, s) for s in (Z, Z1)}
        jid = new_cst_job(db, customer, source, name, data, flags)
        job = db.get(ImportJob, jid)
        n = cst_numbers(db, customer, pids)
        log(f"  {label} {name} (job {jid}, {job.status}): units {n['units']}, latest on-hand {n['latest_on_hand']}, "
            f"rows {n['rows']}, superseded records {n['superseded_records']}")
        if name.startswith(("sales week", "stock week")):
            start = Z if name.endswith(" Z.csv") else Z1
            u0, s0 = before_z[start]
            u1, s1 = week_figures(db, customer, pids, start)
            kind = "stock-only" if "stock" in name else "sales-only"
            kept = "sales unchanged" if kind == "stock-only" and u1 == u0 and u0 else (
                "stock unchanged" if kind == "sales-only" and s1 == s0 and s0 else "first figure for this week")
            log(f"    week {start}: units {u0} -> {u1}, on-hand {s0} -> {s1}: {kind} file, {kept}")


def dsi_numbers(db, pids: list[int]) -> dict:
    sell = db.execute(text("select count(*), coalesce(sum(units),0) from fact_sales_sellout where distributor_id = :d and product_id = any(:p)"),
                      {"d": PINNACLE, "p": pids}).one()
    inv = db.execute(text("select count(*), coalesce(sum(on_hand_units),0) from fact_inventory_distributor where distributor_id = :d and product_id = any(:p)"),
                     {"d": PINNACLE, "p": pids}).one()
    latest = db.scalar(text(
        "select coalesce(sum(x.on_hand_units),0) from (select distinct on (product_id) product_id, on_hand_units "
        "from fact_inventory_distributor where distributor_id = :d and product_id = any(:p) order by product_id, as_of_date desc) x"),
        {"d": PINNACLE, "p": pids})
    return {"sellout_rows": sell[0], "units": float(sell[1]), "inventory_rows": inv[0], "latest_on_hand": float(latest)}


def run_pinnacle(db, pids: list[int], round_no: int) -> None:
    from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

    stocks = [stock_series(k) for k in range(len(pids))]

    def job_with(lines: list[dict], name: str) -> tuple[int, tuple]:
        job = ImportJob(source_id=DSI_SOURCE, template_slug="distributor_inventory", import_mode="apply", status="pending",
                        stage="validated", file_name=name, tenant_id="default", staged_metadata={"n0111_proof": True})
        db.add(job)
        db.flush()
        for i, ln in enumerate(lines, 1):
            db.add(ImportDistributorSiStagingLine(import_job_id=job.id, source_row_number=i, resolved_distributor_id=PINNACLE,
                                                  resolved_customer_id=OPEN_CHANNEL, resolution_status="resolved", **ln))
        db.flush()
        res = upsert_dsi_facts_for_staging_job(db, job)
        db.commit()
        return int(job.id), res

    def history(year: int, bump: int = 0, weeks=None) -> list[dict]:
        out = []
        for w in range(WEEKS):
            if w in (GAP_WEEK, WEEKNO_WEEK) or (weeks is not None and w not in weeks):
                continue
            for i in range(7):
                d = START + timedelta(weeks=w, days=i)
                if year and d.year != year:
                    continue
                for k, pid in enumerate(pids):
                    q = units_for(d, k) + bump
                    if q > 0:
                        out.append({"resolved_product_id": pid, "transaction_date": d, "quantity_sold": q, "invoice_no": f"INV-{d:%Y%m%d}-{k}"})
                    if d.weekday() == 6:
                        out.append({"resolved_product_id": pid, "snapshot_date": d, "stock_on_hand": stocks[k][d] - bump})
        return out

    wk = START + timedelta(weeks=WEEKNO_WEEK)
    steps = [
        ("history 2023", history(2023)),
        ("history 2024", history(2024)),
        ("week-number only (no date)", [{"resolved_product_id": p, "transaction_date": None, "quantity_sold": 3,
                                         "invoice_no": f"W{wk.isocalendar()[1]}"} for p in pids]),
        ("sales-only week Z", [{"resolved_product_id": p, "transaction_date": Z, "quantity_sold": 5, "invoice_no": f"Z-{p}"} for p in pids]),
        ("stock-only week Z", [{"resolved_product_id": p, "snapshot_date": Z + timedelta(days=6), "stock_on_hand": 50} for p in pids]),
        ("history 2024 re-upload", history(2024)),
        ("correction weeks 61-62 (same invoices)", history(0, bump=1, weeks=CORRECTION_WEEKS)),
        ("correction week 61 (new invoice numbers)", [{"resolved_product_id": pids[0], "transaction_date": START + timedelta(weeks=60),
                                                       "quantity_sold": 2, "invoice_no": "CORR-1"}]),
    ]
    for name, lines in steps:
        before = dsi_numbers(db, pids)
        jid, res = job_with(lines, name)
        after = dsi_numbers(db, pids)
        log(f"  Pinnacle {name} (job {jid}): applied sell/ret/inv {res[0]}/{res[2]}/{res[1]} -> units {after['units']}, "
            f"latest on-hand {after['latest_on_hand']}, sellout rows {after['sellout_rows']}, inventory rows {after['inventory_rows']}")
        if name.startswith("stock-only"):
            log(f"    sell-out units {before['units']} -> {after['units']}: stock-only left sales unchanged")
        if name.startswith("sales-only"):
            log(f"    inventory rows {before['inventory_rows']} -> {after['inventory_rows']}, latest on-hand "
                f"{before['latest_on_hand']} -> {after['latest_on_hand']}: sales-only left stock unchanged")


def main() -> int:
    with SessionLocal() as db:
        cdb = db.execute(text("select current_database()")).scalar()
        log(f"current_database()={cdb}")
        if not str(cdb).startswith("cip_n0111"):
            raise SystemExit("refusing: not the N-0111 clone")
        pids = [int(r[0]) for r in db.execute(text(
            "select id from dim_product where sku is not null and sku not like 'SKU-%' "
            "and id not in (select product_id from fact_customer_sellthrough where customer_id in (20, 299)) "
            "and id not in (select product_id from fact_sales_sellout where distributor_id = 29) order by id limit 3")).all()]
        skus = [db.scalar(text("select sku from dim_product where id = :i"), {"i": p}) for p in pids]
        log(f"products {list(zip(pids, skus))}; window {START} to {Z1 + timedelta(days=6)}")
        snap = {}
        for c in CUSTOMERS:
            snap[(c, "before")] = cst_numbers(db, c, pids)
        snap[("P", "before")] = dsi_numbers(db, pids)
        for round_no in (1, 2):
            log(f"\n## Round {round_no}" + (" (re-run of the whole set)" if round_no == 2 else ""))
            for c, (label, source) in CUSTOMERS.items():
                run_customer(db, c, source, skus, pids, round_no)
                snap[(c, f"round{round_no}")] = cst_numbers(db, c, pids)
            run_pinnacle(db, pids, round_no)
            snap[("P", f"round{round_no}")] = dsi_numbers(db, pids)
        log("\n## Per source: before / after / after re-running the whole set")
        for c, (label, _) in CUSTOMERS.items():
            for stage in ("before", "round1", "round2"):
                n = snap[(c, stage)]
                log(f"  {label} ({c}) {stage}: units {n['units']}, latest on-hand {n['latest_on_hand']}, "
                    f"on-hand rows sum {n['on_hand_rows_sum']}, rows {n['rows']}, positions {n['positions']}, "
                    f"customer all units {n['customer_all_units']}")
            same = all(snap[(c, 'round1')][k] == snap[(c, 'round2')][k] for k in ("units", "latest_on_hand", "on_hand_rows_sum", "rows", "positions"))
            log(f"  {label}: re-run changed nothing: {same}")
        for stage in ("before", "round1", "round2"):
            log(f"  Pinnacle (29) {stage}: {snap[('P', stage)]}")
        log(f"  Pinnacle: re-run changed nothing: {snap[('P', 'round1')] == snap[('P', 'round2')]}")
    (Path(__file__).resolve().parent / "n0111_load_output.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
