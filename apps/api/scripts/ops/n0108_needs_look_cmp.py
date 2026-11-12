"""Compare needs-a-look signal inputs, old path against new. Read-only. Stops unless cip.

Old path: the fact id and quantity query runs on the request session, which is
how brief built this signal before the overlap change. New path: the same query
goes through gather_reads, which opens a second pooled connection for an
engine-bound session. On committed rows the two lists must match row for row.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cip:cip@localhost:5432/cip")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

from sqlalchemy import event, select, text

from app.core.my_accounts import apply_account_predicate
from app.core.tenant_scope import tenant_id_from_user
from app.db.parallel_reads import gather_reads
from app.db.session import AsyncSessionLocal, engine
from app.models.facts import FactInboundShipment as F
from app.services.brief_signals import _needs_look_summary
from app.services.commercial_tenant_profile import on_the_water_overrides, reporting_today
from app.services.imports.shipment_open_book import exclude_closed_inbound
from app.services.shipping.on_the_water import config_from_overrides
from app.services.shipping_commercial_kpis import predicate_needs_look


def _read_only(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()


event.listen(engine.sync_engine, "connect", _read_only)


def _stmt(user):
    tenant = tenant_id_from_user(user)
    days = config_from_overrides(on_the_water_overrides(tenant)).needs_look_days
    stmt = apply_account_predicate(
        select(F.id, F.quantity).where(
            F.tenant_id == tenant,
            predicate_needs_look(reporting_today(tenant), days),
            exclude_closed_inbound(F),
        ),
        F.resolved_customer_id,
    )
    return stmt, days


async def _rows(session, stmt):
    found = (await session.execute(stmt)).all()
    return sorted((int(i), float(q or 0)) for i, q in found)


async def main() -> None:
    stmt, days = _stmt(None)
    async with AsyncSessionLocal() as caller:
        name = (await caller.execute(text("select current_database()"))).scalar()
        if name != "cip":
            raise SystemExit(f"STOP: database is {name!r}, not cip")
        old_rows = await _rows(caller, stmt)
        old_summary = await _needs_look_summary(caller, None)
        new_rows, new_summary = await gather_reads(
            caller,
            lambda session: _rows(session, stmt),
            lambda session: _needs_look_summary(session, None),
        )
        await caller.rollback()
    old_units = sum(q for _i, q in old_rows)
    new_units = sum(q for _i, q in new_rows)
    print(
        f"current_database={name} days={days} "
        f"old_lines={len(old_rows)} old_units={old_units} old_summary={old_summary} "
        f"new_lines={len(new_rows)} new_units={new_units} new_summary={new_summary} "
        f"rows_equal={old_rows == new_rows} summary_equal={old_summary == new_summary}",
        flush=True,
    )
    if old_rows != new_rows or old_summary != new_summary:
        raise SystemExit("STOP: signal inputs differ")


if __name__ == "__main__":
    asyncio.run(main())
