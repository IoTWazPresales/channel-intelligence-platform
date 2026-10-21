"""Print SMTP reply codes around AUTH. No password, no message."""
from __future__ import annotations

import logging
import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
logging.disable(logging.CRITICAL)

from app.core.config import get_settings  # noqa: E402
from app.services.shipping_digest.config import smtp_credentials  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    host, user, password, _port = smtp_credentials()
    print("password_len", len(password))
    print("password_has_space", " " in password)
    print("password_has_punct", any(not ch.isalnum() for ch in password))
    smtp = smtplib.SMTP(host, 587, timeout=20)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    features = smtp.esmtp_features or {}
    print("auth_advertised", features.get("auth"))
    try:
        code, reply = smtp.login(user, password)
        print("login_code", code)
        print("login_reply_len", len(reply or b""))
    except smtplib.SMTPResponseException as exc:
        print("login_code", exc.smtp_code)
        text = exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        if password:
            text = text.replace(password, "***")
        print("login_reply", text[:180])
    except smtplib.SMTPServerDisconnected:
        print("login_code", None)
        print("login_reply", "socket closed before a code")
    finally:
        try:
            smtp.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
