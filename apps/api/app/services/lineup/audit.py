"""Persist line-up approval audit events."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lineup import LineupPlanItemEvent


async def record_lineup_approval_event(
    db: AsyncSession,
    *,
    lineup_item_id: int,
    old_status: str | None,
    new_status: str,
    notes: str | None,
    actor: str | None,
) -> None:
    db.add(
        LineupPlanItemEvent(
            lineup_item_id=lineup_item_id,
            event_type="approval_changed",
            old_approval_status=old_status,
            new_approval_status=new_status,
            notes=notes,
            actor=actor,
        )
    )
