"""SMTP connectivity check: EHLO + STARTTLS/SSL + login + QUIT. No DATA."""

from __future__ import annotations

import logging
from typing import Any

from app.services.shipping_digest.config import smtp_credentials
from app.services.shipping_digest.smtp_send import authenticate_smtp, smtp_client

logger = logging.getLogger(__name__)


def smtp_login_check(*, timeout_s: float = 20.0) -> dict[str, Any]:
    host, user, password, port = smtp_credentials()
    if not user or not password:
        return {"ok": False, "error": "mailbox SMTP credentials missing"}
    ports = [int(port)]
    if int(port) == 587:
        ports.append(465)
    last_error = "unknown"
    for try_port in ports:
        try:
            with smtp_client(host, try_port, timeout_s) as smtp:
                authenticate_smtp(smtp, user=user, password=password, port=try_port)
            logger.info("shipping mailer SMTP check ok user=%s host=%s port=%s", user, host, try_port)
            return {"ok": True, "host": host, "user": user, "port": try_port}
        except Exception as exc:  # noqa: BLE001 — never log the password
            last_error = type(exc).__name__
            logger.exception(
                "shipping mailer SMTP check failed user=%s host=%s port=%s",
                user,
                host,
                try_port,
            )
    return {"ok": False, "error": last_error}
