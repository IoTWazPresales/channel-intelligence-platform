"""N-0111 repair item 6: recompute the derived customer stock positions once, then print the cause table.

Runs inside dbrun.py against one database. The write is the same service the Stock gap tab's
Recompute button calls (recompute_all_customer_stock_positions); customer_stock_position is a
derived table. The cause table uses the same classifier the tab uses, read only.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services import commercial_tenant_profile  # noqa: E402
from app.services.channel_intelligence.customer_stock_gap import (  # noqa: E402
    list_stock_positions,
    recompute_all_customer_stock_positions,
)
from app.services.channel_intelligence.customer_stock_gap_cause import CAUSE_ORDER  # noqa: E402

OUT = Path(__file__).resolve().parent / "recompute_stock_gap_output.txt"
lines: list[str] = []


def log(s: str) -> None:
    print(s, flush=True)
    lines.append(s)


def statuses(s) -> dict:
    return {r[0]: r[1] for r in s.execute(text("select status, count(*) from customer_stock_position group by 1 order by 1"))}


with SessionLocal() as s:
    db = s.execute(text("select current_database()")).scalar()
    log(f"current_database()={db}")
    if len(sys.argv) < 2 or sys.argv[1] != db:
        raise SystemExit(f"refusing: pass the database name ({db}) as the first argument to confirm")
    log(f"positions by status before: {statuses(s)}")
    tenants = [r[0] for r in s.execute(text(
        "select distinct tenant_id from fact_customer_sellthrough where reported_soh is not null order by 1"))]
    for tid in tenants:
        result = recompute_all_customer_stock_positions(s, tenant_id=tid)
        log(f"recompute tenant {tid}: {result}")
    s.commit()
    log(f"positions by status after: {statuses(s)}")

with SessionLocal() as s:
    s.execute(text("SET TRANSACTION READ ONLY"))
    for tid in [r[0] for r in s.execute(text("select distinct tenant_id from customer_stock_position order by 1"))]:
        threshold = commercial_tenant_profile.stock_gap_highlight_units(tid)
        rows = list_stock_positions(s, tenant_id=tid, threshold_units=threshold, limit=100000)
        compared = [r for r in rows if r["status"] == "compared"]
        flagged = [r for r in compared if r["highlighted"]]
        first = Counter(r["gap_cause"] for r in flagged)
        any_ = Counter(c for r in flagged for c in r["gap_causes"])
        log(json.dumps({
            "tenant": tid,
            "threshold_units": threshold,
            "positions": len(rows),
            "by_status": dict(Counter(r["status"] for r in rows)),
            "compared": len(compared),
            "flagged": len(flagged),
            "flagged_by_first_cause": {c: first.get(c, 0) for c in CAUSE_ORDER},
            "flagged_with_cause_anywhere": {c: any_.get(c, 0) for c in CAUSE_ORDER},
            "unexplained_by_customer": dict(Counter(r["customer_name"] for r in flagged if r["gap_cause"] == "unexplained")),
        }, indent=1))
    s.rollback()
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
