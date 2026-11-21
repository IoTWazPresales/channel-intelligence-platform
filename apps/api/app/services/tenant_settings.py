"""Tenant settings: one row per tenant and key, written only by a user in the app.

There are no seeded defaults. A key with no row reads as the caller's ``default`` (for the
discovery schedule that is "off"). Keys are registered here with a validator, so a typo or
an unknown key is refused rather than stored.

Reads that gate an automatic run (``tenants_with_true``) fail closed: any error, including a
database that has not had migration 20261120_0064 applied, reads as "no tenant enabled".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

KEY_DISCOVERY_SCHEDULE = "discovery.schedule_enabled"
KEY_MAP_TILEJSON = "map.tilejson_url"
KEY_MAP_GLYPHS = "map.glyphs_url"
KEY_MAP_ATTRIBUTION = "map.attribution"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("value must be true or false")


def _optional_text(value: Any, *, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("value must be text or null")
    clean = value.strip()
    if not clean:
        return None
    if len(clean) > limit or any(ord(char) < 32 for char in clean):
        raise ValueError(f"value must be at most {limit} characters without control characters")
    return clean


def _map_url(value: Any) -> str | None:
    """Validate stored configuration only; the API never fetches these URLs."""
    clean = _optional_text(value, limit=2048)
    if clean is None:
        return None
    try:
        parsed = urlsplit(clean)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and not any(char.isspace() for char in clean)
        )
        # Accessing port also validates malformed/out-of-range ports.
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("use an absolute HTTP(S) URL without credentials or a fragment") from exc
    if not valid:
        raise ValueError("use an absolute HTTP(S) URL without credentials or a fragment")
    return clean


def _map_glyphs_url(value: Any) -> str | None:
    clean = _map_url(value)
    if clean is not None and ("{fontstack}" not in clean or "{range}" not in clean):
        raise ValueError("glyph URL must contain {fontstack} and {range}")
    return clean


def _map_attribution(value: Any) -> str | None:
    clean = _optional_text(value, limit=1000)
    if clean is not None and ("<" in clean or ">" in clean):
        raise ValueError("attribution must be plain text, without HTML")
    return clean


# No map defaults or provider URLs are stored or supplied here.
# PMTiles is deliberately not registered until a client protocol implementation exists.
SETTING_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    KEY_DISCOVERY_SCHEDULE: _as_bool,
    KEY_MAP_TILEJSON: _map_url,
    KEY_MAP_GLYPHS: _map_glyphs_url,
    KEY_MAP_ATTRIBUTION: _map_attribution,
}


def register_setting(key: str, validator: Callable[[Any], Any]) -> None:
    SETTING_VALIDATORS[key] = validator


def get_setting(session: Session, tenant_id: str, key: str, default: Any = None) -> Any:
    row = session.execute(
        text("SELECT value FROM tenant_setting WHERE tenant_id = :t AND key = :k"),
        {"t": tenant_id, "k": key},
    ).first()
    return default if row is None else row[0]


def list_settings(session: Session, tenant_id: str) -> dict[str, Any]:
    rows = session.execute(
        text("SELECT key, value FROM tenant_setting WHERE tenant_id = :t ORDER BY key"),
        {"t": tenant_id},
    ).all()
    return {str(r[0]): r[1] for r in rows}


def set_setting(session: Session, tenant_id: str, key: str, value: Any, *, actor: str | None) -> Any:
    validator = SETTING_VALIDATORS.get(key)
    if validator is None:
        raise ValueError(f"unknown setting: {key}")
    clean = validator(value)
    session.execute(
        text(
            "INSERT INTO tenant_setting (tenant_id, key, value, updated_by) "
            "VALUES (:t, :k, CAST(:v AS jsonb), :a) "
            "ON CONFLICT (tenant_id, key) DO UPDATE "
            "SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()"
        ),
        {"t": tenant_id, "k": key, "v": json.dumps(clean), "a": actor},
    )
    return clean


def tenants_with_true(session: Session, key: str) -> list[str]:
    """Tenants whose setting ``key`` is exactly true. Fails closed: any error gives no tenants."""
    try:
        with session.begin_nested():
            rows = session.execute(
                text(
                    "SELECT tenant_id FROM tenant_setting "
                    "WHERE key = :k AND value = 'true'::jsonb ORDER BY tenant_id"
                ),
                {"k": key},
            ).all()
        return [str(r[0]) for r in rows]
    except Exception:
        logger.exception("tenant setting %s unreadable; treating it as off for every tenant", key)
        return []
