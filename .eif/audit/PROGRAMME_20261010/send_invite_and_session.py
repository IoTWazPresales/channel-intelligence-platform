"""Send the requested invite if SMTP is configured, and mint a short browser session.

Prints flags only. Does not print the token, the link, or mailbox secrets.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

from sqlalchemy import select

from app.core.password import hash_password, hash_session_token, new_session_token
from app.db.session import AsyncSessionLocal
from app.models.iam import AppUser, AuthSession
from app.services.account_invite import issue_invite
from app.services.shipping_digest.config import smtp_credentials

EMAIL = "warren_eliason@asus.com"


async def main() -> None:
    host, user, password, port = smtp_credentials()
    print(
        f"smtp host_set={'yes' if host else 'no'} port={port} "
        f"user_set={'yes' if user else 'no'} password_set={'yes' if password else 'no'}"
    )
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(AppUser).where(AppUser.email == EMAIL))).scalar_one_or_none()
        print(
            f"account_exists={'yes' if row else 'no'} "
            f"role={getattr(row, 'role', 'none')} active={getattr(row, 'is_active', 'na')}"
        )
        admin = row if row is not None and row.role == "admin" and row.is_active else None
        if admin is None:
            admin = (
                await db.execute(select(AppUser).where(AppUser.role == "admin", AppUser.is_active.is_(True)).limit(1))
            ).scalar_one_or_none()
        if admin is None:
            print("admin_session=no")
        else:
            token = new_session_token()
            db.add(
                AuthSession(
                    user_id=admin.id,
                    token_hash=hash_session_token(token),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                )
            )
            await db.commit()
            token_path = Path(os.environ["TEMP"]) / "cip-smoke-token.txt"
            token_path.write_text(token, encoding="utf-8")
            print(f"admin_session=yes email_is_target={'yes' if admin.email == EMAIL else 'no'}")

        if not user or not password:
            print("invite_sent=no reason=smtp_unset")
            return
        if row is None:
            chosen = new_session_token()
            row = AppUser(
                tenant_id="default",
                email=EMAIL,
                password_hash=hash_password(chosen),
                display_name="Warren Eliason",
                role="admin",
                is_active=True,
            )
            db.add(row)
            await db.flush()
            print("account_created=yes")
        sent = await issue_invite(db, row)
        await db.commit()
        print(f"invite_sent={'yes' if sent else 'no'}")


if __name__ == "__main__":
    asyncio.run(main())
