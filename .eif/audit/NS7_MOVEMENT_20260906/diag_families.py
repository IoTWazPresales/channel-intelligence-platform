"""Family WoW on cip using ISO-Monday dates. Read-only. Prints current_database() first."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2
        rows = (
            await db.execute(
                text(
                    """
                    WITH weeks AS (
                      SELECT
                        COALESCE(NULLIF(p.product_line, ''), NULLIF(p.category, ''), 'Unclassified') AS family,
                        f.transaction_date
                          - CAST(EXTRACT(ISODOW FROM f.transaction_date) AS int)
                          + 1 AS monday,
                        SUM(f.units) AS units
                      FROM fact_sales_sellout f
                      JOIN dim_product p ON p.id = f.product_id
                      WHERE f.tenant_id = 'default'
                        AND f.transaction_date >= DATE '2026-06-01'
                        AND f.transaction_date < DATE '2026-06-15'
                      GROUP BY 1, 2
                    )
                    SELECT
                      COALESCE(a.family, b.family) AS family,
                      COALESCE(a.units, 0) AS w24,
                      COALESCE(b.units, 0) AS w23
                    FROM (SELECT * FROM weeks WHERE monday = DATE '2026-06-08') a
                    FULL OUTER JOIN (SELECT * FROM weeks WHERE monday = DATE '2026-06-01') b
                      ON a.family = b.family
                    ORDER BY COALESCE(a.units, 0) DESC
                    """
                )
            )
        ).all()
        growing = 0
        for r in rows:
            print(f"  {r[0]}: W24={r[1]} W23={r[2]} growing={float(r[1]) > float(r[2])}")
            if float(r[1]) > float(r[2]):
                growing += 1
        print(f"families_growing={growing} of {len(rows)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
