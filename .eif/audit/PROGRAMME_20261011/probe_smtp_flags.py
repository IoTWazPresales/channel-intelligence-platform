"""Print whether the digest mailer is the named Gmail account. No secret values."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import os

os.chdir(ROOT / "apps" / "api")
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import get_settings

EXPECTED = "warren.eliason@gmail.com"


def _file_flags() -> None:
    """Booleans from the env file itself, ignoring process environment overrides."""
    path = ROOT / "apps" / "api" / ".env"
    wanted = {
        "CIP_MAILBOX_IMAP_USER": "file_user",
        "CIP_MAILBOX_IMAP_PASSWORD": "file_password",
        "CIP_SHIPPING_MAILER_SEND": "file_send",
    }
    found = {k: "" for k in wanted}
    if not path.exists():
        print("env_file_exists", False)
        return
    print("env_file_exists", True)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key in found:
            found[key] = val.strip().strip('"').strip("'")
    user = found["CIP_MAILBOX_IMAP_USER"].lower()
    print("file_user_set", bool(user))
    print("file_user_is_digest_gmail", user == EXPECTED)
    print("file_password_set", bool(found["CIP_MAILBOX_IMAP_PASSWORD"]))
    send = found["CIP_SHIPPING_MAILER_SEND"].lower()
    print("file_send_enabled", send in {"1", "true", "yes", "on"})
    mail_keys = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if any(part in key.upper() for part in ("MAIL", "SMTP", "IMAP", "GMAIL")):
            mail_keys.append(key)
    print("mail_keys", ",".join(mail_keys) if mail_keys else "none")
    for key in wanted:
        env_val = os.environ.get(key)
        print(f"process_{wanted[key]}_overrides", env_val is not None)


def main() -> None:
    s = get_settings()
    user = (s.cip_mailbox_imap_user or "").strip().lower()
    print("user_set", bool(user))
    print("user_is_digest_gmail", user == EXPECTED)
    print("password_set", bool(s.cip_mailbox_imap_password))
    print("smtp_host", s.cip_shipping_mailer_smtp_host)
    print("smtp_port", s.cip_shipping_mailer_smtp_port)
    print("send_enabled", bool(s.cip_shipping_mailer_send))
    _file_flags()


if __name__ == "__main__":
    main()
