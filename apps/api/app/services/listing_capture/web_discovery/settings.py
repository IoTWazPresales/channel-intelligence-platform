"""Load the tenant's discovery settings. No defaults, nothing seeded: a missing key is "not set".

``load_discovery_settings`` re-validates what it reads with the same validators the settings
endpoint uses, so a stored value that no longer validates reads as missing rather than being
trusted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy.orm import Session

from app.services import tenant_settings as ts

SCOPE_CUSTOMER = "customer"
SCOPE_REPORTING = "reporting"
SCOPE_DOMAIN = "domain"
SCOPE_UNLINKED = "unlinked_listings"
SCOPES = (SCOPE_CUSTOMER, SCOPE_REPORTING, SCOPE_DOMAIN, SCOPE_UNLINKED)

# Search configuration is deliberately not a Preview prerequisite: unavailable search must
# leave the other candidate sources usable.
REQUIRED_BY_SCOPE: dict[str, tuple[str, ...]] = {
    SCOPE_CUSTOMER: (ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS),
    SCOPE_REPORTING: (ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS),
    SCOPE_DOMAIN: (ts.KEY_TENANT_COUNTRY,),
    SCOPE_UNLINKED: (),
}

# Keys the plan fingerprint covers.
FINGERPRINT_KEYS = (
    ts.KEY_TENANT_COUNTRY,
    ts.KEY_TENANT_DOMAIN_ENDINGS,
    ts.KEY_DISCOVERY_SEARCH_PROVIDERS,
    ts.KEY_DISCOVERY_SEARCH_OPTIONS,
    ts.KEY_DISCOVERY_SEARXNG_URL,
    ts.KEY_DISCOVERY_EXCLUDED_DOMAINS,
    ts.KEY_DISCOVERY_BROWSER_FALLBACK,
)


@dataclass(frozen=True)
class DiscoverySettings:
    country: dict[str, str] | None = None
    domain_endings: list[str] = field(default_factory=list)
    search_providers: list[str] = field(default_factory=list)
    searxng_url: str | None = None
    excluded_domains: list[str] = field(default_factory=list)
    browser_fallback_enabled: bool = False
    # The keys a customer-scope Discover needs and the tenant has not set.
    missing: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    search_options: dict[str, Any] | None = None

    @property
    def country_code(self) -> str | None:
        return self.country["code"] if self.country else None

    @property
    def country_name(self) -> str | None:
        return self.country["name"] if self.country else None

    def missing_for(self, scope: str) -> list[str]:
        needed = REQUIRED_BY_SCOPE.get(scope, ())
        return [key for key in self.missing_all() if key in needed]

    def missing_all(self) -> list[str]:
        out: list[str] = []
        if self.country is None:
            out.append(ts.KEY_TENANT_COUNTRY)
        if not self.domain_endings:
            out.append(ts.KEY_TENANT_DOMAIN_ENDINGS)
        return out

    def fingerprint(self) -> str:
        """sha256 of the discovery keys, so Apply can tell settings changed after Preview."""
        payload = {key: self.raw.get(key) for key in FINGERPRINT_KEYS}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def public(self) -> dict[str, Any]:
        """The part shown in a Preview result."""
        return {
            "country": dict(self.country) if self.country else None,
            "domain_endings": list(self.domain_endings),
            "search_providers": list(self.search_providers),
            "search_options": dict(self.search_options) if self.search_options else None,
        }


def _clean(key: str, value: Any) -> Any | None:
    validator = ts.SETTING_VALIDATORS.get(key)
    if validator is None or value is None:
        return None
    try:
        return validator(value)
    except ValueError:
        return None


def settings_from_values(values: dict[str, Any]) -> DiscoverySettings:
    """Build settings from a ``{key: stored value}`` mapping."""
    country = _clean(ts.KEY_TENANT_COUNTRY, values.get(ts.KEY_TENANT_COUNTRY))
    endings = _clean(ts.KEY_TENANT_DOMAIN_ENDINGS, values.get(ts.KEY_TENANT_DOMAIN_ENDINGS)) or []
    providers = (
        _clean(ts.KEY_DISCOVERY_SEARCH_PROVIDERS, values.get(ts.KEY_DISCOVERY_SEARCH_PROVIDERS))
        or []
    )
    search_options = _clean(
        ts.KEY_DISCOVERY_SEARCH_OPTIONS, values.get(ts.KEY_DISCOVERY_SEARCH_OPTIONS)
    )
    searxng_url = _clean(ts.KEY_DISCOVERY_SEARXNG_URL, values.get(ts.KEY_DISCOVERY_SEARXNG_URL))
    if "searxng" in providers and not searxng_url:
        providers = [provider for provider in providers if provider != "searxng"]
    excluded = (
        _clean(ts.KEY_DISCOVERY_EXCLUDED_DOMAINS, values.get(ts.KEY_DISCOVERY_EXCLUDED_DOMAINS))
        or []
    )
    fallback = _clean(
        ts.KEY_DISCOVERY_BROWSER_FALLBACK, values.get(ts.KEY_DISCOVERY_BROWSER_FALLBACK)
    )
    cleaned_raw = {
        ts.KEY_TENANT_COUNTRY: country,
        ts.KEY_TENANT_DOMAIN_ENDINGS: endings or None,
        ts.KEY_DISCOVERY_SEARCH_PROVIDERS: providers or None,
        ts.KEY_DISCOVERY_SEARCH_OPTIONS: search_options,
        ts.KEY_DISCOVERY_SEARXNG_URL: searxng_url,
        ts.KEY_DISCOVERY_EXCLUDED_DOMAINS: excluded or None,
        ts.KEY_DISCOVERY_BROWSER_FALLBACK: fallback,
    }
    result = DiscoverySettings(
        country=country,
        domain_endings=list(endings),
        search_providers=list(providers),
        search_options=search_options,
        searxng_url=searxng_url,
        excluded_domains=list(excluded),
        browser_fallback_enabled=bool(fallback),
        raw=cleaned_raw,
    )
    return replace(result, missing=result.missing_all())


def load_discovery_settings(session: Session, tenant_id: str) -> DiscoverySettings:
    """The tenant's discovery settings."""
    return settings_from_values(ts.list_settings(session, tenant_id))
