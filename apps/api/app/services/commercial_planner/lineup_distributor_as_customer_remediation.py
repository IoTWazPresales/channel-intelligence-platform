"""BACKLOG-125/126 — distributor-as-customer remediation (Warren-locked 2026-08-08).

Locks applied:
- Syntech = distributor 51; customer-column Syntech → OPEN_CHANNEL + dist 51
- Channel Syntech = OPEN_CHANNEL + Syntech (already correct)
- Compuspeed as customer = OPEN_CHANNEL (ship: dist 12 → OC majority; no Compuspeed-named ship customer)
- Superdist = distributor 50; alias ``superdisti`` → 50
- SMD = customer token, no ship customer evidence → leave free-picker (no invent)

Never auto-creates dims. Uses existing stamp + open_channel_absorb + distributor alias mint.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
)
from app.services.commercial_planner.lineup_customer_token_stamp import (
    apply_customer_token_stamp,
    revoke_customer_token_alias,
)
from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.open_channel_absorb import (
    confirm_absorb_into_open_channel,
    preview_absorb_into_open_channel,
)
from app.services.steward_audit import record_steward_audit

# Warren-locked loser provisional customers (distributor names parked as customers)
_ABSORB_LOSER_IDS = (4145, 1152)  # Syntech DISTRIBUTION; Compuspeed LTD
_SUPERDIST_ID = 50
_SUPERDISTI_TOKEN = "superdisti"


async def _revoke_aliases_to_customers(
    db: AsyncSession,
    user: dict | None,
    *,
    customer_ids: list[int],
    reason: str,
) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(CustomerSourceTokenAlias).where(
                    CustomerSourceTokenAlias.customer_id.in_([int(x) for x in customer_ids]),
                    CustomerSourceTokenAlias.status == "approved",
                )
            )
        ).scalars().all()
    )
    out: list[dict[str, Any]] = []
    for alias in rows:
        rev = await revoke_customer_token_alias(
            db,
            user,
            alias_id=int(alias.id),
            reason=reason,
            commit=False,
        )
        out.append(rev)
    return out


async def ensure_distributor_alias(
    db: AsyncSession,
    user: dict | None,
    *,
    distributor_id: int,
    raw_token: str,
    reason: str,
) -> dict[str, Any]:
    nt = _norm_key(raw_token)
    if not nt:
        raise ValueError("empty distributor alias token")
    dist = await db.get(DimDistributor, int(distributor_id))
    if dist is None:
        raise ValueError(f"distributor {distributor_id} missing")

    existing = (
        await db.execute(
            select(DistributorSourceTokenAlias).where(
                DistributorSourceTokenAlias.normalized_token == nt,
                DistributorSourceTokenAlias.status == "approved",
            )
        )
    ).scalars().first()
    if existing is not None:
        if int(existing.distributor_id) != int(distributor_id):
            raise ValueError(
                f"approved distributor alias {nt!r} already maps to "
                f"{existing.distributor_id}, not {distributor_id}"
            )
        return {
            "alias_id": int(existing.id),
            "created": False,
            "normalized_token": nt,
            "distributor_id": int(distributor_id),
        }

    alias = DistributorSourceTokenAlias(
        distributor_id=int(distributor_id),
        source_definition_id=None,
        raw_token=str(raw_token)[:512],
        normalized_token=nt[:512],
        status="approved",
        notes=f"backlog-126:{reason}"[:1024],
        created_from_import_job_id=None,
    )
    db.add(alias)
    await db.flush()
    await record_steward_audit(
        db,
        user,
        action="distributor_source_token_alias_mint",
        importer="commercial_planner",
        entity_type="distributor_token",
        entity_token=nt,
        target_dim="dim_distributor",
        target_id=int(distributor_id),
        payload={"reason": reason, "alias_id": int(alias.id), "raw_token": raw_token},
        commit=False,
    )
    return {
        "alias_id": int(alias.id),
        "created": True,
        "normalized_token": nt,
        "distributor_id": int(distributor_id),
    }


async def preview_backlog_125_126(db: AsyncSession) -> dict[str, Any]:
    oc_id = await get_open_channel_customer_id(db)
    aliases_4145 = list(
        (
            await db.execute(
                select(CustomerSourceTokenAlias).where(
                    CustomerSourceTokenAlias.customer_id.in_(list(_ABSORB_LOSER_IDS)),
                    CustomerSourceTokenAlias.status == "approved",
                )
            )
        ).scalars().all()
    )
    dist_alias = (
        await db.execute(
            select(DistributorSourceTokenAlias).where(
                DistributorSourceTokenAlias.normalized_token == _norm_key(_SUPERDISTI_TOKEN),
                DistributorSourceTokenAlias.status == "approved",
            )
        )
    ).scalars().first()
    return {
        "open_channel_customer_id": oc_id,
        "absorb_loser_ids": list(_ABSORB_LOSER_IDS),
        "aliases_to_revoke": [
            {
                "alias_id": int(a.id),
                "customer_id": int(a.customer_id),
                "normalized_token": a.normalized_token,
            }
            for a in aliases_4145
        ],
        "superdisti_alias": (
            {
                "alias_id": int(dist_alias.id),
                "distributor_id": int(dist_alias.distributor_id),
            }
            if dist_alias
            else None
        ),
        "smd_policy": "customer_token_leave_free_picker_no_ship_customer_evidence",
        "stamp_tokens": ["syntech", "sadc - superdisti"],
    }


async def apply_backlog_125_126_async_phase(
    db: AsyncSession,
    user: dict | None,
    *,
    reason: str = "BACKLOG-125/126 Warren lock 2026-08-08",
    commit: bool = True,
) -> dict[str, Any]:
    """Revoke bad customer aliases, mint superdisti→50, restamp Syntech + sadc - superdisti."""
    oc_id = await get_open_channel_customer_id(db)
    if oc_id is None:
        raise ValueError("OPEN_CHANNEL missing")

    revoked = await _revoke_aliases_to_customers(
        db,
        user,
        customer_ids=list(_ABSORB_LOSER_IDS),
        reason=reason,
    )
    dist_alias = await ensure_distributor_alias(
        db,
        user,
        distributor_id=_SUPERDIST_ID,
        raw_token=_SUPERDISTI_TOKEN,
        reason=reason,
    )

    syntech = await apply_customer_token_stamp(
        db,
        user,
        norm_token="syntech",
        target_customer_id=int(oc_id),
        reason=reason,
        commit=False,
    )
    superdisti = await apply_customer_token_stamp(
        db,
        user,
        norm_token="sadc - superdisti",
        target_customer_id=int(oc_id),
        reason=reason,
        commit=False,
    )

    if commit:
        await db.commit()
    else:
        await db.flush()

    return {
        "open_channel_customer_id": int(oc_id),
        "revoked_aliases": revoked,
        "distributor_alias": dist_alias,
        "syntech_stamp": {
            "stamped_count": syntech.get("stamped_count"),
            "alias_id": syntech.get("alias_id"),
            "line_distributor_id": syntech.get("line_distributor_id"),
            "distributor_token_match": syntech.get("distributor_token_match"),
        },
        "superdisti_stamp": {
            "stamped_count": superdisti.get("stamped_count"),
            "alias_id": superdisti.get("alias_id"),
            "line_distributor_id": superdisti.get("line_distributor_id"),
            "distributor_token_match": superdisti.get("distributor_token_match"),
        },
        "smd": "left_unresolved_customer_free_picker",
    }


def apply_backlog_125_absorb_sync(
    db: Session,
    *,
    reason: str = "BACKLOG-125 absorb distributor-named customers into OPEN_CHANNEL",
    performed_by: str = "backlog-125",
) -> dict[str, Any]:
    preview = preview_absorb_into_open_channel(
        db,
        loser_ids=list(_ABSORB_LOSER_IDS),
        audit_note=reason,
    )
    if not preview.get("pending_loser_ids") and preview.get("already_redirected_ids"):
        return {**preview, "applied": False, "note": "already absorbed"}
    return {
        **confirm_absorb_into_open_channel(
            db,
            loser_ids=list(_ABSORB_LOSER_IDS),
            audit_note=reason,
            performed_by=performed_by,
        ),
        "applied": True,
    }
