"""Shipping-digest send gates and seed-source helper. Send list is DB-backed."""

from __future__ import annotations

from app.core.config import Settings
from app.services.shipping_digest.recipients import DEFAULT_SHIPPING_MAILER_RECIPIENTS


def mailer_send_enabled() -> bool:
    return bool(Settings().cip_shipping_mailer_send)


def mailer_smtp_check_enabled() -> bool:
    return bool(Settings().cip_shipping_mailer_smtp_check)


def mailer_recipients() -> tuple[str, ...]:
    """Seed source only — not the live send list.

    ``CIP_SHIPPING_MAILER_RECIPIENTS`` when set is the first-run seed / break-glass
    source for an *empty* table. A populated UI list wins; see
    ``resolve_shipping_recipients``.
    """
    settings = Settings()
    dedicated = tuple(
        part.strip()
        for part in (settings.cip_shipping_mailer_recipients or "").split(",")
        if part.strip()
    )
    if dedicated:
        return dedicated
    return DEFAULT_SHIPPING_MAILER_RECIPIENTS


def smtp_credentials() -> tuple[str, str, str, int]:
    """Return (host, user, password, port). Password must never be logged."""
    settings = Settings()
    host = (settings.cip_shipping_mailer_smtp_host or "smtp.gmail.com").strip() or "smtp.gmail.com"
    port = int(settings.cip_shipping_mailer_smtp_port or 587)
    user = (settings.cip_mailbox_imap_user or "").strip()
    password = settings.cip_mailbox_imap_password or ""
    return host, user, password, port
