"""Follow ``merged_into_*`` soft-redirects to the surviving dimension row.

Resolution callers (imports, aliases, code/name lookups) must return the survivor
id, never a merged loser. Provisional-reuse / picker callers exclude merged rows
instead of following.

Cycle-safe: a loop stops at the first repeated id and does not hang.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor

MAX_MERGE_HOPS = 32


def follow_merge_chain(
    start_id: int | None,
    parent: Mapping[int, int | None],
    *,
    max_hops: int = MAX_MERGE_HOPS,
) -> int | None:
    """Walk ``parent[id] = merged_into_id`` until a terminal (None) or cycle.

    Returns the last living id. ``None`` input stays ``None``. Missing ids stay as
    the last known id. A cycle returns the first repeated node (does not hang).
    """
    if start_id is None:
        return None
    cur = int(start_id)
    seen: set[int] = set()
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = parent.get(cur)
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


def build_redirect_map(pairs: Iterable[tuple[int, int | None]]) -> dict[int, int]:
    """Map every id to its merge-chain terminal (self if not merged)."""
    parent: dict[int, int | None] = {}
    for raw_id, merged_into in pairs:
        cid = int(raw_id)
        parent[cid] = int(merged_into) if merged_into is not None else None
    return {cid: int(follow_merge_chain(cid, parent) or cid) for cid in parent}


def collapse_ids(ids: Iterable[int], redirect: Mapping[int, int]) -> list[int]:
    """Unique terminal ids, first-seen order."""
    out: list[int] = []
    seen: set[int] = set()
    for raw in ids:
        tid = int(redirect.get(int(raw), int(raw)))
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def redirect_id(raw_id: int | None, redirect: Mapping[int, int]) -> int | None:
    if raw_id is None:
        return None
    cid = int(raw_id)
    return int(redirect.get(cid, cid))


def merged_into_customer_id(row: Any) -> int | None:
    """Read ``merged_into_customer_id``; missing attribute means not merged."""
    raw = getattr(row, "merged_into_customer_id", None)
    return int(raw) if raw is not None else None


def merged_into_distributor_id(row: Any) -> int | None:
    """Read ``merged_into_distributor_id``; missing attribute means not merged."""
    raw = getattr(row, "merged_into_distributor_id", None)
    return int(raw) if raw is not None else None


def is_merged_customer_row(row: Any) -> bool:
    if row is None:
        return False
    if merged_into_customer_id(row) is not None:
        return True
    return str(getattr(row, "customer_status", "") or "").strip().lower() == "merged"


def is_merged_distributor_row(row: Any) -> bool:
    if row is None:
        return False
    if merged_into_distributor_id(row) is not None:
        return True
    return str(getattr(row, "distributor_status", "") or "").strip().lower() == "merged"


def living_customer_clause():
    """SQLAlchemy filter: exclude merged losers from pickers / provisional reuse."""
    return and_(
        DimCustomer.merged_into_customer_id.is_(None),
        DimCustomer.customer_status != "merged",
    )


def living_distributor_clause():
    return and_(
        DimDistributor.merged_into_distributor_id.is_(None),
        DimDistributor.distributor_status != "merged",
    )


def load_customer_redirect_map(db: Session) -> dict[int, int]:
    rows = db.execute(select(DimCustomer.id, DimCustomer.merged_into_customer_id)).all()
    return build_redirect_map((int(r[0]), r[1]) for r in rows)


def load_distributor_redirect_map(db: Session) -> dict[int, int]:
    rows = db.execute(select(DimDistributor.id, DimDistributor.merged_into_distributor_id)).all()
    return build_redirect_map((int(r[0]), r[1]) for r in rows)


async def load_customer_redirect_map_async(db: AsyncSession) -> dict[int, int]:
    rows = (await db.execute(select(DimCustomer.id, DimCustomer.merged_into_customer_id))).all()
    return build_redirect_map((int(r[0]), r[1]) for r in rows)


async def load_distributor_redirect_map_async(db: AsyncSession) -> dict[int, int]:
    rows = (
        await db.execute(select(DimDistributor.id, DimDistributor.merged_into_distributor_id))
    ).all()
    return build_redirect_map((int(r[0]), r[1]) for r in rows)


def follow_customer_merge_redirect_sync(
    db: Session,
    customer_id: int | None,
    *,
    max_hops: int = MAX_MERGE_HOPS,
) -> int | None:
    """DB walk of ``dim_customer.merged_into_customer_id``. Cycle-safe."""
    if customer_id is None:
        return None
    seen: set[int] = set()
    cur = int(customer_id)
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = db.scalar(select(DimCustomer.merged_into_customer_id).where(DimCustomer.id == cur))
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


async def follow_customer_merge_redirect_async(
    db: AsyncSession,
    customer_id: int | None,
    *,
    max_hops: int = MAX_MERGE_HOPS,
) -> int | None:
    if customer_id is None:
        return None
    seen: set[int] = set()
    cur = int(customer_id)
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = await db.scalar(select(DimCustomer.merged_into_customer_id).where(DimCustomer.id == cur))
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


def follow_distributor_merge_redirect_sync(
    db: Session,
    distributor_id: int | None,
    *,
    max_hops: int = MAX_MERGE_HOPS,
) -> int | None:
    if distributor_id is None:
        return None
    seen: set[int] = set()
    cur = int(distributor_id)
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = db.scalar(
            select(DimDistributor.merged_into_distributor_id).where(DimDistributor.id == cur)
        )
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


async def follow_distributor_merge_redirect_async(
    db: AsyncSession,
    distributor_id: int | None,
    *,
    max_hops: int = MAX_MERGE_HOPS,
) -> int | None:
    if distributor_id is None:
        return None
    seen: set[int] = set()
    cur = int(distributor_id)
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = await db.scalar(
            select(DimDistributor.merged_into_distributor_id).where(DimDistributor.id == cur)
        )
        if nxt is None:
            return cur
        cur = int(nxt)
    return cur


def index_by_code_and_name(
    rows: Sequence[Any],
    *,
    merged_into_attr: str,
) -> dict[str, Any]:
    """Map lowercased code/name → surviving row (loser keys point at the winner object)."""
    by_id = {int(r.id): r for r in rows}
    if merged_into_attr == "merged_into_distributor_id":
        parent = {int(r.id): merged_into_distributor_id(r) for r in rows}
    else:
        parent = {int(r.id): merged_into_customer_id(r) for r in rows}
    redirect = build_redirect_map(parent.items())
    out: dict[str, Any] = {}
    for r in rows:
        survivor = by_id.get(redirect[int(r.id)], r)
        name = str(getattr(r, "name", "") or "").lower().strip()
        code = str(getattr(r, "code", "") or "").lower().strip()
        if name:
            out[name] = survivor
        if code:
            out[code] = survivor
    return out
