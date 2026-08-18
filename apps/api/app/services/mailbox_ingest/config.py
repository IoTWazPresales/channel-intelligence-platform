"""Mailbox ingest settings. Read via pydantic Settings (.env), not os.environ alone."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import Settings

_DEFAULT_POLL_SECONDS = 60
_DEFAULT_IMAP_PORT = 993
_DEFAULT_FOLDER = "INBOX"
_DEFAULT_IMAP_HOST = "outlook.office365.com"
_API_ROOT = Path(__file__).resolve().parents[3]


def _settings() -> Settings:
    """Fresh Settings so .env and process env both apply (do not use get_settings cache)."""
    return Settings()


def mailbox_msal_cache_path() -> Path:
    return _API_ROOT / ".mailbox-msal.bin"


def mailbox_graph_client_id() -> str:
    return (_settings().cip_mailbox_graph_client_id or "").strip()


def mailbox_graph_client_secret() -> str:
    return _settings().cip_mailbox_graph_client_secret or ""


def mailbox_graph_tenant() -> str:
    raw = (_settings().cip_mailbox_graph_tenant or "").strip()
    if raw:
        return raw
    user = mailbox_imap_user()
    if "@" in user:
        return user.rsplit("@", 1)[-1]
    return "organizations"


def mailbox_transport() -> str:
    raw = (_settings().cip_mailbox_transport or "auto").strip().lower()
    if raw in ("graph", "imap"):
        return raw
    if mailbox_graph_client_id():
        return "graph"
    return "imap"


def _identity_disabled_reason() -> str | None:
    if not mailbox_imap_user():
        return "CIP_MAILBOX_IMAP_USER missing"
    if mailbox_shipment_source_id() is None:
        return "CIP_MAILBOX_SHIPMENT_SOURCE_ID missing"
    if not mailbox_allowed_senders():
        return "CIP_MAILBOX_ALLOWED_SENDERS empty"
    if mailbox_transport() == "graph":
        if not mailbox_graph_client_id():
            return "CIP_MAILBOX_GRAPH_CLIENT_ID missing"
        return None
    if not mailbox_imap_password():
        return "IMAP user/password missing"
    return None


def mailbox_ingest_enabled() -> bool:
    """Off in pytest; requires CIP_MAILBOX_INGEST_ENABLED and mailbox credentials."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if not _settings().cip_mailbox_ingest_enabled:
        return False
    return _identity_disabled_reason() is None


def mailbox_ingest_poll_interval_seconds() -> int:
    try:
        raw = int(_settings().cip_mailbox_poll_seconds or _DEFAULT_POLL_SECONDS)
    except (TypeError, ValueError):
        raw = _DEFAULT_POLL_SECONDS
    return max(15, min(raw, 3600))


def mailbox_imap_host() -> str:
    host = (_settings().cip_mailbox_imap_host or _DEFAULT_IMAP_HOST).strip()
    return host or _DEFAULT_IMAP_HOST


def mailbox_imap_port() -> int:
    try:
        raw = int(_settings().cip_mailbox_imap_port or _DEFAULT_IMAP_PORT)
    except (TypeError, ValueError):
        raw = _DEFAULT_IMAP_PORT
    return max(1, min(raw, 65535))


def mailbox_imap_user() -> str:
    return (_settings().cip_mailbox_imap_user or "").strip()


def mailbox_imap_password() -> str:
    return _settings().cip_mailbox_imap_password or ""


def mailbox_folder() -> str:
    folder = (_settings().cip_mailbox_folder or _DEFAULT_FOLDER).strip()
    return folder or _DEFAULT_FOLDER


def mailbox_graph_folder() -> str:
    """Graph well-known folder name. IMAP INBOX → inbox."""
    folder = mailbox_folder()
    if folder.strip().upper() == "INBOX":
        return "inbox"
    return folder.strip() or "inbox"


def mailbox_allowed_senders() -> frozenset[str]:
    raw = _settings().cip_mailbox_allowed_senders or ""
    out = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(out)


def mailbox_shipment_source_id() -> int | None:
    sid = _settings().cip_mailbox_shipment_source_id
    if sid is None:
        return None
    try:
        n = int(sid)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def mailbox_env_disabled_reason() -> str | None:
    """Human-readable why the poller will no-op (for FLAG logs). None if enabled."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "pytest"
    if not _settings().cip_mailbox_ingest_enabled:
        return "CIP_MAILBOX_INGEST_ENABLED not set"
    return _identity_disabled_reason()


def mailbox_mailer_recipients() -> tuple[str, ...]:
    """Interim Outlook mailer list (BACKLOG-132). Not used by Unit 1 ingest."""
    raw = _settings().cip_mailbox_mailer_recipients or ""
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())
