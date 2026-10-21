"""N-0110 repair: read-only look at the positions the classifier leaves unexplained."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.channel_intelligence.customer_stock_gap import list_stock_positions  # noqa: E402

with SessionLocal() as s:
    s.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database()=" + s.execute(text("select current_database()")).scalar())
    rows = [r for r in list_stock_positions(s, tenant_id="default", threshold_units=1, limit=100000) if r["highlighted"]]
    un = [r for r in rows if r["gap_cause"] == "unexplained"]
    pids = sorted({r["product_id"] for r in un})
    ship = s.execute(
        text(
            "select product_id, resolved_customer_id is null unmatched, pod_date is null no_pod, lower(line_state) st, "
            "count(*), sum(quantity), min(coalesce(pod_date, ship_confirm_date)), max(coalesce(pod_date, ship_confirm_date)) "
            "from fact_inbound_shipment where product_id = any(:p) group by 1,2,3,4"
        ),
        {"p": pids},
    ).all()
    agg = Counter()
    for pid, unm, nopod, st, n, q, lo, hi in ship:
        agg[(("unmatched" if unm else "matched"), ("no_pod" if nopod else "pod"), st)] += int(n)
    print("shipment lines for unexplained products:", {"/".join(k): v for k, v in sorted(agg.items())})
    print("shipment date range:", s.execute(text("select min(pod_date), max(pod_date), min(ship_confirm_date), max(ship_confirm_date) from fact_inbound_shipment where product_id = any(:p)"), {"p": pids}).one())
    print("matched customers on those lines:", s.execute(text("select resolved_customer_id, count(*) from fact_inbound_shipment where product_id = any(:p) group by 1 order by 2 desc limit 8"), {"p": pids}).all())
    spans = Counter()
    for r in un:
        d = (date.fromisoformat(r["period_end_date"]) - date.fromisoformat(r["previous_period_end_date"])).days
        spans[(r["customer_name"], "<=7d" if d <= 7 else "<=35d" if d <= 35 else ">35d")] += 1
    print("window length:", {f"{a} {b}": n for (a, b), n in sorted(spans.items())})
    rec = Counter((r["customer_name"], "receipts>0" if (r["receipts_units"] or 0) > 0 else "no receipts") for r in un)
    print("receipts in window:", {f"{a} {b}": n for (a, b), n in sorted(rec.items())})
    fut = s.execute(
        text(
            "select f.customer_id, f.period_start_date, count(*) from fact_customer_sellthrough f join import_job j on j.id=f.import_job_id "
            "where f.period_start_date > j.created_at::date group by 1,2"
        )
    ).all()
    print("rows dated after their load:", fut)
    futset = {(c, d) for c, _, d in [(a, None, b) for a, b, _ in fut]}
    hit = sum(
        1
        for r in un
        if (r["customer_id"], date.fromisoformat(r["period_start_date"])) in futset
        or any(
            (r["customer_id"], d) in futset
            for d in [date.fromisoformat(r["previous_period_end_date"])]
        )
    )
    print("unexplained rows whose report period is a week dated after its load:", hit)
    cm = [r for r in un if r["customer_name"] == "Computer Mania"][:6]
    for r in cm:
        print(json.dumps({k: r[k] for k in ("sku", "period_start_date", "previous_period_end_date", "previous_on_hand", "receipts_units", "units_sold", "expected_on_hand", "reported_on_hand", "gap_units")}))
    s.rollback()
