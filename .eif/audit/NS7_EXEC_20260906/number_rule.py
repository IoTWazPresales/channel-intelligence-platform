"""Read-only NUMBER RULE proof for Execution vs plan on cip.

Prints current_database() then the same scorecard/default_period path the lab strip uses
(collect_execution_rows + compute_scorecard_from_execution_rows). Does not write.
"""
from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.commercial_planner.plan_vs_executed import (
    collect_execution_rows,
    compute_scorecard_from_execution_rows,
    coverage,
    lineup_linked_year_quarters,
    periods_from_coverage,
    resolve_default_period,
)


def customers_under_plan_share(rows: list[dict], threshold: float = 0.7) -> int:
    rolled: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        key = (r.get("customer_label") or "").strip() or (
            f"Customer {r.get('customer_id')}" if r.get("customer_id") is not None else "Unnamed"
        )
        rolled[key][0] += float(r.get("planned_units") or 0)
        rolled[key][1] += float(r.get("shipped_units") or 0)
    return sum(1 for plan, shipped in rolled.values() if plan > 0 and shipped / plan < threshold)


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2
        cov = await coverage(db)
        all_periods = periods_from_coverage(cov)
        lineup_quarters = await lineup_linked_year_quarters(db)
        default_period = resolve_default_period(
            all_periods,
            coverage_groups=cov.get("groups"),
            lineup_linked_quarters=lineup_quarters,
        )
        rows = await collect_execution_rows(
            db,
            period_from=default_period,
            period_to=default_period,
            product_line=None,
        )
        sc = compute_scorecard_from_execution_rows(rows)
        planned = sc["planned_units"]
        shipped = sc["shipped_units_in_plan"]
        pct = round((shipped / planned) * 100) if planned else None
        under70 = customers_under_plan_share(rows)
        print(f"default_period={default_period}")
        print(f"drill_row_count={len(rows)}")
        print(f"planned_units={planned}")
        print(f"shipped_units_in_plan={shipped}")
        print(f"pct_of_plan={pct}")
        print(f"customers_under_70pct={under70}")
        print("lab_fixture_p09_used=false")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
