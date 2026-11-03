"""Replace a user's customer-account rows. Does not create a master."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.my_accounts import accounts_to_store
from app.models.dimensions import DimCustomer
from app.models.user_customer_account import UserCustomerAccount


class AccountAssignmentError(ValueError):
    """The requested accounts cannot be stored."""


async def replace_user_accounts(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: int,
    scope: str,
    customer_ids: list[int],
) -> list[int]:
    requested = [int(cid) for cid in customer_ids]
    existing: set[int] = set()
    if scope == "selected" and requested:
        found = (
            await db.execute(
                select(DimCustomer.id).where(
                    DimCustomer.tenant_id == tenant_id,
                    DimCustomer.id.in_(requested),
                )
            )
        ).scalars().all()
        existing = {int(cid) for cid in found}
    try:
        chosen = accounts_to_store(scope, requested, existing)
    except ValueError as exc:
        raise AccountAssignmentError(str(exc)) from exc
    try:
        async with db.begin_nested():
            await db.execute(
                delete(UserCustomerAccount).where(
                    UserCustomerAccount.tenant_id == tenant_id,
                    UserCustomerAccount.user_id == user_id,
                )
            )
            for cid in chosen:
                db.add(
                    UserCustomerAccount(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        customer_id=cid,
                    )
                )
            await db.flush()
    except ProgrammingError as exc:
        if not chosen:
            return []
        raise AccountAssignmentError(
            "Account assignments are not on this database yet."
        ) from exc
    return chosen
