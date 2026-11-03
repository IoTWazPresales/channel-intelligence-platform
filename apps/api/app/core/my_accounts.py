"""My accounts is a clearable filter (D-0138, Warren 3 Nov 2026).

An assignment is a row, not a permission. The account predicate is added to a
query only while this request's filter is on. Clear is a sign-in flag the
client sends on ``X-Cip-My-Accounts: off``. It is not stored on the user and
not a row-security policy. Product-line scope is a separate gate and stays on
either way. Import steward and import apply do not call this.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy import bindparam
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

# None: filter off (no predicate). A non-empty set: filter on, those customers only.
request_my_account_ids: ContextVar[frozenset[int] | None] = ContextVar(
    "cip_my_account_ids", default=None
)

ACCOUNT_PREDICATE_BIND = "my_account_customer_ids"
CLEAR_HEADER = "x-cip-my-accounts"


def header_clears_my_accounts(headers: Any) -> bool:
    raw = headers.get(CLEAR_HEADER) if headers is not None else None
    return str(raw or "").strip().lower() == "off"


def account_predicate(column: Any):
    """The one account condition. None when the filter is off, including after Clear
    and when the signed-in user has no assigned accounts.
    """
    ids = request_my_account_ids.get()
    if not ids:
        return None
    return column.in_(bindparam(ACCOUNT_PREDICATE_BIND, value=sorted(ids), expanding=True))


def apply_account_predicate(stmt: Any, column: Any):
    pred = account_predicate(column)
    if pred is None:
        return stmt
    return stmt.where(pred)


def accounts_to_store(scope: str, requested_ids: list[int], existing_ids: set[int]) -> list[int]:
    """Ids to write. ``all`` stores nothing (filter starts off). Never invents a customer."""
    if scope == "all":
        return []
    if scope != "selected":
        raise ValueError("Account scope is all or selected.")
    ordered: list[int] = []
    seen: set[int] = set()
    missing: list[int] = []
    for raw in requested_ids:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        if cid not in existing_ids:
            missing.append(cid)
            continue
        ordered.append(cid)
    if missing:
        raise ValueError("A customer account must already exist in this tenant.")
    if not ordered:
        raise ValueError("Choose all accounts in this tenant, or at least one account.")
    return ordered


async def load_assigned_customer_ids(db: AsyncSession, *, tenant_id: str, user_id: int) -> list[int]:
    """Assigned customer ids. An absent table (migration not applied) is an empty list."""
    from sqlalchemy import select

    from app.models.user_customer_account import UserCustomerAccount

    try:
        async with db.begin_nested():
            rows = (
                await db.execute(
                    select(UserCustomerAccount.customer_id)
                    .where(
                        UserCustomerAccount.tenant_id == tenant_id,
                        UserCustomerAccount.user_id == user_id,
                    )
                    .order_by(UserCustomerAccount.customer_id.asc())
                )
            ).scalars().all()
    except ProgrammingError:
        return []
    return [int(cid) for cid in rows]


async def bind_my_accounts(db: AsyncSession, user: dict | None, headers: Any) -> Token:
    """Turn the filter on for this request when the user has accounts and has not cleared it."""
    if user is None or header_clears_my_accounts(headers):
        return request_my_account_ids.set(None)
    uid = str(user.get("id") or "")
    if not uid.isdigit():
        return request_my_account_ids.set(None)
    tenant_id = str(user.get("tenant_id") or "default").strip() or "default"
    ids = await load_assigned_customer_ids(db, tenant_id=tenant_id, user_id=int(uid))
    return request_my_account_ids.set(frozenset(ids) if ids else None)


def reset_my_accounts(token: Token) -> None:
    request_my_account_ids.reset(token)


@asynccontextmanager
async def my_accounts_scope(db: AsyncSession, user: dict | None, headers: Any) -> AsyncIterator[None]:
    """Bind the filter for one request, then put the context back."""
    token = await bind_my_accounts(db, user, headers)
    try:
        yield
    finally:
        reset_my_accounts(token)
