"""Auth endpoints: me / login / logout / admin create-user (P2-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_password, hash_session_token, new_session_token, verify_password
from app.core.security import Role, get_current_user, normalize_role, require_roles
from app.models.iam import AppUser, AuthSession, Tenant
from app.services import commercial_tenant_profile

router = APIRouter()

_SESSION_DAYS = 14


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        email = v.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        local, _, domain = email.partition("@")
        if not local or not domain:
            raise ValueError("Invalid email")
        return email


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: dict


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=200)
    role: Role = Role.VIEWER
    tenant_id: str = "default"

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        email = v.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        local, _, domain = email.partition("@")
        if not local or not domain:
            raise ValueError("Invalid email")
        return email


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    settings = get_settings()
    return {
        "id": user["id"],
        "role": user["role"].value if isinstance(user["role"], Role) else user["role"],
        "tenant_id": user.get("tenant_id"),
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "auth_mode": settings.cip_auth_mode,
        "roles_supported": [r.value for r in Role],
    }


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    result = await db.execute(select(AppUser).where(AppUser.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = new_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=_SESSION_DAYS)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return LoginResponse(
        token=token,
        expires_at=expires_at,
        user={
            "id": str(user.id),
            "email": user.email,
            "role": normalize_role(user.role).value,
            "tenant_id": user.tenant_id,
            "display_name": user.display_name,
        },
    )


@router.post("/logout")
async def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            token_hash = hash_session_token(token)
            result = await db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
            session = result.scalar_one_or_none()
            if session and session.revoked_at is None:
                session.revoked_at = datetime.now(timezone.utc)
                await db.commit()
    return {"ok": True}


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    result = await db.execute(
        select(AppUser)
        .where(AppUser.tenant_id == tenant_id)
        .order_by(AppUser.email.asc())
    )
    users = result.scalars().all()
    return {
        "tenant_id": tenant_id,
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "tenant_id": u.tenant_id,
                "is_active": u.is_active,
            }
            for u in users
        ],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (body.tenant_id or "default").strip() or "default"
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tenant_id")

    email = body.email.strip().lower()
    existing = await db.execute(
        select(AppUser).where(AppUser.tenant_id == tenant_id, AppUser.email == email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = AppUser(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        role=body.role.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


class SetPasswordRequest(BaseModel):
    """Admin password reset — local multi-user path until SMTP productisation."""

    new_password: str = Field(min_length=8, max_length=200)
    revoke_sessions: bool = True


@router.post("/users/{user_id}/set-password")
async def admin_set_password(
    user_id: int,
    body: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.now(timezone.utc)
    if body.revoke_sessions:
        result = await db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        now = datetime.now(timezone.utc)
        for sess in result.scalars().all():
            sess.revoked_at = now
    await db.commit()
    return {"ok": True, "user_id": str(user.id), "sessions_revoked": body.revoke_sessions}


class TenantCommercialProfileUpdate(BaseModel):
    """BACKLOG-096 (P6) — onboarding-editable subset only; other profile fields stay env-only."""

    constraint_axis: str | None = None
    over_budget_action: str | None = None
    reservation_source: str | None = None
    pm_attribution_mode: str | None = None


@router.get("/tenant-commercial-profile")
async def get_tenant_commercial_profile(
    user: dict = Depends(get_current_user),
):
    tenant_id = (user.get("tenant_id") or "default").strip() or "default"
    return commercial_tenant_profile.profile_snapshot(tenant_id)


@router.put("/tenant-commercial-profile")
async def put_tenant_commercial_profile(
    body: TenantCommercialProfileUpdate,
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    try:
        commercial_tenant_profile.save_tenant_profile_overrides(
            tenant_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return commercial_tenant_profile.profile_snapshot(tenant_id)
