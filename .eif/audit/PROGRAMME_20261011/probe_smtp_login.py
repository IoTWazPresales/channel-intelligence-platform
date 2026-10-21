"""SMTP login only. No DATA, no password, no message body."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

logging.disable(logging.CRITICAL)

from app.core.config import get_settings  # noqa: E402
from app.services.shipping_digest.smtp_check import smtp_login_check  # noqa: E402
from app.services.shipping_digest.smtp_send import authenticate_smtp, smtp_client  # noqa: E402
from app.services.shipping_digest.config import smtp_credentials  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    result = smtp_login_check(timeout_s=25.0)
    print("smtp_ok", bool(result.get("ok")))
    print("smtp_port_used", result.get("port"))
    err = result.get("error")
    print("smtp_error_type", err if isinstance(err, str) else None)
    host, user, password, port = smtp_credentials()
    print("configured_port", port)
    print("user_present", bool(user))
    print("password_present", bool(password))
    if not result.get("ok"):
        return
    # Confirm the port the real send will use, not only the fallback inside the check.
    try:
        with smtp_client(host, int(port), 25.0) as smtp:
            authenticate_smtp(smtp, user=user, password=password, port=int(port))
        print("configured_port_login_ok", True)
    except Exception as exc:  # noqa: BLE001
        print("configured_port_login_ok", False)
        print("configured_port_error_type", type(exc).__name__)


if __name__ == "__main__":
    main()
