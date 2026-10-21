"""Per-port SMTP login. Redacts the password. No DATA."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
logging.disable(logging.CRITICAL)

from app.core.config import get_settings  # noqa: E402
from app.services.shipping_digest.config import smtp_credentials  # noqa: E402
from app.services.shipping_digest.smtp_send import authenticate_smtp, public_smtp_error, smtp_client  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    host, user, password, _port = smtp_credentials()
    print("host_is_gmail", host == "smtp.gmail.com")
    print("user_present", bool(user))
    print("password_present", bool(password))
    print("password_len", len(password))
    for port in (587, 465):
        try:
            with smtp_client(host, port, 20.0) as smtp:
                authenticate_smtp(smtp, user=user, password=password, port=port)
            print(f"port_{port}_ok", True)
        except Exception as exc:  # noqa: BLE001
            safe = public_smtp_error(exc, secret=password)
            print(f"port_{port}_ok", False)
            print(f"port_{port}_error_type", type(exc).__name__)
            print(f"port_{port}_error", safe[:180])


if __name__ == "__main__":
    main()
