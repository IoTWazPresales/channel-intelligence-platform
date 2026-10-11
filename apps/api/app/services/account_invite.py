"""Account invite: one-time set-password link, 72 hours, no password in the mail.

The raw token exists only in the outbound message. The database stores its hash.
Logs record the user id and whether send succeeded. They never record the token,
the link, or the password.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.password import hash_password, hash_session_token, new_session_token
from app.models.iam import AppUser, AppUserInvite, AuthSession
from app.services.shipping_digest.smtp_send import send_digest_email

logger = logging.getLogger(__name__)

INVITE_TTL = timedelta(hours=72)


def compose_invite(link: str) -> tuple[str, str, str]:
    """Subject, plain text, and HTML. The link is the only secret in the message."""
    subject = "Set your Channel Intelligence password"
    text = (
        "You have a Channel Intelligence account.\n\n"
        "Open this link to choose your password. It works once and expires in 72 hours.\n"
        f"{link}\n\n"
        "If you were not expecting this, you can ignore it.\n"
    )
    safe = escape(link, quote=True)
    html = (
        "<p>You have a Channel Intelligence account.</p>"
        "<p>Open this link to choose your password. It works once and expires in 72 hours.</p>"
        f'<p><a href="{safe}">Set your password</a></p>'
        "<p>If you were not expecting this, you can ignore it.</p>"
    )
    return subject, text, html


def invite_link(raw_token: str) -> str:
    origin = get_settings().cip_public_web_origin.strip().rstrip("/")
    return f"{origin}/set-password?token={quote(raw_token, safe='')}"


def new_invite_row(user_id: int, now: datetime) -> tuple[str, AppUserInvite]:
    raw = new_session_token()
    row = AppUserInvite(
        user_id=user_id,
        token_hash=hash_session_token(raw),
        expires_at=now + INVITE_TTL,
    )
    return raw, row


async def issue_invite(db: AsyncSession, user: AppUser, now: datetime | None = None) -> bool:
    """Retire open links, store a new hash, and send the mail. True when SMTP accepted it."""
    now = now or datetime.now(timezone.utc)
    open_rows = await db.execute(
        select(AppUserInvite).where(
            AppUserInvite.user_id == user.id,
            AppUserInvite.used_at.is_(None),
        )
    )
    for prior in open_rows.scalars().all():
        prior.used_at = now
    raw, row = new_invite_row(user.id, now)
    db.add(row)
    await db.flush()
    link = invite_link(raw)
    subject, text, html = compose_invite(link)
    try:
        send_digest_email(
            to_addr=user.email,
            subject=subject,
            html_body=html,
            text_body=text,
        )
    except Exception as exc:
        row.used_at = now
        logger.warning(
            "account_invite send_failed user_id=%s error_type=%s",
            user.id,
            type(exc).__name__,
        )
        return False
    logger.info("account_invite sent user_id=%s", user.id)
    return True


async def accept_invite(db: AsyncSession, token: str, new_password: str) -> bool:
    """Set the password when the link is unused and unexpired. Same failure for every miss."""
    now = datetime.now(timezone.utc)
    token_hash = hash_session_token((token or "").strip())
    found = await db.execute(select(AppUserInvite).where(AppUserInvite.token_hash == token_hash))
    invite = found.scalar_one_or_none()
    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        return False
    user = await db.get(AppUser, invite.user_id)
    if user is None or not user.is_active:
        return False
    user.password_hash = hash_password(new_password)
    user.updated_at = now
    invite.used_at = now
    sessions = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
    )
    for sess in sessions.scalars().all():
        sess.revoked_at = now
    from app.services.platform_audit import record_platform_audit

    await record_platform_audit(
        db,
        {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "display_name": user.display_name,
        },
        area="user",
        action="accept_invite",
        target_type="app_user",
        target_id=str(user.id),
    )
    await db.commit()
    return True
