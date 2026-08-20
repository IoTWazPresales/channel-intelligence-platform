"""DB-backed shipping-digest recipient list. UI list wins; env is seed only."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.tenant_scope import DEFAULT_TENANT_ID
from app.models.shipping_mailer_recipient import ShippingMailerRecipient
from app.services.mailbox_ingest.imap_fetch import normalize_email_addr
from app.services.shipping_digest.config import mailer_recipients

SEED_ADDED_BY = "system:seed"


class RecipientValidationError(ValueError):
    """Invalid SMTP address input."""


def _tenant(tenant_id: str | None) -> str:
    tid = (tenant_id or "").strip()
    return tid or DEFAULT_TENANT_ID


def stored_address_from_input(value: str | None) -> str:
    """Trim and extract a bare address; preserve casing. Empty if not a usable email."""
    raw = (value or "").strip()
    if not raw:
        return ""
    _name, parsed = parseaddr(raw)
    candidate = (parsed or raw).strip()
    if not candidate or "@" not in candidate:
        return ""
    if not normalize_email_addr(candidate):
        return ""
    return candidate


def recipient_to_dict(row: ShippingMailerRecipient) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tenant_id": row.tenant_id,
        "address": row.address,
        "display_name": row.display_name,
        "enabled": bool(row.enabled),
        "added_by": row.added_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _count_for_tenant(session: Session, tenant_id: str) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(ShippingMailerRecipient)
            .where(ShippingMailerRecipient.tenant_id == tenant_id)
        ).scalar_one()
    )


def _get_by_normalized(session: Session, tenant_id: str, norm: str) -> ShippingMailerRecipient | None:
    return session.execute(
        select(ShippingMailerRecipient).where(
            ShippingMailerRecipient.tenant_id == tenant_id,
            func.lower(ShippingMailerRecipient.address) == norm,
        )
    ).scalars().first()


def ensure_seeded_sync(session: Session, tenant_id: str, added_by: str = SEED_ADDED_BY) -> int:
    """If the tenant has zero rows, insert seed addresses. Returns inserted count."""
    tenant_id = _tenant(tenant_id)
    if _count_for_tenant(session, tenant_id):
        return 0
    inserted = 0
    for addr in mailer_recipients():
        stored = stored_address_from_input(addr)
        if not stored:
            continue
        norm = normalize_email_addr(stored)
        if _get_by_normalized(session, tenant_id, norm) is not None:
            continue
        try:
            with session.begin_nested():
                session.add(
                    ShippingMailerRecipient(
                        tenant_id=tenant_id,
                        address=stored,
                        display_name=None,
                        enabled=True,
                        added_by=added_by,
                    )
                )
                session.flush()
            inserted += 1
        except IntegrityError:
            continue
    return inserted


def list_recipients_sync(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    tenant_id = _tenant(tenant_id)
    ensure_seeded_sync(session, tenant_id)
    rows = session.execute(
        select(ShippingMailerRecipient)
        .where(ShippingMailerRecipient.tenant_id == tenant_id)
        .order_by(ShippingMailerRecipient.created_at, ShippingMailerRecipient.id)
    ).scalars().all()
    return [recipient_to_dict(r) for r in rows]


def resolve_shipping_recipients_sync(session: Session, tenant_id: str) -> tuple[str, ...]:
    """Enabled To-list. Empty table seeds first; all-disabled returns empty (mute)."""
    tenant_id = _tenant(tenant_id)
    ensure_seeded_sync(session, tenant_id)
    rows = session.execute(
        select(ShippingMailerRecipient)
        .where(
            ShippingMailerRecipient.tenant_id == tenant_id,
            ShippingMailerRecipient.enabled.is_(True),
        )
        .order_by(ShippingMailerRecipient.created_at, ShippingMailerRecipient.id)
    ).scalars().all()
    return tuple(str(r.address) for r in rows)


def add_recipient_sync(
    session: Session,
    tenant_id: str,
    address: str,
    display_name: str | None,
    added_by: str | None,
) -> dict[str, Any]:
    tenant_id = _tenant(tenant_id)
    stored = stored_address_from_input(address)
    if not stored:
        raise RecipientValidationError("A valid email address is required")
    norm = normalize_email_addr(stored)
    existing = _get_by_normalized(session, tenant_id, norm)
    now = datetime.now(timezone.utc)
    name = (display_name or "").strip() or None
    if existing is not None:
        existing.enabled = True
        if display_name is not None:
            existing.display_name = name
        existing.updated_at = now
        session.flush()
        return recipient_to_dict(existing)
    row = ShippingMailerRecipient(
        tenant_id=tenant_id,
        address=stored,
        display_name=name,
        enabled=True,
        added_by=added_by,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raced = _get_by_normalized(session, tenant_id, norm)
        if raced is not None:
            raced.enabled = True
            if display_name is not None:
                raced.display_name = name
            raced.updated_at = now
            session.flush()
            return recipient_to_dict(raced)
        raise RecipientValidationError("That address is already on the list") from exc
    return recipient_to_dict(row)


def patch_recipient_sync(
    session: Session,
    tenant_id: str,
    recipient_id: int,
    *,
    enabled: bool | None = None,
    display_name: str | None | object = ...,
) -> dict[str, Any] | None:
    tenant_id = _tenant(tenant_id)
    row = session.execute(
        select(ShippingMailerRecipient).where(
            ShippingMailerRecipient.id == int(recipient_id),
            ShippingMailerRecipient.tenant_id == tenant_id,
        )
    ).scalars().first()
    if row is None:
        return None
    if enabled is not None:
        row.enabled = bool(enabled)
    if display_name is not ...:
        raw = display_name
        row.display_name = (str(raw).strip() or None) if raw is not None else None
    row.updated_at = datetime.now(timezone.utc)
    session.flush()
    return recipient_to_dict(row)


def delete_recipient_sync(session: Session, tenant_id: str, recipient_id: int) -> bool:
    tenant_id = _tenant(tenant_id)
    row = session.execute(
        select(ShippingMailerRecipient).where(
            ShippingMailerRecipient.id == int(recipient_id),
            ShippingMailerRecipient.tenant_id == tenant_id,
        )
    ).scalars().first()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


async def ensure_seeded(db: AsyncSession, tenant_id: str, added_by: str = SEED_ADDED_BY) -> int:
    return await db.run_sync(ensure_seeded_sync, tenant_id, added_by)


async def list_recipients(db: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    return await db.run_sync(list_recipients_sync, tenant_id)


async def resolve_shipping_recipients(db: AsyncSession, tenant_id: str) -> tuple[str, ...]:
    return await db.run_sync(resolve_shipping_recipients_sync, tenant_id)


async def add_recipient(
    db: AsyncSession,
    tenant_id: str,
    address: str,
    display_name: str | None,
    added_by: str | None,
) -> dict[str, Any]:
    return await db.run_sync(add_recipient_sync, tenant_id, address, display_name, added_by)


async def patch_recipient(
    db: AsyncSession,
    tenant_id: str,
    recipient_id: int,
    *,
    enabled: bool | None = None,
    display_name: str | None | object = ...,
) -> dict[str, Any] | None:
    def _work(session: Session) -> dict[str, Any] | None:
        return patch_recipient_sync(
            session,
            tenant_id,
            recipient_id,
            enabled=enabled,
            display_name=display_name,
        )

    return await db.run_sync(_work)


async def delete_recipient(db: AsyncSession, tenant_id: str, recipient_id: int) -> bool:
    return await db.run_sync(delete_recipient_sync, tenant_id, recipient_id)
