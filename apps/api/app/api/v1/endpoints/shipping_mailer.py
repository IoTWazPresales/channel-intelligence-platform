"""Admin API for the shipping-digest SMTP recipient list."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.services.shipping_digest.recipients_store import (
    RecipientValidationError,
    add_recipient,
    delete_recipient,
    list_recipients,
    patch_recipient,
)

router = APIRouter()


class RecipientCreate(BaseModel):
    address: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)


class RecipientPatch(BaseModel):
    enabled: bool | None = None
    display_name: str | None = Field(default=None, max_length=200)


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    address: str
    display_name: str | None
    enabled: bool
    added_by: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RecipientListOut(BaseModel):
    items: list[RecipientOut]


def _actor(admin: dict) -> str:
    email = str(admin.get("email") or "").strip()
    if email:
        return email
    display = str(admin.get("display_name") or "").strip()
    if display:
        return display
    return str(admin.get("id") or "admin")


def _out(row: dict[str, Any]) -> RecipientOut:
    return RecipientOut.model_validate(row)


@router.get("/recipients", response_model=RecipientListOut)
async def get_shipping_mailer_recipients(
    admin: dict = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> RecipientListOut:
    tenant_id = tenant_id_from_user(admin)
    items = await list_recipients(db, tenant_id)
    await db.commit()
    return RecipientListOut(items=[_out(r) for r in items])


@router.post("/recipients", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def post_shipping_mailer_recipient(
    body: RecipientCreate,
    admin: dict = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> RecipientOut:
    tenant_id = tenant_id_from_user(admin)
    try:
        row = await add_recipient(
            db,
            tenant_id,
            body.address,
            body.display_name,
            _actor(admin),
        )
    except RecipientValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return _out(row)


@router.patch("/recipients/{recipient_id}", response_model=RecipientOut)
async def patch_shipping_mailer_recipient(
    recipient_id: int,
    body: RecipientPatch,
    admin: dict = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> RecipientOut:
    tenant_id = tenant_id_from_user(admin)
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    display: str | None | object = ...
    if "display_name" in fields:
        display = body.display_name
    row = await patch_recipient(
        db,
        tenant_id,
        recipient_id,
        enabled=body.enabled if "enabled" in fields else None,
        display_name=display,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    await db.commit()
    return _out(row)


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_shipping_mailer_recipient(
    recipient_id: int,
    admin: dict = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    tenant_id = tenant_id_from_user(admin)
    deleted = await delete_recipient(db, tenant_id, recipient_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
