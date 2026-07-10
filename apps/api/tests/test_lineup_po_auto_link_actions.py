"""Unit 4 — PO auto-link dismiss / apply actions."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.services.commercial_planner.lineup_po_auto_link_actions import (
    ProposalNotFoundError,
    apply_auto_link_proposals,
    dismiss_auto_link_proposal,
    restore_auto_link_proposal,
)


def _dismiss_table_exists(connection) -> bool:
    return inspect(connection).has_table("commercial_lineup_po_auto_link_dismiss")


@pytest.mark.anyio
async def test_dismiss_and_restore_roundtrip():
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupCase
    from app.models.purchase_order import PurchaseOrder

    async with AsyncSessionLocal() as db:
        conn = await db.connection()
        if not await conn.run_sync(lambda c: _dismiss_table_exists(c)):
            pytest.skip("migration 0059 not applied")

        case_id = (await db.execute(select(CommercialLineupCase.id).limit(1))).scalar_one_or_none()
        po_id = (await db.execute(select(PurchaseOrder.id).limit(1))).scalar_one_or_none()
        if case_id is None or po_id is None:
            pytest.skip("no lineup case or purchase order on dev DB")

        key = f"{int(case_id)}:0:0:{int(po_id)}"
        await dismiss_auto_link_proposal(
            db,
            proposal_key=key,
            case_id=int(case_id),
            purchase_order_id=int(po_id),
            reason_code="test wrong match",
        )
        with pytest.raises(ProposalNotFoundError):
            await restore_auto_link_proposal(db, proposal_key="nonexistent-key-xyz")

        out = await restore_auto_link_proposal(db, proposal_key=key)
        assert out["restored"] is True


@pytest.mark.anyio
async def test_apply_requires_items():
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="At least one"):
            await apply_auto_link_proposals(db, items=[])
