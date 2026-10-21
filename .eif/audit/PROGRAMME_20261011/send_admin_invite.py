"""Send one admin invite. Prints booleans only. Never prints the link or token."""
from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select, text  # noqa: E402

from app.core.password import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.iam import AppUser, Tenant  # noqa: E402
from app.services.account_invite import issue_invite  # noqa: E402
from app.services.platform_audit import record_platform_audit  # noqa: E402

EMAIL = "warren_eliason@asus.com"
TENANT = "default"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print("db_is_cip", dbname == "cip")
        if dbname != "cip":
            return
        tenant = await db.get(Tenant, TENANT)
        print("tenant_exists", tenant is not None)
        if tenant is None:
            return
        found = await db.execute(
            select(AppUser).where(AppUser.tenant_id == TENANT, AppUser.email == EMAIL)
        )
        user = found.scalar_one_or_none()
        created = user is None
        if user is None:
            user = AppUser(
                tenant_id=TENANT,
                email=EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                display_name="Warren Eliason",
                role="admin",
                is_active=True,
            )
            db.add(user)
            await db.flush()
        elif user.role != "admin":
            user.role = "admin"
        print("user_created", created)
        print("role_is_admin", user.role == "admin")
        sent = await issue_invite(db, user)
        print("invite_sent", bool(sent))
        if not sent:
            await db.rollback()
            print("rolled_back", True)
            return
        actor = await db.execute(
            select(AppUser).where(AppUser.tenant_id == TENANT, AppUser.email == "admin@local")
        )
        admin = actor.scalar_one_or_none()
        await record_platform_audit(
            db,
            {
                "id": admin.id if admin is not None else user.id,
                "tenant_id": TENANT,
                "email": admin.email if admin is not None else user.email,
                "display_name": admin.display_name if admin is not None else user.display_name,
            },
            area="admin",
            action="user_create" if created else "user_invite",
            target_type="app_user",
            target_id=str(user.id),
            detail={"role": "admin", "invite_sent": True},
        )
        await db.commit()
        print("committed", True)
        print("local_accounts_retired", False)


if __name__ == "__main__":
    asyncio.run(main())
