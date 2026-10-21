"""Step through SMTP without printing secrets. No DATA."""
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
from app.services.shipping_digest.smtp_send import public_smtp_error  # noqa: E402


def step(name: str, fn) -> bool:
    try:
        fn()
        print(name, "ok")
        return True
    except Exception as exc:  # noqa: BLE001
        host, _user, password, _port = smtp_credentials()
        print(name, "fail", type(exc).__name__, public_smtp_error(exc, secret=password)[:160])
        return False


def main() -> None:
    get_settings.cache_clear()
    host, user, password, port = smtp_credentials()
    print("configured_port", port)
    smtp = smtplib.SMTP(host, 587, timeout=20)
    try:
        if not step("connect_587", lambda: None):
            return
        code = smtp.ehlo()[0]
        print("ehlo_code", code)
        if not step("starttls", smtp.starttls):
            return
        code2 = smtp.ehlo()[0]
        print("ehlo_after_tls_code", code2)
        if not step("login", lambda: smtp.login(user, password)):
            return
        print("login_ok", True)
    finally:
        try:
            smtp.quit()
        except Exception:
            smtp.close()


if __name__ == "__main__":
    main()
