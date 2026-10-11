"""Record platform audit events. Append-only: callers insert, never update."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.platform_audit import PlatformAuditEvent

AREAS = frozenset({"admin", "user", "settings", "case"})
_SECRET_KEYS = frozenset(
    {"password", "new_password", "token", "token_hash", "password_hash", "secret"}
)


def scrub_audit_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    clean = {k: v for k, v in detail.items() if k not in _SECRET_KEYS}
    return clean or None


def _actor_fields(user: dict | None, actor_label: str | None) -> tuple[int | None, str, str]:
    tenant_id = "default"
    actor_user_id: int | None = None
    label = (actor_label or "").strip()
    if user:
        tenant_id = str(user.get("tenant_id") or "default").strip() or "default"
        uid = user.get("id")
        if uid is not None:
            try:
                actor_user_id = int(uid)
            except (TypeError, ValueError):
                actor_user_id = None
        if not label:
            display = user.get("display_name")
            email = user.get("email")
            label = (
                (str(display).strip() if display else "")
                or (str(email).strip() if email else "")
                or (str(uid) if uid is not None else "")
            )
    return actor_user_id, (label or "system")[:512], tenant_id


def record_platform_audit_sync(
    session: Session,
    user: dict | None,
    *,
    area: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_label: str | None = None,
) -> PlatformAuditEvent:
    area_key = area.strip().lower()
    if area_key not in AREAS:
        raise ValueError(f"unknown audit area {area}")
    actor_user_id, actor, tenant_id = _actor_fields(user, actor_label)
    row = PlatformAuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor=actor,
        area=area_key,
        action=action.strip().lower()[:64],
        target_type=(target_type.strip().lower()[:64] if target_type else None),
        target_id=(str(target_id).strip()[:128] if target_id is not None else None),
        detail_json=scrub_audit_detail(detail),
    )
    session.add(row)
    return row


async def record_platform_audit(
    db: AsyncSession,
    user: dict | None,
    *,
    area: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_label: str | None = None,
    commit: bool = False,
) -> PlatformAuditEvent:
    row = record_platform_audit_sync(
        db,
        user,
        area=area,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        actor_label=actor_label,
    )
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


def record_platform_audit_committed(
    user: dict | None,
    *,
    area: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_label: str | None = None,
) -> None:
    """Own transaction for writers that do not share the request session."""
    with SessionLocal() as session:
        record_platform_audit_sync(
            session,
            user,
            area=area,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            actor_label=actor_label,
        )
        session.commit()
