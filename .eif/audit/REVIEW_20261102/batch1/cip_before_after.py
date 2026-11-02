"""READ-ONLY figures on cip for the GOV-008 B1 fix: shipped quantity (v2 model), cover-distribution open inbound,
movement-lens shipped week, weekly-flow anchor and CPOR intake weighting, with the shared live-line rule OFF ("before",
the old behaviour: closed facts count) and ON ("after").

Run (from the repo root, no cd):
    apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/batch1/cip_before_after.py before
    apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/batch1/cip_before_after.py after

Safety: every transaction is set READ ONLY (``SET SESSION CHARACTERISTICS`` + ``SET TRANSACTION READ ONLY``) before any
read, and the script proves it by attempting a write that must be refused (ReadOnlySqlTransaction). No commit is issued.
"before" is simulated by emptying the rule's closed-state list before any reader module is imported, so every query that
embeds the rule (including the raw-SQL twin text built at import time) behaves as it did before the fix.
"""
from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

MODE = sys.argv[1] if len(sys.argv) > 1 else "after"
assert MODE in ("before", "after")

import app.services.shipment_live_line as live  # noqa: E402

if MODE == "before":
    live._CLOSED_SORTED = ("__rule_off__",)

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.facts import FactInboundShipment  # noqa: E402
from app.query.model.execute import run_v2  # noqa: E402
from app.query.model.graph import V2Request  # noqa: E402
from app.services.shipment_strict_pair import twin_remainder  # noqa: E402

TENANT = "default"


def num(x):
    if isinstance(x, Decimal):
        return float(x)
    return x


async def main() -> dict:
    out: dict = {"mode": MODE, "rule_closed_states": list(live._CLOSED_SORTED)}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out["database"] = (await db.execute(text("select current_database()"))).scalar_one()
        assert out["database"] == "cip", out["database"]
        try:
            async with db.begin_nested():
                await db.execute(text("CREATE TEMP TABLE _ro_probe (i int)"))
            out["write_probe"] = "WRITE WAS ACCEPTED (abort)"
            raise SystemExit("the connection is not read-only; aborting")
        except DBAPIError as exc:
            out["write_probe"] = "refused: " + type(exc.orig).__name__ if exc.orig is not None else "refused"
        assert out["write_probe"].startswith("refused")
        out["default_transaction_read_only"] = (await db.execute(text("show default_transaction_read_only"))).scalar_one()
        out["transaction_read_only"] = (await db.execute(text("show transaction_read_only"))).scalar_one()

        # fact mix by state (context)
        rows = (
            await db.execute(
                select(FactInboundShipment.line_state, func.count(), func.coalesce(func.sum(FactInboundShipment.quantity), 0))
                .where(FactInboundShipment.tenant_id == TENANT)
                .group_by(FactInboundShipment.line_state)
                .order_by(FactInboundShipment.line_state)
            )
        ).all()
        out["facts_by_state"] = {r[0]: {"rows": r[1], "units": num(r[2])} for r in rows}

        # 1. v2 model: shipped quantity and lines (all time), and open measures (must not move)
        v = await run_v2(db, V2Request(measures=["shipments.quantity", "shipments.lines", "shipments.open_quantity", "shipments.open_lines"], breakdowns=[]), tenant_id=TENANT, skip_cache=True)
        out["v2_shipments_totals"] = {k: num(val) for k, val in v["totals"].items()}

        # 2. channel_ops
        from app.api.v1.endpoints.channel_ops import _cover_weekly_flow, _open_inbound_by_pair, channel_ops_movement_lens

        inbound = await _open_inbound_by_pair(db, TENANT)
        out["cover_distribution_open_inbound"] = {"pairs": len(inbound), "units": round(sum(inbound.values()), 4)}
        lens = await channel_ops_movement_lens(db=db, user={"tenant_id": TENANT}, weeks=13)
        out["movement_lens_shipped"] = {"week": lens["headlines"]["shipped_week"], "units": lens["headlines"]["shipped_units"]}
        flow = await _cover_weekly_flow(db, TENANT)
        out["weekly_flow"] = {"shipped_through": flow["shipped_through"], "shipped_units_13w": sum(p["shipped"] for p in flow["points"])}

        # 3. CPOR intake weighting (the _intake_wavg rows, all products and all dates): weight = counted quantity
        twin = twin_remainder(FactInboundShipment)
        res = (
            await db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(twin.counted_quantity), 0),
                    func.coalesce(func.sum(twin.counted_quantity * FactInboundShipment.unit_price), 0),
                )
                .select_from(FactInboundShipment)
                .outerjoin(twin.subquery, twin.onclause)
                .where(
                    FactInboundShipment.tenant_id == TENANT,
                    FactInboundShipment.purchase_order_id.is_not(None),
                    FactInboundShipment.unit_price.is_not(None),
                    FactInboundShipment.unit_price > 0,
                    FactInboundShipment.quantity.is_not(None),
                    FactInboundShipment.quantity > 0,
                    twin.kept,
                )
            )
        ).one()
        w = float(res[1] or 0)
        out["intake_weighting_all_products"] = {
            "rows": res[0], "weight_units": round(w, 4), "weighted_unit_price": round(float(res[2] or 0) / w, 6) if w else None,
        }
        per = (
            await db.execute(
                select(
                    FactInboundShipment.product_id,
                    func.coalesce(func.sum(twin.counted_quantity), 0),
                    func.coalesce(func.sum(twin.counted_quantity * FactInboundShipment.unit_price), 0),
                )
                .select_from(FactInboundShipment)
                .outerjoin(twin.subquery, twin.onclause)
                .where(
                    FactInboundShipment.tenant_id == TENANT,
                    FactInboundShipment.purchase_order_id.is_not(None),
                    FactInboundShipment.product_id.is_not(None),
                    FactInboundShipment.unit_price.is_not(None),
                    FactInboundShipment.unit_price > 0,
                    FactInboundShipment.quantity.is_not(None),
                    FactInboundShipment.quantity > 0,
                    twin.kept,
                )
                .group_by(FactInboundShipment.product_id)
            )
        ).all()
        out["intake_per_product"] = {str(p): {"weight": round(float(q or 0), 4), "avg": round(float(v_ or 0) / float(q), 6) if q else None} for p, q, v_ in per}
        await db.rollback()
    return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main()), indent=2, sort_keys=True))
