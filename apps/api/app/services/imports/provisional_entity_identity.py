"""Canonical identity for provisional distributor/customer create-path deduplication.

Provisional rows are minted with ``TMP-DIST-%`` / ``TMP-CUST-%`` codes. Before creating a new
provisional, stewards and bulk apply paths look up an existing unverified provisional with the
same canonical display-name identity and reuse it (new alias only).

The same ``canonical_provisional_entity_name_key`` is used by governed merge/cleanup (Unit 2b).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from app.models.dimensions import DimCustomer, DimDistributor

_PUNCT_COLLAPSE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_COLLAPSE = re.compile(r"\s+")

# Exact normalized keys that must never become provisional customers.
CUSTOMER_PROVISIONAL_NON_ENTITY_EXACT: frozenset[str] = frozenset(
    {
        "n/a",
        "na",
        "tbd",
        "unknown",
        "misc",
        "blank",
        "open channel",
        "open_channel",
        "cash sale",
        "internal",
        "sample",
        "retail",
        "accessory",
        "accy",
    }
)

# Substrings in canonical display/raw text → not a real customer entity.
CUSTOMER_PROVISIONAL_NON_ENTITY_SUBSTRINGS: tuple[str, ...] = (
    "employee terms",
    "employee term",
    " staff",
    "staff purchase",
    "internal note",
    "not a customer",
    "house account",
    "write off",
    "writeoff",
)


def canonical_provisional_entity_name_key(name: str | None) -> str:
    """Case-, whitespace-, and punctuation-normalized key for provisional entity grouping."""
    if name is None:
        return ""
    t = str(name).strip().lower()
    t = _WS_COLLAPSE.sub(" ", t)
    t = _PUNCT_COLLAPSE.sub(" ", t)
    return _WS_COLLAPSE.sub(" ", t).strip()


def is_non_entity_customer_provisional_token(
    *,
    raw_token: str | None = None,
    display_name: str | None = None,
) -> bool:
    """True when text looks like policy/note noise, not a dealer/customer name."""
    for text in (raw_token, display_name):
        key = canonical_provisional_entity_name_key(text)
        if not key:
            continue
        if key in CUSTOMER_PROVISIONAL_NON_ENTITY_EXACT:
            return True
        for sub in CUSTOMER_PROVISIONAL_NON_ENTITY_SUBSTRINGS:
            if sub in key:
                return True
    return False


def _pick_earliest_provisional_distributor(rows: list[DimDistributor]) -> DimDistributor | None:
    if not rows:
        return None
    rows.sort(key=lambda d: int(d.id))
    return rows[0]


def _pick_earliest_provisional_customer(rows: list[DimCustomer]) -> DimCustomer | None:
    if not rows:
        return None
    rows.sort(key=lambda c: int(c.id))
    return rows[0]


def find_existing_provisional_distributor_by_canonical_name(
    session: Session,
    display_name: str | None,
) -> DimDistributor | None:
    """Return earliest ``TMP-DIST-%`` row matching canonical display name, else None."""
    from app.models.dimensions import DimDistributor

    key = canonical_provisional_entity_name_key(display_name)
    if not key:
        return None
    rows = list(session.scalars(select(DimDistributor).where(DimDistributor.code.like("TMP-DIST-%"))).all())
    matches = [d for d in rows if canonical_provisional_entity_name_key(d.name) == key]
    return _pick_earliest_provisional_distributor(matches)


async def find_existing_provisional_distributor_by_canonical_name_async(
    session: AsyncSession,
    display_name: str | None,
) -> DimDistributor | None:
    from app.models.dimensions import DimDistributor

    key = canonical_provisional_entity_name_key(display_name)
    if not key:
        return None
    result = await session.scalars(select(DimDistributor).where(DimDistributor.code.like("TMP-DIST-%")))
    rows = list(result.all())
    matches = [d for d in rows if canonical_provisional_entity_name_key(d.name) == key]
    return _pick_earliest_provisional_distributor(matches)


def find_existing_provisional_customer_by_canonical_name(
    session: Session,
    display_name: str | None,
) -> DimCustomer | None:
    """Return earliest unverified ``TMP-CUST-%`` row matching canonical display name, else None."""
    from app.models.dimensions import DimCustomer

    key = canonical_provisional_entity_name_key(display_name)
    if not key:
        return None
    rows = list(
        session.scalars(
            select(DimCustomer).where(
                DimCustomer.code.like("TMP-CUST-%"),
                DimCustomer.customer_status == "unverified",
            )
        ).all()
    )
    matches = [c for c in rows if canonical_provisional_entity_name_key(c.name) == key]
    return _pick_earliest_provisional_customer(matches)


async def find_existing_provisional_customer_by_canonical_name_async(
    session: AsyncSession,
    display_name: str | None,
) -> DimCustomer | None:
    from app.models.dimensions import DimCustomer

    key = canonical_provisional_entity_name_key(display_name)
    if not key:
        return None
    result = await session.scalars(
        select(DimCustomer).where(
            DimCustomer.code.like("TMP-CUST-%"),
            DimCustomer.customer_status == "unverified",
        )
    )
    rows = list(result.all())
    matches = [c for c in rows if canonical_provisional_entity_name_key(c.name) == key]
    return _pick_earliest_provisional_customer(matches)
