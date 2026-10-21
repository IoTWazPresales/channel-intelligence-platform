"""N-0110 repair: read-only. Why each highlighted stock gap differs, counted per cause.

Runs inside dbrun.py against one database, in a READ ONLY transaction, through the same
classifier the Stock gap tab uses.
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
from app.services.channel_intelligence.customer_stock_gap import list_stock_positions  # noqa: E402
from app.services.channel_intelligence.customer_stock_gap_cause import CAUSE_ORDER  # noqa: E402

with SessionLocal() as s:
    s.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database()=" + s.execute(text("select current_database()")).scalar())
    tenants = [r[0] for r in s.execute(text("select distinct tenant_id from customer_stock_position order by 1"))]
    for tid in tenants:
        threshold = commercial_tenant_profile.stock_gap_highlight_units(tid)
        rows = list_stock_positions(s, tenant_id=tid, threshold_units=threshold, limit=100000)
        compared = [r for r in rows if r["status"] == "compared"]
        flagged = [r for r in compared if r["highlighted"]]
        first = Counter(r["gap_cause"] for r in flagged)
        any_ = Counter(c for r in flagged for c in r["gap_causes"])
        by_sign = Counter((r["gap_cause"], "short" if r["gap_units"] < 0 else "over") for r in flagged)
        overwrite_by = Counter(r["gap_cause_detail"].get("overwrite_by") for r in flagged if "overwrite" in r["gap_causes"])
        print(
            json.dumps(
                {
                    "tenant": tid,
                    "threshold_units": threshold,
                    "positions": len(rows),
                    "compared": len(compared),
                    "flagged": len(flagged),
                    "flagged_by_first_cause": {c: first.get(c, 0) for c in CAUSE_ORDER},
                    "flagged_with_cause_anywhere": {c: any_.get(c, 0) for c in CAUSE_ORDER},
                    "first_cause_by_sign": {f"{c}/{sg}": n for (c, sg), n in sorted(by_sign.items())},
                    "overwrite_by": dict(overwrite_by),
                    "unexplained_by_customer": dict(
                        Counter(r["customer_name"] for r in flagged if r["gap_cause"] == "unexplained")
                    ),
                },
                indent=1,
            )
        )
    s.rollback()
