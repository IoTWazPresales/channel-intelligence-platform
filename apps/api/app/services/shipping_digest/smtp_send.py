"""Send the shipping digest via Gmail SMTP (same IMAP app-password creds)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from app.services.shipping_digest.config import smtp_credentials

logger = logging.getLogger(__name__)


def smtp_client(host: str, port: int, timeout_s: float):
    """Gmail: 587 = STARTTLS, 465 = implicit TLS. This network blocks 587."""
    if int(port) == 465:
        return smtplib.SMTP_SSL(host, int(port), timeout=timeout_s)
    return smtplib.SMTP(host, int(port), timeout=timeout_s)


def authenticate_smtp(smtp: smtplib.SMTP, *, user: str, password: str, port: int) -> None:
    smtp.ehlo()
    if int(port) != 465:
        smtp.starttls()
        smtp.ehlo()
    smtp.login(user, password)


class EmailStubRejected(ValueError):
    """Real SMTP must not use the email_stub channel."""


def public_smtp_error(exc: BaseException, *, secret: str) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    if secret:
        msg = msg.replace(secret, "***")
    return msg[:2000]


def send_digest_email(
    *,
    to_addr: str,
    subject: str,
    html_body: str,
    text_body: str,
    channel: str = "email",
    timeout_s: float = 45.0,
) -> str:
    if channel == "email_stub":
        raise EmailStubRejected("email_stub is not a live send channel")
    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        raise ValueError("recipient_email missing")
    host, user, password, port = smtp_credentials()
    if not user or not password:
        raise RuntimeError("mailbox SMTP credentials missing")
    message_id = make_msgid(domain="gmail.com")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg.set_content(text_body or "")
    msg.add_alternative(html_body or "", subtype="html")
    with smtp_client(host, port, timeout_s) as smtp:
        authenticate_smtp(smtp, user=user, password=password, port=port)
        smtp.send_message(msg)
    return message_id


def send_digest_to_recipients(
    *,
    recipients: list[str] | tuple[str, ...],
    subject: str,
    html_body: str,
    text_body: str,
) -> list[dict[str, Any]]:
    """Attempt one SMTP send per recipient. Failures are returned, never raised."""
    _, _, password, _ = smtp_credentials()
    out: list[dict[str, Any]] = []
    for raw in recipients:
        addr = str(raw or "").strip()
        if not addr:
            continue
        try:
            mid = send_digest_email(
                to_addr=addr,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                channel="email",
            )
            out.append(
                {
                    "recipient_email": addr,
                    "status": "delivered",
                    "provider_message_id": mid,
                    "error_message": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 — per-recipient FLAG, apply must not crash
            logger.exception("shipping digest SMTP failed recipient=%s", addr)
            out.append(
                {
                    "recipient_email": addr,
                    "status": "failed",
                    "provider_message_id": None,
                    "error_message": public_smtp_error(exc, secret=password),
                }
            )
    return out
