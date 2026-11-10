"""Auth endpoints: me / login / logout / admin create-user (P2-3)."""

from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.login_throttle import client_address, log_throttle_event, login_throttle
from app.core.password import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.core.product_line_scope import widen_product_line_catalog
from app.core.security import Role, get_current_user, normalize_role, require_roles
from app.core.user_job import normalize_job
from app.models.dimensions import DimCustomer
from app.models.iam import AppUser, AuthSession, Tenant
from app.models.product_line_access import TenantColumnGrain, UserProductLineAccess
from app.services import commercial_tenant_profile
from app.services.account_invite import accept_invite, issue_invite
from app.services.platform_audit import record_platform_audit, record_platform_audit_committed

router = APIRouter()

# The only auth route that must work WITHOUT a bearer: mounted outside the gated api_router
# (see app/api/v1/router.py) so session mode can bootstrap. Everything else on `router`
# inherits the router-level get_current_user dependency.
public_router = APIRouter()

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


def _account_scope(value: str) -> str:
    scope = str(value or "all").strip().lower()
    if scope not in {"all", "selected"}:
        raise ValueError("Account scope is all or selected.")
    return scope


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str | None = None
    display_name: str = Field(min_length=1, max_length=200)
    role: Role = Role.VIEWER
    tenant_id: str = "default"
    account_scope: str = "all"
    customer_ids: list[int] = Field(default_factory=list)
    job: str | None = None

    @field_validator("account_scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        return _account_scope(v)

    @field_validator("job", mode="before")
    @classmethod
    def _job(cls, v: object) -> str | None:
        return normalize_job(v)

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

    @field_validator("password")
    @classmethod
    def _optional_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned == "":
            return None
        if len(cleaned) < 8:
            raise ValueError("Password must be at least 8 characters")
        return cleaned


@router.get("/me")
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.core.my_accounts import header_clears_my_accounts, load_assigned_customer_ids

    settings = get_settings()
    uid = str(user.get("id") or "")
    assigned: list[int] = []
    if uid.isdigit():
        assigned = await load_assigned_customer_ids(
            db,
            tenant_id=str(user.get("tenant_id") or "default").strip() or "default",
            user_id=int(uid),
        )
    cleared = header_clears_my_accounts(request.headers)
    job: str | None = None
    if uid.isdigit():
        row = await db.get(AppUser, int(uid))
        job = row.job if row is not None else None
    return {
        "id": user["id"],
        "role": user["role"].value if isinstance(user["role"], Role) else user["role"],
        "job": job,
        "tenant_id": user.get("tenant_id"),
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "auth_mode": settings.cip_auth_mode,
        "roles_supported": [r.value for r in Role],
        "my_accounts": {
            "assigned_count": len(assigned),
            "filter_on": bool(assigned) and not cleared,
        },
    }


def _too_many_attempts(retry_after: int) -> HTTPException:
    # Same body for account and address throttles, known and unknown emails (no enumeration).
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


@public_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    throttle_on = get_settings().cip_login_throttle_enabled
    address = client_address(request)
    if throttle_on:
        verdict = login_throttle.check(email, address)
        if verdict is not None:
            log_throttle_event("throttled", verdict, account=email, address=address)
            raise _too_many_attempts(verdict.retry_after)

    result = await db.execute(select(AppUser).where(AppUser.email == email))
    user = result.scalar_one_or_none()
    # Always verify (dummy hash when unknown) and only then branch, so unknown / inactive /
    # wrong-password take the same path and roughly the same time.
    password_ok = verify_password(
        body.password, user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    )
    if user is None or not user.is_active or not password_ok:
        if throttle_on:
            for locked in login_throttle.record_failure(email, address):
                log_throttle_event("lockout", locked, account=email, address=address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if throttle_on:
        login_throttle.reset_account(email)

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
                "job": u.job,
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

    # No password from the admin: store a hash nobody knows until the invite link is used.
    chosen = body.password if body.password else secrets.token_urlsafe(32)
    user = AppUser(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(chosen),
        display_name=body.display_name.strip(),
        role=body.role.value,
        job=body.job,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    from app.services.my_account_assignments import AccountAssignmentError, replace_user_accounts

    try:
        chosen_accounts = await replace_user_accounts(
            db,
            tenant_id=tenant_id,
            user_id=int(user.id),
            scope=body.account_scope,
            customer_ids=list(body.customer_ids),
        )
    except AccountAssignmentError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    invite_sent = await issue_invite(db, user)
    await record_platform_audit(
        db,
        _admin,
        area="admin",
        action="user_create",
        target_type="app_user",
        target_id=str(user.id),
        detail={
            "role": user.role,
            "job": user.job,
            "invite_sent": invite_sent,
            "account_count": len(chosen_accounts),
        },
    )
    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "job": user.job,
        "tenant_id": user.tenant_id,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "invite_sent": invite_sent,
    }


class UserJobBody(BaseModel):
    job: str | None = None

    @field_validator("job", mode="before")
    @classmethod
    def _job(cls, v: object) -> str | None:
        return normalize_job(v)


@router.put("/users/{user_id}/job")
async def put_user_job(
    user_id: int,
    body: UserJobBody,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    """N-0100 part B: set or clear a user's job. The role is never changed here."""
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = user.job
    user.job = body.job
    user.updated_at = datetime.now(timezone.utc)
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="user_job",
        target_type="app_user",
        target_id=str(user.id),
        detail={"job": body.job, "previous_job": previous},
    )
    await db.commit()
    return {"user_id": str(user.id), "job": body.job, "role": user.role}


class AccountAssignmentBody(BaseModel):
    account_scope: str = "all"
    customer_ids: list[int] = Field(default_factory=list)

    @field_validator("account_scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        return _account_scope(v)


def _like_contains(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/customer-accounts")
async def list_customer_accounts(
    q: str = Query(default="", max_length=80),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    """Existing customer accounts in this tenant. The picker does not create one."""
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    stmt = select(DimCustomer.id, DimCustomer.name).where(DimCustomer.tenant_id == tenant_id)
    term = q.strip()
    if term:
        stmt = stmt.where(DimCustomer.name.ilike(_like_contains(term), escape="\\"))
    rows = (await db.execute(stmt.order_by(DimCustomer.name.asc()).limit(50))).all()
    return {"accounts": [{"id": int(row.id), "name": row.name} for row in rows]}


@router.get("/users/{user_id}/accounts")
async def get_user_accounts(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    from app.core.my_accounts import load_assigned_customer_ids

    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    ids = await load_assigned_customer_ids(db, tenant_id=tenant_id, user_id=int(user.id))
    names: dict[int, str] = {}
    if ids:
        found = (
            await db.execute(
                select(DimCustomer.id, DimCustomer.name).where(
                    DimCustomer.tenant_id == tenant_id,
                    DimCustomer.id.in_(ids),
                )
            )
        ).all()
        names = {int(row.id): str(row.name or "") for row in found}
    return {
        "user_id": str(user.id),
        "account_scope": "selected" if ids else "all",
        "customer_ids": ids,
        "accounts": [{"id": cid, "name": names.get(cid, "")} for cid in ids],
    }


@router.put("/users/{user_id}/accounts")
async def put_user_accounts(
    user_id: int,
    body: AccountAssignmentBody,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    from app.services.my_account_assignments import AccountAssignmentError, replace_user_accounts

    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        chosen = await replace_user_accounts(
            db,
            tenant_id=tenant_id,
            user_id=int(user.id),
            scope=body.account_scope,
            customer_ids=list(body.customer_ids),
        )
    except AccountAssignmentError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="user_accounts",
        target_type="app_user",
        target_id=str(user.id),
        detail={"account_scope": body.account_scope, "account_count": len(chosen)},
    )
    await db.commit()
    return {
        "user_id": str(user.id),
        "account_scope": "selected" if chosen else "all",
        "customer_ids": chosen,
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
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="user_set_password",
        target_type="app_user",
        target_id=str(user.id),
        detail={"sessions_revoked": body.revoke_sessions},
    )
    await db.commit()
    return {"ok": True, "user_id": str(user.id), "sessions_revoked": body.revoke_sessions}


@router.post("/users/{user_id}/invite")
async def resend_user_invite(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    invite_sent = await issue_invite(db, user)
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="user_invite",
        target_type="app_user",
        target_id=str(user.id),
        detail={"invite_sent": invite_sent},
    )
    await db.commit()
    return {"ok": True, "user_id": str(user.id), "invite_sent": invite_sent}


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=8, max_length=200)


@public_router.post("/invites/accept")
async def accept_user_invite(body: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    ok = await accept_invite(db, body.token, body.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is not valid. Ask an admin to send a new one.",
        )
    return {"ok": True}


class TenantCommercialProfileUpdate(BaseModel):
    """BACKLOG-096 (P6) — onboarding-editable subset; lineup export sheets/columns are Lane B tenant law."""

    constraint_axis: str | None = None
    over_budget_action: str | None = None
    reservation_source: str | None = None
    pm_attribution_mode: str | None = None
    line_identifier_preference: str | None = None
    lineup_export_net_requirement_sheet: str | None = None
    lineup_export_draft_sheet: str | None = None
    reporting_cadence: str | None = None
    woc_min_velocity_days: int | None = None
    stock_gap_highlight_units: float | None = None
    business_calendar: dict[str, Any] | None = None
    vat_rate_pct: float | None = None
    sales_value_vat_basis: str | None = None


class BusinessCalendarPreviewRequest(BaseModel):
    business_calendar: dict[str, Any] = Field(default_factory=dict)
    on: date | None = None


@router.post("/business-calendar/preview")
async def preview_business_calendar(
    body: BusinessCalendarPreviewRequest,
    user: dict = Depends(get_current_user),
):
    """The year containing ``on`` (default today) under a calendar setting, before it is saved."""
    from app.services.business_calendar import BusinessCalendar, normalize_calendar_config

    try:
        cfg = normalize_calendar_config(body.business_calendar, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    tenant_id = (user.get("tenant_id") or "default").strip() or "default"
    on = body.on or commercial_tenant_profile.reporting_today(tenant_id)
    return {"business_calendar": cfg, **BusinessCalendar(cfg).describe_year(on)}


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
    record_platform_audit_committed(
        admin,
        area="settings",
        action="tenant_profile",
        target_type="tenant",
        target_id=tenant_id,
        detail={"fields": sorted(body.model_dump(exclude_unset=True))},
    )
    return commercial_tenant_profile.profile_snapshot(tenant_id)


class ProductLineAssignment(BaseModel):
    product_line: str = Field(min_length=1, max_length=256)
    can_edit: bool = False


class ProductLineAssignmentBody(BaseModel):
    assignments: list[ProductLineAssignment]


class ColumnGrainBody(BaseModel):
    # The grain names a key inside column_mapping_memory.mapping_profile, so keep it an identifier.
    grain: str = Field(min_length=1, max_length=64)

    @field_validator("grain")
    @classmethod
    def _identifier(cls, v: str) -> str:
        grain = v.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", grain):
            raise ValueError("grain must be a lowercase name such as product_line")
        return grain


@router.get("/product-lines")
async def list_product_lines(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    """Every product line on the master, so an admin can assign them."""
    await widen_product_line_catalog(db)
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT btrim(product_line) AS product_line
                FROM dim_product
                WHERE product_line IS NOT NULL AND btrim(product_line) <> ''
                ORDER BY 1
                """
            )
        )
    ).all()
    return {
        "tenant_id": (admin.get("tenant_id") or "default").strip() or "default",
        "product_lines": [str(row.product_line) for row in rows],
    }


@router.get("/users/{user_id}/product-lines")
async def get_user_product_lines(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = (
        await db.execute(
            select(UserProductLineAccess)
            .where(UserProductLineAccess.user_id == user.id)
            .order_by(UserProductLineAccess.product_line.asc())
        )
    ).scalars().all()
    return {
        "user_id": str(user.id),
        "assignments": [
            {"product_line": row.product_line, "can_edit": bool(row.can_edit)} for row in rows
        ],
    }


@router.put("/users/{user_id}/product-lines")
async def put_user_product_lines(
    user_id: int,
    body: ProductLineAssignmentBody,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    user = await db.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    seen: set[str] = set()
    clean: list[tuple[str, bool]] = []
    for item in body.assignments:
        line = item.product_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        clean.append((line, bool(item.can_edit)))
    existing = (
        await db.execute(select(UserProductLineAccess).where(UserProductLineAccess.user_id == user.id))
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    for line, can_edit in clean:
        db.add(
            UserProductLineAccess(
                tenant_id=tenant_id,
                user_id=user.id,
                product_line=line,
                can_edit=can_edit,
            )
        )
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="user_product_lines",
        target_type="app_user",
        target_id=str(user.id),
        detail={"line_count": len(clean)},
    )
    await db.commit()
    return {
        "user_id": str(user.id),
        "assignments": [{"product_line": line, "can_edit": can_edit} for line, can_edit in clean],
    }


@router.get("/column-grain")
async def get_column_grain(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    row = await db.get(TenantColumnGrain, tenant_id)
    return {"tenant_id": tenant_id, "grain": row.grain if row else "product_line"}


@router.put("/column-grain")
async def put_column_grain(
    body: ColumnGrainBody,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
):
    tenant_id = (admin.get("tenant_id") or "default").strip() or "default"
    grain = body.grain.strip()
    if not grain:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="grain is required")
    row = await db.get(TenantColumnGrain, tenant_id)
    if row is None:
        row = TenantColumnGrain(tenant_id=tenant_id, grain=grain)
        db.add(row)
    else:
        row.grain = grain
    await record_platform_audit(
        db,
        admin,
        area="settings",
        action="column_grain",
        target_type="tenant",
        target_id=tenant_id,
        detail={"grain": grain},
    )
    await db.commit()
    return {"tenant_id": tenant_id, "grain": grain}
