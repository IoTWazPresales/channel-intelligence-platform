"""SESSION D Task 1: 26Q3 fill-rate numerator/denominator on cip (read-only)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.commercial_planner.plan_vs_executed import (  # noqa: E402
    collect_execution_rows,
    compute_scorecard_from_execution_rows,
)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database()", dbname)
        rows = await collect_execution_rows(db, period_from="26Q3", period_to="26Q3")
        sc = compute_scorecard_from_execution_rows(rows)
        in_plan = [r for r in rows if float(r.get("planned_units") or 0) > 0]
        sum_p = sum(float(r["planned_units"]) for r in in_plan)
        sum_s = sum(float(r["shipped_units"]) for r in in_plan)
        sum_min = sum(min(float(r["shipped_units"]), float(r["planned_units"])) for r in in_plan)
        print("in_plan_row_count", len(in_plan))
        print("all_row_count", len(rows))
        print("denominator_sum_planned", sum_p)
        print("numerator_sum_min_shipped_capped", sum_min)
        print("shipped_units_in_plan_uncapped", sum_s)
        print("fill_rate", sc.get("fill_rate"))
        print("fill_rate_pct_1dp", None if sc.get("fill_rate") is None else round(sc["fill_rate"] * 100, 1))
        print("scorecard_planned_units", sc.get("planned_units"))
        print("scorecard_shipped_units_in_plan", sc.get("shipped_units_in_plan"))
        print("scorecard_shipped_units_total", sc.get("shipped_units_total"))
        if sum_p:
            print("13.2pct_of_today_planned", round(0.132 * sum_p, 1))
            print("implied_planned_if_num_fixed_at_sum_min_for_13.2pct", round(sum_min / 0.132, 1) if sum_min else None)


if __name__ == "__main__":
    asyncio.run(main())
