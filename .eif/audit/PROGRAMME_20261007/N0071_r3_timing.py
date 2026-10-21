"""N-0071 round 3: time the channel ops statements, D-0057 form vs D-0065 form (read-only, cip).

SET TRANSACTION READ ONLY, prints current_database() first, rolls back. Three runs each,
alternating, so load drift hits both forms alike. Also times the whole movement lens and
latest_woc_observations (the lens' other cost) once each.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services import shipment_strict_pair as ssp

OUT = Path(__file__).with_name("N0071_r3_timing_out.json")


def _url() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    raise SystemExit("unexpected url scheme")


def _movement(in_date, monday, form):
    where = [F.tenant_id == "default", in_date.is_not(None), in_date >= monday, in_date < monday + timedelta(days=7)]
    if form == "d0057":
        return select(func.coalesce(func.sum(F.quantity), 0)).where(*where, ssp.exclude_open_when_shipped_twin(F))
    t = ssp.twin_remainder(F)
    return select(func.coalesce(func.sum(t.counted_quantity), 0)).select_from(F).outerjoin(t.subquery, t.onclause).where(*where, t.kept)


def _cover(form):
    where = [F.tenant_id == "default", F.pod_date.is_(None), F.distributor_id.is_not(None), F.product_id.is_not(None)]
    if form == "d0057":
        return (
            select(F.distributor_id, F.product_id, func.coalesce(func.sum(F.quantity), 0))
            .where(*where, ssp.exclude_open_when_shipped_twin(F))
            .group_by(F.distributor_id, F.product_id)
        )
    t = ssp.twin_remainder(F)
    return (
        select(F.distributor_id, F.product_id, func.coalesce(func.sum(t.counted_quantity), 0))
        .select_from(F)
        .outerjoin(t.subquery, t.onclause)
        .where(*where, t.kept)
        .group_by(F.distributor_id, F.product_id)
    )


async def main() -> None:
    from app.api.v1.endpoints import channel_ops
    latest_woc_observations = channel_ops.latest_woc_observations

    engine = create_async_engine(_url())
    out: dict = {}
    async with AsyncSession(engine) as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["current_database"] = (await db.execute(text("SELECT current_database()"))).scalar()
        print("current_database:", out["current_database"], flush=True)
        out["transaction_read_only"] = (await db.execute(text("SHOW transaction_read_only"))).scalar()
        in_date = func.coalesce(F.ship_confirm_date, F.pod_date)
        in_max = (await db.execute(select(func.max(in_date)).where(F.tenant_id == "default"))).scalar()
        monday = in_max - timedelta(days=in_max.weekday())
        for name, build in (("movement", lambda f: _movement(in_date, monday, f)), ("cover_inbound_open", _cover)):
            for form in ("d0057", "d0065", "d0057", "d0065", "d0057", "d0065"):
                t0 = time.perf_counter()
                res = (await db.execute(build(form))).all()
                dt = round(time.perf_counter() - t0, 2)
                total = sum(float(r[-1] or 0) for r in res)
                out.setdefault(f"{name}_{form}_s", []).append(dt)
                out[f"{name}_{form}_total"] = total
        t0 = time.perf_counter()
        await latest_woc_observations(db, tenant_id="default")
        out["latest_woc_observations_s"] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()
        await channel_ops.channel_ops_movement_lens(db=db, user=None, weeks=13)
        out["movement_lens_s"] = round(time.perf_counter() - t0, 2)
        await db.rollback()
    await engine.dispose()
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
