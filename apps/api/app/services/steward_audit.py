"""Record steward decisions for P2-3 audit trail."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.steward_audit import StewardAuditEvent


def _actor_fields(user: dict | None) -> tuple[int | None, str, str]:
    """Return (actor_user_id, actor label, tenant_id)."""
    if not user:
        return None, "anonymous", "default"
    tenant_id = str(user.get("tenant_id") or "default").strip() or "default"
    email = user.get("email")
    display = user.get("display_name")
    uid = user.get("id")
    actor = (
        (str(display).strip() if display else None)
        or (str(email).strip() if email else None)
        or (str(uid) if uid is not None else "unknown")
    )
    actor_user_id: int | None = None
    if uid is not None:
        try:
            actor_user_id = int(uid)
        except (TypeError, ValueError):
            actor_user_id = None
    return actor_user_id, actor[:512], tenant_id


def _build_event(
    user: dict | None,
    *,
    action: str,
    importer: str,
    entity_type: str | None = None,
    entity_token: str | None = None,
    import_job_id: int | None = None,
    candidate_id: int | None = None,
    target_dim: str | None = None,
    target_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> StewardAuditEvent:
    actor_user_id, actor, tenant_id = _actor_fields(user)
    return StewardAuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor=actor,
        action=action.strip().lower()[:64],
        importer=importer.strip().lower()[:64],
        entity_type=(entity_type.strip().lower()[:64] if entity_type else None),
        entity_token=(entity_token.strip()[:512] if entity_token else None),
        import_job_id=import_job_id,
        candidate_id=candidate_id,
        target_dim=(target_dim.strip().lower()[:64] if target_dim else None),
        target_id=target_id,
        payload_json=payload,
    )


async def record_steward_audit(
    db: AsyncSession,
    user: dict | None,
    *,
    action: str,
    importer: str,
    entity_type: str | None = None,
    entity_token: str | None = None,
    import_job_id: int | None = None,
    candidate_id: int | None = None,
    target_dim: str | None = None,
    target_id: int | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> StewardAuditEvent:
    row = _build_event(
        user,
        action=action,
        importer=importer,
        entity_type=entity_type,
        entity_token=entity_token,
        import_job_id=import_job_id,
        candidate_id=candidate_id,
        target_dim=target_dim,
        target_id=target_id,
        payload=payload,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


def record_steward_audit_sync(
    user: dict | None,
    *,
    action: str,
    importer: str,
    entity_type: str | None = None,
    entity_token: str | None = None,
    import_job_id: int | None = None,
    candidate_id: int | None = None,
    target_dim: str | None = None,
    target_id: int | None = None,
    payload: dict[str, Any] | None = None,
    db: Session | None = None,
) -> StewardAuditEvent:
    """Sync writer for shipment/CPOR/CST steward endpoints (own short session by default)."""
    row = _build_event(
        user,
        action=action,
        importer=importer,
        entity_type=entity_type,
        entity_token=entity_token,
        import_job_id=import_job_id,
        candidate_id=candidate_id,
        target_dim=target_dim,
        target_id=target_id,
        payload=payload,
    )
    if db is not None:
        db.add(row)
        db.flush()
        return row
    with SessionLocal() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
        return row
