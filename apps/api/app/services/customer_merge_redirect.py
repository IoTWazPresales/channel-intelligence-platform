"""Follow dim_customer.merged_into_customer_id to the merge-chain terminal."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer

_MAX_MERGE_REDIRECT_HOPS = 10


def follow_customer_merge_redirect(
    db: Session,
    customer_id: int,
    *,
    max_hops: int = _MAX_MERGE_REDIRECT_HOPS,
) -> tuple[int, bool]:
    """Return ``(terminal_customer_id, followed)`` chasing soft-redirects."""
    cur = int(customer_id)
    seen: set[int] = set()
    followed = False
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            break
        seen.add(cur)
        row = db.get(DimCustomer, cur)
        if row is None or row.merged_into_customer_id is None:
            break
        nxt = int(row.merged_into_customer_id)
        if nxt == cur:
            break
        cur = nxt
        followed = True
    return cur, followed


def terminal_customer_id_from_map(
    merged_into_by_id: dict[int, int | None],
    customer_id: int,
    *,
    max_hops: int = _MAX_MERGE_REDIRECT_HOPS,
) -> int:
    """In-memory terminal chase using ``id -> merged_into_customer_id`` map."""
    cur = int(customer_id)
    seen: set[int] = set()
    for _ in range(max(1, int(max_hops))):
        if cur in seen:
            break
        seen.add(cur)
        nxt = merged_into_by_id.get(cur)
        if nxt is None:
            break
        nxt_i = int(nxt)
        if nxt_i == cur:
            break
        cur = nxt_i
    return cur
