"""BACKLOG-061-U-B3a — collision-safe distributor code mint allocator.

Never auto-creates dim_distributor. Mint bumps are silent (not FLAG events).
Mirrors customer_code_mint.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimDistributor
from app.models.distributor_code_mint_setting import DistributorCodeMintSetting
from app.services.distributor_promote import DistributorPromoteError

DEFAULT_TENANT_ID = "default"
_MAX_BUMP_ATTEMPTS = 10_000


def render_distributor_code(*, prefix: str, separator: str, seq: int, pad_width: int) -> str:
    return f"{prefix}{separator}{str(int(seq)).zfill(int(pad_width))}"


async def _code_taken(
    db: AsyncSession,
    code: str,
    *,
    reserved: set[str] | None = None,
) -> bool:
    key = code.strip().lower()
    if not key:
        return True
    if reserved and key in reserved:
        return True
    owner = (
        await db.execute(select(DimDistributor.id).where(func.lower(DimDistributor.code) == key))
    ).scalar_one_or_none()
    return owner is not None


async def _load_settings(
    db: AsyncSession,
    *,
    tenant_id: str,
    for_update: bool,
) -> DistributorCodeMintSetting:
    stmt = select(DistributorCodeMintSetting).where(
        DistributorCodeMintSetting.tenant_id == tenant_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise DistributorPromoteError(
            f"Mint settings not found for tenant_id={tenant_id!r}",
            status_code=422,
            code="mint_settings_missing",
        )
    if (row.segment_mode or "").strip().lower() != "none":
        raise DistributorPromoteError(
            f"segment_mode={row.segment_mode!r} is not implemented (Candidate A requires none)",
            status_code=422,
            code="mint_segment_mode_unsupported",
        )
    return row


async def mint_next_distributor_code(
    db: AsyncSession,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    dry_run: bool = False,
    reserved: set[str] | None = None,
    start_seq: int | None = None,
) -> tuple[str, int]:
    """Allocate one code.

    Returns ``(code, seq_used)``.
    dry_run: no FOR UPDATE, does not persist next_seq (caller tracks reserved + start_seq).
    confirm: FOR UPDATE, persists next_seq = used + 1.
    """
    settings = await _load_settings(db, tenant_id=tenant_id, for_update=not dry_run)
    seq = int(start_seq) if start_seq is not None else int(settings.next_seq)
    if seq < 1:
        seq = 1

    for _ in range(_MAX_BUMP_ATTEMPTS):
        code = render_distributor_code(
            prefix=settings.prefix,
            separator=settings.separator,
            seq=seq,
            pad_width=settings.pad_width,
        )
        if not await _code_taken(db, code, reserved=reserved):
            if not dry_run:
                settings.next_seq = seq + 1
                settings.updated_at = datetime.now(timezone.utc)
                await db.flush()
            return code, seq
        seq += 1

    raise DistributorPromoteError(
        "Unable to allocate a free distributor code; retry",
        status_code=503,
        code="mint_exhausted",
    )


async def mint_distributor_codes(
    db: AsyncSession,
    *,
    count: int,
    tenant_id: str = DEFAULT_TENANT_ID,
    dry_run: bool = False,
) -> list[str]:
    """Allocate ``count`` codes in order. dry_run does not advance persisted next_seq."""
    if count < 0:
        raise DistributorPromoteError("count must be >= 0", status_code=422, code="mint_bad_count")
    if count == 0:
        return []

    reserved: set[str] = set()
    codes: list[str] = []
    start_seq: int | None = None

    if dry_run:
        settings = await _load_settings(db, tenant_id=tenant_id, for_update=False)
        start_seq = int(settings.next_seq)

    for _ in range(count):
        code, used = await mint_next_distributor_code(
            db,
            tenant_id=tenant_id,
            dry_run=dry_run,
            reserved=reserved,
            start_seq=start_seq,
        )
        reserved.add(code.lower())
        codes.append(code)
        if dry_run:
            start_seq = used + 1

    return codes
