"""Auth: session mode (P2-3) with optional stub fallback for local transition."""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_session_token
from app.models.iam import AppUser, AuthSession


class Role(str, Enum):
    """Charter P2-3 roles (collapsed from the prior 7-value stub)."""

    ADMIN = "admin"
    STEWARD = "steward"
    PLANNER = "planner"
    VIEWER = "viewer"


# Backward-compatible aliases for call sites / headers still using old names.
_ROLE_ALIASES: dict[str, Role] = {
    "admin": Role.ADMIN,
    "steward": Role.STEWARD,
    "data_steward": Role.STEWARD,
    "planner": Role.PLANNER,
    "commercial_manager": Role.PLANNER,
    "product_manager": Role.PLANNER,
    "viewer": Role.VIEWER,
    "executive_viewer": Role.VIEWER,
    "finance_reviewer": Role.VIEWER,
}


def normalize_role(raw: str | None) -> Role:
    if not raw:
        return Role.VIEWER
    key = str(raw).strip().lower()
    return _ROLE_ALIASES.get(key, Role.VIEWER)


def _user_payload(
    user_id: str,
    role: Role,
    *,
    tenant_id: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
) -> dict:
    return {
        "id": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "email": email,
        "display_name": display_name,
    }


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    mode = (settings.cip_auth_mode or "stub").strip().lower()

    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip() or None

    if bearer:
        token_hash = hash_session_token(bearer)
        result = await db.execute(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .options(selectinload(AuthSession.user))
        )
        session = result.scalar_one_or_none()
        if session is None or session.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        from datetime import datetime, timezone

        if session.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        user = session.user
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return _user_payload(
            str(user.id),
            normalize_role(user.role),
            tenant_id=user.tenant_id,
            email=user.email,
            display_name=user.display_name,
        )

    if mode == "session":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # Stub / transition mode: forgeable headers (local only).
    return _user_payload(
        x_user_id or "demo-user",
        normalize_role(x_user_role or Role.ADMIN.value),
        tenant_id="default",
        email=None,
        display_name=None,
    )


# Legacy name used by older call sites.
get_current_user_stub = get_current_user


def require_roles(*allowed: Role):
    allowed_set = set(allowed)

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        role: Role = user["role"]
        if role == Role.ADMIN:
            return user
        if role not in allowed_set:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _dep
