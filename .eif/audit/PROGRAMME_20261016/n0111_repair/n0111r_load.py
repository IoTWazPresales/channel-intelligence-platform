"""N-0111 repair: proof load on a CLONE of cip (run through dbrun.py <clone>).

A. Customer sell-through, Amazon (299), through the real pipeline (job + raw file ->
   process_import_job_sync: parse, resolve, apply):
   - a file whose sale-date column is headed just "Date" (item 1);
   - a week-number file running W51, W52, W1, W2 with year 2024 confirmed (item 3);
   - a file with a row missing units and a row with an unknown product (item 2: the job says so).
   Then the same three files again: totals unchanged.
B. Pinnacle (distributor 29) through the real DSI fact apply (upsert_dsi_facts_for_staging_job) from
   resolved staging lines (item 4): load, reload of the same invoices with changed figures, correction
   (same invoices, plus one new invoice); re-apply of the correction; re-run of the whole set.
   Prints totals and superseded counts after each step, and each job's load report.

Refuses to run unless current_database() starts with cip_n0111r.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.ingestion.pipeline import process_import_job_sync  # noqa: E402
from app.models.import_distributor_si import ImportDistributorSiStagingLine  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.imports.import_load_report import display_status, load_report_sync  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

AMAZON, AMAZON_SOURCE = 299, 21
PINNACLE, DSI_SOURCE, DSI_CUSTOMER = 29, 12, 20
DAY0 = date(2024, 3, 4)
OUT: list[str] = []


def log(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


def csv(rows: list[list]) -> bytes:
    return ("\n".join(",".join(str(c) for c in r) for r in rows) + "\n").encode()


def report_line(db, job_id: int) -> str:
    job = db.get(ImportJob, job_id)
    rep = load_report_sync(db, job)
    reasons = ", ".join(f"{i['reason']} {i['rows']}" for i in rep["not_loaded"]) or "none"
    return (f"status {job.status} -> shown as '{display_status(job.status, rep)}'; read {rep['rows_read']}, "
            f"loaded {rep['rows_loaded']}, not loaded {rep['rows_not_loaded']}, partly {rep['rows_partly_loaded']}; "
            f"reasons: {reasons}")


# ------------------------------------------------------------------ A: customer sell-through


def cst_job(db, name: str, data: bytes, flags: dict) -> int:
    meta = {"customer_id": AMAZON, "report_structure_type": "flat", "cst_batch_filenames": [name], **flags}
    job = ImportJob(source_id=AMAZON_SOURCE, template_slug="customer_sell_through", import_mode="apply",
                    status="pending", stage="uploaded", file_name=name, tenant_id="default", staged_metadata=meta)
    db.add(job)
    db.flush()
    key = f"imports/n0111r-proof/{uuid.uuid4().hex}/{name}"
    get_storage_backend().save(key, data, "text/csv")
    db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(data), checksum=None))
    db.commit()
    process_import_job_sync(db, job.id)
    db.commit()
    return int(job.id)


def cst_numbers(db, pids: list[int]) -> dict:
    r = db.execute(text(
        "select count(*), coalesce(sum(units_sold),0), coalesce(sum(reported_soh),0) from fact_customer_sellthrough "
        "where customer_id = :c and product_id = any(:p)"), {"c": AMAZON, "p": pids}).one()
    grains = db.execute(text(
        "select period_grain, period_year, period_week, period_start_date, count(*), sum(units_sold) "
        "from fact_customer_sellthrough where customer_id = :c and product_id = any(:p) "
        "group by 1, 2, 3, 4 order by 4"), {"c": AMAZON, "p": pids}).all()
    return {"rows": r[0], "units": float(r[1]), "on_hand_sum": float(r[2]),
            "periods": [(g[0], g[1], g[2], str(g[3]), g[4], float(g[5])) for g in grains]}


def run_cst(db, skus: list[str], pids: list[int]) -> None:
    date_rows = [["Date", "SKU", "Units Sold", "SOH"]]
    for i in range(3):
        for k, sku in enumerate(skus):
            date_rows.append([(DAY0 + timedelta(days=i)).isoformat(), sku, 1 + k + i, 50 - i])
    week_rows = [["Week", "SKU", "Units Sold", "SOH"]]
    for wk in ("W51", "W52", "W1", "W2"):
        for k, sku in enumerate(skus):
            week_rows.append([wk, sku, 2 + k, 40 + k])
    drop_rows = [["Date", "SKU", "Units Sold", "SOH"],
                 [DAY0.isoformat(), skus[0], "", 30],
                 [DAY0.isoformat(), "N0111R-UNKNOWN-SKU", 4, 30],
                 [(DAY0 + timedelta(days=7)).isoformat(), skus[1], 6, 20]]
    files = [
        ("amazon date header.csv", csv(date_rows), {}),
        ("amazon 2024 W51-W2.csv", csv(week_rows), {"cst_confirmed_year": 2024}),
        ("amazon with dropped rows.csv", csv(drop_rows), {}),
    ]
    snaps = []
    for round_no in (1, 2):
        log(f"\n### Customer sell-through, round {round_no}" + (" (same three files again)" if round_no == 2 else ""))
        for name, data, flags in files:
            jid = cst_job(db, name, data, flags)
            log(f"  {name} (job {jid}): {report_line(db, jid)}")
        n = cst_numbers(db, pids)
        snaps.append(n)
        log(f"  Amazon synthetic products: rows {n['rows']}, units {n['units']}, on-hand rows sum {n['on_hand_sum']}")
        for p in n["periods"]:
            log(f"    grain {p[0]}, year {p[1]}, week {p[2]}, start {p[3]}: rows {p[4]}, units {p[5]}")
    log(f"  re-running the three files changed nothing: {snaps[0] == snaps[1]}")


# ------------------------------------------------------------------ B: Pinnacle


def dsi_numbers(db, pids: list[int]) -> dict:
    sell = db.execute(text("select count(*), coalesce(sum(units),0), coalesce(sum(revenue),0) from fact_sales_sellout "
                           "where distributor_id = :d and product_id = any(:p)"), {"d": PINNACLE, "p": pids}).one()
    ret = db.execute(text("select count(*), coalesce(sum(return_quantity),0) from fact_returns "
                          "where distributor_id = :d and product_id = any(:p)"), {"d": PINNACLE, "p": pids}).one()
    kept = dict(db.execute(text("select fact_table, count(*) from fact_distributor_line_superseded "
                                "where distributor_id = :d and product_id = any(:p) group by 1"),
                           {"d": PINNACLE, "p": pids}).all())
    return {"sellout_rows": sell[0], "units": float(sell[1]), "revenue": float(sell[2]), "return_rows": ret[0],
            "returned": float(ret[1]), "superseded_sellout": kept.get("fact_sales_sellout", 0),
            "superseded_returns": kept.get("fact_returns", 0)}


def run_pinnacle(db, pids: list[int]) -> None:
    from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

    def lines(qty_for, *, extra: list[dict] | None = None) -> list[dict]:
        out = []
        for i in range(10):
            pid = pids[i % len(pids)]
            q = qty_for(i)
            out.append({"resolved_product_id": pid, "transaction_date": DAY0 + timedelta(days=i), "quantity_sold": q,
                        "reported_revenue_amount": q * 100, "invoice_no": f"N111R-INV-{i + 1}"})
        out.append({"resolved_product_id": pids[0], "transaction_date": DAY0, "quantity_sold": -1 if qty_for(0) == 3 else -2,
                    "invoice_no": "N111R-CR-1"})
        return out + (extra or [])

    sets = [
        ("load", lines(lambda i: 3)),
        ("reload same invoices (4 lines and the credit changed)", lines(lambda i: 5 if i < 4 else 3)),
        ("correction (2 lines back to 4) plus new invoice N111R-INV-11",
         lines(lambda i: 4 if i < 2 else (5 if i < 4 else 3),
               extra=[{"resolved_product_id": pids[1], "transaction_date": DAY0, "quantity_sold": 2,
                       "reported_revenue_amount": 200, "invoice_no": "N111R-INV-11"}])),
    ]

    def new_job(name: str, rows: list[dict]) -> ImportJob:
        job = ImportJob(source_id=DSI_SOURCE, template_slug="distributor_inventory", import_mode="apply",
                        status="completed", stage="validated", file_name=name, tenant_id="default", staged_metadata={})
        db.add(job)
        db.flush()
        for i, ln in enumerate(rows, 1):
            db.add(ImportDistributorSiStagingLine(import_job_id=job.id, source_row_number=i,
                                                  resolved_distributor_id=PINNACLE, resolved_customer_id=DSI_CUSTOMER,
                                                  resolution_status="resolved", **ln))
        db.flush()
        return job

    def apply(job: ImportJob, label: str) -> dict:
        sell, inv, ret, errors = upsert_dsi_facts_for_staging_job(db, job)
        db.commit()
        n = dsi_numbers(db, pids)
        log(f"  {label} (job {job.id}): applied sell/ret/inv {sell}/{ret}/{inv}, errors {len(errors)} -> {n}")
        log(f"    load report: {report_line(db, int(job.id))}")
        return n

    log("\n### Pinnacle (29), distributor sell-out and returns")
    log(f"  before: {dsi_numbers(db, pids)}")
    jobs = []
    for name, rows in sets:
        job = new_job(name, rows)
        jobs.append(job)
        last = apply(job, name)
    again = apply(jobs[-1], "re-apply the correction")
    log(f"  re-applying the correction changed nothing (totals and superseded counts): {again == last}")
    log("  re-run of the whole set (the three loads applied again in order):")
    for job, (name, _rows) in zip(jobs, sets):
        rerun = apply(job, f"re-run: {name}")
    same_totals = all(rerun[k] == last[k] for k in ("sellout_rows", "units", "revenue", "return_rows", "returned"))
    log(f"  re-run of the whole set left the totals unchanged: {same_totals}; superseded sell-out "
        f"{last['superseded_sellout']} -> {rerun['superseded_sellout']}, returns {last['superseded_returns']} -> "
        f"{rerun['superseded_returns']} (re-applying an older load replaces the newer figures again, and keeps them)")


def main() -> int:
    with SessionLocal() as db:
        cdb = db.execute(text("select current_database()")).scalar()
        log(f"current_database()={cdb}")
        if not str(cdb).startswith("cip_n0111r"):
            raise SystemExit("refusing: not the N-0111 repair clone")
        pids = [int(r[0]) for r in db.execute(text(
            "select id from dim_product where sku is not null and sku not like 'SKU-%' "
            "and id not in (select product_id from fact_customer_sellthrough where customer_id = 299) "
            "and id not in (select product_id from fact_sales_sellout where distributor_id = 29) order by id limit 3")).all()]
        skus = [db.scalar(text("select sku from dim_product where id = :i"), {"i": p}) for p in pids]
        log(f"products {list(zip(pids, skus))}")
        run_cst(db, skus, pids)
        run_pinnacle(db, pids)
    (Path(__file__).resolve().parent / "n0111r_load_output.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
