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
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

KEY_DISCOVERY_SCHEDULE = "discovery.schedule_enabled"
KEY_TENANT_COUNTRY = "tenant.country"
KEY_TENANT_DOMAIN_ENDINGS = "tenant.domain_endings"
KEY_DISCOVERY_SEARCH_PROVIDERS = "discovery.search_providers"
KEY_DISCOVERY_SEARXNG_URL = "discovery.searxng_url"
KEY_DISCOVERY_EXCLUDED_DOMAINS = "discovery.excluded_domains"
KEY_DISCOVERY_BROWSER_FALLBACK = "discovery.browser_fallback_enabled"

# The search providers a tenant may list. These are provider ids, not sites; the provider
# implementations live in ``listing_capture.web_discovery.search``.
SEARCH_PROVIDER_IDS: tuple[str, ...] = ("ddg_html", "ddg_lite", "searxng")
MAX_DOMAIN_ENDINGS = 20
MAX_EXCLUDED_DOMAINS = 200

_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_DOMAIN_ENDING = re.compile(r"^\.[a-z0-9-]+(\.[a-z0-9-]+)*$")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("value must be true or false")


def _as_country(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"code", "name"}:
        raise ValueError('country must be an object with "code" and "name"')
    code = value["code"]
    name = value["name"]
    if not isinstance(code, str) or not _COUNTRY_CODE.fullmatch(code.strip()):
        raise ValueError("country code must be two capital letters")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
        raise ValueError("country name must be 1 to 64 characters")
    return {"code": code.strip(), "name": name.strip()}


def _as_domain_endings(value: Any) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_DOMAIN_ENDINGS:
        raise ValueError(f"give 1 to {MAX_DOMAIN_ENDINGS} domain endings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("each domain ending must be text")
        ending = item.strip().lower()
        if not _DOMAIN_ENDING.fullmatch(ending):
            raise ValueError(f"domain ending {item!r} must start with a dot, for example .example")
        if ending not in out:
            out.append(ending)
    return out


def _as_search_providers(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > len(SEARCH_PROVIDER_IDS):
        raise ValueError(f"give at most {len(SEARCH_PROVIDER_IDS)} search providers")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() not in SEARCH_PROVIDER_IDS:
            raise ValueError(f"search provider must be one of {', '.join(SEARCH_PROVIDER_IDS)}")
        if item.strip() not in out:
            out.append(item.strip())
    return out


def _as_https_base_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("the SearXNG address must be an https:// URL")
    text = value.strip()
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment or parts.username:
        raise ValueError("the SearXNG address must be an https:// URL with no query string")
    return text.rstrip("/")


def _as_excluded_domains(value: Any) -> list[str]:
    from app.services.listing_capture.site_onboarding import normalize_domain

    if not isinstance(value, list) or len(value) > MAX_EXCLUDED_DOMAINS:
        raise ValueError(f"give at most {MAX_EXCLUDED_DOMAINS} excluded domains")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("each excluded domain must be text")
        host = normalize_domain(item)
        if host not in out:
            out.append(host)
    return out


# key -> validator returning the cleaned value. Later features register their own keys here.
SETTING_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    KEY_DISCOVERY_SCHEDULE: _as_bool,
    KEY_TENANT_COUNTRY: _as_country,
    KEY_TENANT_DOMAIN_ENDINGS: _as_domain_endings,
    KEY_DISCOVERY_SEARCH_PROVIDERS: _as_search_providers,
    KEY_DISCOVERY_SEARXNG_URL: _as_https_base_url,
    KEY_DISCOVERY_EXCLUDED_DOMAINS: _as_excluded_domains,
    KEY_DISCOVERY_BROWSER_FALLBACK: _as_bool,
}


def _check_searxng_url_present(session: Session, tenant_id: str, clean: Any) -> None:
    if "searxng" in clean and get_setting(session, tenant_id, KEY_DISCOVERY_SEARXNG_URL) is None:
        raise ValueError(f"set {KEY_DISCOVERY_SEARXNG_URL} before adding searxng to the providers")


# key -> check that needs the tenant's other settings. Runs after the value validates.
CROSS_CHECKS: dict[str, Callable[[Session, str, Any], None]] = {
    KEY_DISCOVERY_SEARCH_PROVIDERS: _check_searxng_url_present,
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
    cross_check = CROSS_CHECKS.get(key)
    if cross_check is not None:
        cross_check(session, tenant_id, clean)
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
                text("SELECT tenant_id FROM tenant_setting WHERE key = :k AND value = 'true'::jsonb ORDER BY tenant_id"),
                {"k": key},
            ).all()
        return [str(r[0]) for r in rows]
    except Exception:
        logger.exception("tenant setting %s unreadable; treating it as off for every tenant", key)
        return []
