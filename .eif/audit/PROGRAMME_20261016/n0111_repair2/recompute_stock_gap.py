"""N-0111 repair 2: recompute the derived customer stock positions once (bridge rule D-0112) and print the
status table before and after: compared / flagged / no on-hand reported / unreported weeks / first report.

Runs inside dbrun.py against one database. The write is the service the Stock gap tab's Recompute button
calls (recompute_all_customer_stock_positions); customer_stock_position is a derived table.
usage (cwd any): python recompute_stock_gap.py <dbname>      (the name must match current_database())
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

OUT = Path(__file__).resolve().parent / "recompute_stock_gap_output.txt"
lines: list[str] = []


def log(s: str) -> None:
    print(s, flush=True)
    lines.append(s)


def table(s, label: str) -> None:
    """Status table from the stored positions (read in a read-only view of this session)."""
    out = {}
    for tid in [r[0] for r in s.execute(text("select distinct tenant_id from customer_stock_position order by 1"))]:
        threshold = commercial_tenant_profile.stock_gap_highlight_units(tid)
        rows = list_stock_positions(s, tenant_id=tid, threshold_units=threshold, limit=1_000_000)
        by = Counter(r["status"] for r in rows)
        compared = [r for r in rows if r["status"] == "compared"]
        flagged = [r for r in compared if r["highlighted"]]
        out[tid] = {
            "threshold_units": threshold,
            "positions": len(rows),
            "compared": len(compared),
            "flagged (compared, |gap| >= threshold)": len(flagged),
            "no on-hand reported (no_on_hand)": by.get("no_on_hand", 0),
            "unreported weeks (stored chain_restart)": by.get("chain_restart", 0),
            "first report": by.get("first_report", 0),
            "by customer [compared, no_on_hand, unreported(chain_restart), first_report]": {
                name: [
                    sum(1 for r in rows if r["customer_name"] == name and r["status"] == st)
                    for st in ("compared", "no_on_hand", "chain_restart", "first_report")
                ]
                for name in sorted({r["customer_name"] for r in rows})
            },
            "flagged by first cause": dict(Counter(r["gap_cause"] for r in flagged)),
        }
        # flagged per customer, as its own small map
        out[tid]["flagged by customer"] = dict(Counter(r["customer_name"] for r in flagged))
    log(f"--- status table {label} ---")
    log(json.dumps(out, indent=1, default=str))


with SessionLocal() as s:
    db = s.execute(text("select current_database()")).scalar()
    log(f"current_database()={db}")
    if len(sys.argv) < 2 or sys.argv[1] != db:
        raise SystemExit(f"refusing: pass the database name ({db}) as the first argument to confirm")
    s.execute(text("SET TRANSACTION READ ONLY"))
    table(s, "BEFORE (stored positions, previous rule)")
    s.rollback()

with SessionLocal() as s:
    tenants = [r[0] for r in s.execute(text(
        "select distinct tenant_id from fact_customer_sellthrough where reported_soh is not null order by 1"))]
    for tid in tenants:
        result = recompute_all_customer_stock_positions(s, tenant_id=tid)
        log(f"recompute tenant {tid}: {result}")
    s.commit()

with SessionLocal() as s:
    s.execute(text("SET TRANSACTION READ ONLY"))
    table(s, "AFTER (bridge rule)")
    s.rollback()
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
