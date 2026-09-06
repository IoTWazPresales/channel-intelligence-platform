"""Read-only NUMBER RULE: prove movement-lens week-key alignment vs sell-out tape.

Prints current_database() first. Does not write.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import func, select, text

from app.core.tenant_scope import tenant_id_from_user
from app.db.session import AsyncSessionLocal
from app.models.dimensions import DimProduct
from app.models.facts import FactSalesSellout


def iso_week_label(value: date) -> str:
    return f"W{value.isocalendar().week:02d}"


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        tz = (await db.execute(text("SHOW timezone"))).scalar()
        print(f"timezone={tz}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2

        tid = tenant_id_from_user(None)
        print(f"tenant_id={tid}")

        so_max = await db.scalar(
            select(func.max(FactSalesSellout.transaction_date)).where(FactSalesSellout.tenant_id == tid)
        )
        print(f"so_max={so_max!r} type={type(so_max).__name__}")
        if so_max is None:
            print("no sell-out")
            return 0

        sample = (
            await db.execute(
                text(
                    """
                    SELECT
                      date_trunc('week', transaction_date) AS wk_trunc,
                      pg_typeof(date_trunc('week', transaction_date)) AS wk_typeof,
                      CAST(date_trunc('week', transaction_date) AS date) AS wk_date,
                      transaction_date
                        - CAST(EXTRACT(ISODOW FROM transaction_date) AS int)
                        + 1 AS iso_monday,
                      EXTRACT(WEEK FROM transaction_date) AS iso_week,
                      SUM(units) AS units
                    FROM fact_sales_sellout
                    WHERE tenant_id = :tid
                      AND transaction_date >= CAST(:so_max AS date) - 14
                      AND transaction_date <= CAST(:so_max AS date)
                    GROUP BY 1, 2, 3, 4, 5
                    ORDER BY 1
                    """
                ),
                {"tid": tid, "so_max": so_max},
            )
        ).all()
        print("PG_WEEK_KEYS")
        for r in sample:
            print(
                f"  trunc={r[0]!r} typeof={r[1]} as_date={r[2]} iso_monday={r[3]} iso_week={r[4]} units={r[5]}"
            )

        weeks = 13
        start = so_max - timedelta(days=weeks * 7)
        so_week = func.date_trunc("week", FactSalesSellout.transaction_date)
        so_rows = (
            await db.execute(
                select(so_week.label("wk"), func.coalesce(func.sum(FactSalesSellout.units), 0))
                .where(FactSalesSellout.tenant_id == tid)
                .where(FactSalesSellout.transaction_date >= start)
                .where(FactSalesSellout.transaction_date <= so_max)
                .group_by(so_week)
                .order_by(so_week)
            )
        ).all()
        sell_map_raw: dict = {}
        sell_map_norm: dict = {}
        print("SA_WEEK_KEYS")
        for r in so_rows:
            wk = r.wk
            print(f"  wk={wk!r} type={type(wk).__name__} units={r[1]}")
            as_date = wk.date() if hasattr(wk, "date") else wk
            sell_map_raw[as_date] = float(r[1] or 0)
            if isinstance(as_date, date):
                monday = as_date - timedelta(days=as_date.weekday())
                sell_map_norm[monday] = float(r[1] or 0)

        end_monday = so_max - timedelta(days=so_max.weekday())
        cursor = end_monday - timedelta(days=7 * (weeks - 1))
        last_raw = last_norm = None
        last_raw_u = last_norm_u = None
        while cursor <= end_monday:
            last_raw, last_raw_u = iso_week_label(cursor), sell_map_raw.get(cursor, 0.0)
            last_norm, last_norm_u = iso_week_label(cursor), sell_map_norm.get(cursor, 0.0)
            cursor += timedelta(days=7)
        print(f"python_end_monday={end_monday} label={iso_week_label(end_monday)}")
        print(f"OLD_headline_week={last_raw} units={last_raw_u}")
        print(f"NEW_headline_week={last_norm} units={last_norm_u}")
        print(f"raw_key_count={len(sell_map_raw)} sample_keys={list(sell_map_raw)[-3:]}")
        print(f"norm_key_count={len(sell_map_norm)} sample_keys={list(sell_map_norm)[-3:]}")

        # ISO-week truth for last complete labelled week of so_max
        truth = (
            await db.execute(
                text(
                    """
                    SELECT
                      CAST(EXTRACT(WEEK FROM transaction_date) AS int) AS iso_week,
                      MIN(
                        transaction_date
                        - CAST(EXTRACT(ISODOW FROM transaction_date) AS int)
                        + 1
                      ) AS monday,
                      SUM(units) AS units
                    FROM fact_sales_sellout
                    WHERE tenant_id = :tid
                      AND transaction_date
                        - CAST(EXTRACT(ISODOW FROM transaction_date) AS int)
                        + 1
                          = CAST(:so_max AS date)
                            - CAST(EXTRACT(ISODOW FROM CAST(:so_max AS date)) AS int)
                            + 1
                    GROUP BY 1
                    """
                ),
                {"tid": tid, "so_max": so_max},
            )
        ).all()
        print("ISO_WEEK_OF_SO_MAX")
        for r in truth:
            print(f"  W{int(r[0]):02d} monday={r[1]} units={r[2]}")

        prev_monday = end_monday - timedelta(days=7)
        prev_truth = (
            await db.execute(
                text(
                    """
                    SELECT SUM(units)
                    FROM fact_sales_sellout
                    WHERE tenant_id = :tid
                      AND transaction_date
                        - CAST(EXTRACT(ISODOW FROM transaction_date) AS int)
                        + 1
                          = CAST(:prev AS date)
                    """
                ),
                {"tid": tid, "prev": prev_monday},
            )
        ).scalar()
        print(f"prior_iso_week_units={prev_truth} prior_monday={prev_monday} label={iso_week_label(prev_monday)}")

        # family growing using ISO monday vs date_trunc python compare (old)
        family_col = func.coalesce(
            func.nullif(DimProduct.product_line, ""),
            func.nullif(DimProduct.category, ""),
            "Unclassified",
        )
        fam_rows = (
            await db.execute(
                select(family_col.label("family"), so_week.label("wk"), func.coalesce(func.sum(FactSalesSellout.units), 0))
                .join(DimProduct, FactSalesSellout.product_id == DimProduct.id)
                .where(FactSalesSellout.tenant_id == tid)
                .where(FactSalesSellout.transaction_date >= prev_monday)
                .where(FactSalesSellout.transaction_date < end_monday + timedelta(days=7))
                .group_by(family_col, so_week)
            )
        ).all()
        this_old: dict[str, float] = {}
        prev_old: dict[str, float] = {}
        this_new: dict[str, float] = {}
        prev_new: dict[str, float] = {}
        for r in fam_rows:
            wk = r.wk.date() if hasattr(r.wk, "date") else r.wk
            fam = str(r.family or "Unclassified")
            units = float(r[2] or 0)
            if wk == end_monday:
                this_old[fam] = units
            else:
                prev_old[fam] = units
            monday = wk - timedelta(days=wk.weekday()) if isinstance(wk, date) else wk
            if monday == end_monday:
                this_new[fam] = units
            else:
                prev_new[fam] = units
        names_old = sorted(set(this_old) | set(prev_old), key=lambda n: -this_old.get(n, 0.0))
        names_new = sorted(set(this_new) | set(prev_new), key=lambda n: -this_new.get(n, 0.0))
        grow_old = sum(1 for f in names_old if this_old.get(f, 0.0) > prev_old.get(f, 0.0))
        grow_new = sum(1 for f in names_new if this_new.get(f, 0.0) > prev_new.get(f, 0.0))
        print(f"OLD_families_growing={grow_old} of {len(names_old)} this_keys={len(this_old)} prev_keys={len(prev_old)}")
        print(f"NEW_families_growing={grow_new} of {len(names_new)} this_keys={len(this_new)} prev_keys={len(prev_new)}")
        print("NEW_family_rows")
        for f in names_new:
            print(f"  {f}: curr={this_new.get(f, 0.0)} prev={prev_new.get(f, 0.0)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
