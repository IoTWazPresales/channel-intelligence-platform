"""Assign a distributor to a lineup case's lines (Unit A).

Covers the gap that token-keyed entity resolution does not: lineup lines that carry **no**
distributor token (the file never named a distributor) cannot be resolved through
``apply_entity_resolutions``. This is steward-initiated, set-based, and idempotent.

Governance:
  * The target is always a real ``dim_distributor`` — either an existing id (e.g. one suggested
    from shipment-evidence corroboration, which is itself a PO FK) or one created here through an
    explicit, confirmed create (code + name). No auto-create on parse; creation is steward action.
  * Only ``distributor_id`` is written on the lines. Cost / DAP / SKU assumptions are untouched.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimDistributor
from app.services.commercial_planner.lineup_entity_resolution import (
    RESOLUTION_ALLOWED_CASE_STATUSES,
    append_manual_resolution_tag,
    refresh_diagnostics_after_entity_update,
)


class CaseNotFoundError(Exception):
    pass


class CaseStatusNotResolvableError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


class DistributorNotFoundError(Exception):
    pass


class DistributorCodeExistsError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def assign_case_distributor(
    db: AsyncSession,
    case_id: int,
    *,
    distributor_id: int | None = None,
    new_code: str | None = None,
    new_name: str | None = None,
    only_unassigned: bool = True,
) -> dict[str, Any]:
    """Set ``distributor_id`` on a case's lines.

    Provide exactly one of: an existing ``distributor_id``, or ``new_code`` + ``new_name`` to create
    a new ``dim_distributor`` (steward-confirmed creation). ``only_unassigned`` (default) writes only
    lines whose ``distributor_id`` is currently NULL; pass False to overwrite all lines.
    """
    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise CaseNotFoundError(str(case_id))
    if case.commercial_status not in RESOLUTION_ALLOWED_CASE_STATUSES:
        raise CaseStatusNotResolvableError(case.commercial_status)

    created = False
    if distributor_id is not None:
        dim = await db.get(DimDistributor, distributor_id)
        if dim is None:
            raise DistributorNotFoundError(str(distributor_id))
    else:
        code = (new_code or "").strip()[:32]
        name = (new_name or "").strip()[:256]
        if not code or not name:
            raise ValueError("new_code and new_name are required to create a distributor.")
        exists = await db.scalar(
            select(func.count()).select_from(DimDistributor).where(DimDistributor.code == code)
        )
        if exists:
            raise DistributorCodeExistsError(code)
        dim = DimDistributor(code=code, name=name)
        db.add(dim)
        await db.flush()
        distributor_id = int(dim.id)
        created = True

    lines = (
        (await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)))
        .scalars()
        .all()
    )
    updated = 0
    for ln in lines:
        if only_unassigned and ln.distributor_id is not None:
            continue
        if ln.distributor_id == distributor_id:
            continue
        ln.distributor_id = distributor_id
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_distributor_assigned")
        updated += 1

    await db.commit()
    return {
        "case_id": case_id,
        "distributor_id": int(distributor_id),
        "distributor_created": created,
        "updated_lines": updated,
    }
