"""GOV-008 N-0065: does a request-path sync SessionLocal() honour the bound scope? (read-only, cip)

Run from apps/api with its virtualenv. Binds the request contextvars exactly as
the router does for a non-admin with no assignment (empty read and edit), then
counts product rows through (a) the async get_db session the router scopes and
(b) a sync SessionLocal() as opened by many endpoints (e.g. GET /forecasts/rollups).
Both transactions are READ ONLY and rolled back. Prints current_database() first.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.product_line_scope import (
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
)

Q_PRODUCTS = "select count(*) from dim_product"
Q_FORECAST = "select count(*) from fact_demand_forecast"


def sync_path() -> None:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as s:
        db = s.execute(text("select current_database()")).scalar_one()
        print("[sync SessionLocal] current_database() =", db)
        assert db == "cip"
        s.rollback()
        s.execute(text("SET TRANSACTION READ ONLY"))
        print("[sync SessionLocal] cip.product_lines =", s.execute(text("select current_setting('cip.product_lines', true)")).scalar_one())
        print("[sync SessionLocal] dim_product =", s.execute(text(Q_PRODUCTS)).scalar_one(),
              "fact_demand_forecast =", s.execute(text(Q_FORECAST)).scalar_one())
        s.rollback()


async def async_path() -> None:
    from app.api.deps import get_db

    gen = get_db()
    s = await gen.__anext__()
    try:
        db = (await s.execute(text("select current_database()"))).scalar_one()
        print("[async get_db] current_database() =", db)
        assert db == "cip"
        await s.execute(text("SET TRANSACTION READ ONLY"))
        print("[async get_db] cip.product_lines =", repr((await s.execute(text("select current_setting('cip.product_lines', true)"))).scalar_one()))
        print("[async get_db] dim_product =", (await s.execute(text(Q_PRODUCTS))).scalar_one(),
              "fact_demand_forecast =", (await s.execute(text(Q_FORECAST))).scalar_one())
        await s.rollback()
    finally:
        await gen.aclose()


def main() -> int:
    read, edit = product_line_scope_for(is_admin=False, assignments=[])
    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        print("bound request scope (non-admin, no rows):", read, edit)
        asyncio.run(async_path())
        sync_path()
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
