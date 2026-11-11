"""Page readers chosen by a site's configured ``adapter_key``.

A site (``listing_site`` row) is data: its key, display name, link patterns, the seller name it
shows for its own stock, request spacing and which reader parses its pages. The readers here are
code and name no site. Each reader module exposes:

- ``REQUIRED_FIELDS``: site columns that must be filled before the reader can fetch.
- ``READS_STORED_URL``: True when the reader fetches the stored listing URL itself (so a
  successful parse verifies that URL).
- ``request_headers(site)``: extra request headers.
- ``fetch(site, *, url, http_get, external_id, ean, known_page_id)``: ``(status, body, flags)``.
- ``parse(body, *, site, preferred_sku, parser_version)``: ``ParseResult``.
- ``link_dead(fetch_flags, status)``: the stored link no longer opens the product.
- ``verified_url(site, fetch_flags, parse_flags)``: the product link to write back, or None.
- ``quality_fields(text, *, site)``: page fields the quality checks read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any


def normalize_seller(value: Any) -> str:
    """Seller names compare case-insensitively with whitespace collapsed (exact, never substring)."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def seller_role_label(is_own_seller: bool | None) -> str | None:
    """Own when this seller is the customer's. Competition when another seller holds the buy box."""
    if is_own_seller is True:
        return "Own"
    if is_own_seller is False:
        return "Competition"
    return None


@dataclass(frozen=True)
class SiteSeller:
    customer_id: int
    names: tuple[str, ...] = ()
    ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SiteConfig:
    site_key: str
    display_name: str
    adapter_key: str | None = None
    product_url_pattern: str | None = None
    page_id_pattern: str | None = None
    search_url_pattern: str | None = None
    details_url_pattern: str | None = None
    first_party_seller: str | None = None
    rate_limit_seconds: float | None = None
    is_active: bool = True
    id: int | None = None
    tenant_id: str = "default"
    sellers: tuple[SiteSeller, ...] = field(default_factory=tuple)

    def own_seller(self, customer_id: int | None) -> SiteSeller | None:
        if customer_id is None:
            return None
        for seller in self.sellers:
            if int(seller.customer_id) == int(customer_id):
                return seller
        return None

    def is_own_seller(
        self,
        customer_id: int | None,
        *,
        name: str | None = None,
        seller_id: str | None = None,
    ) -> bool | None:
        """True/False when the customer's seller identity on this site is configured, else None."""
        own = self.own_seller(customer_id)
        if own is None or (not own.names and not own.ids):
            return None
        sid = str(seller_id or "").strip()
        if sid and sid in {str(i).strip() for i in own.ids}:
            return True
        key = normalize_seller(name)
        return bool(key) and key in {normalize_seller(n) for n in own.names}


def _registry() -> dict[str, ModuleType]:
    from app.services.listing_capture.adapters import html_page, rest_buybox

    return {html_page.ADAPTER_KEY: html_page, rest_buybox.ADAPTER_KEY: rest_buybox}


def adapter_keys() -> tuple[str, ...]:
    return tuple(sorted(_registry()))


def adapter_module(adapter_key: str | None) -> ModuleType | None:
    if not adapter_key:
        return None
    return _registry().get(str(adapter_key).strip())


def missing_fields(site: SiteConfig | None) -> list[str]:
    """Site columns still empty before pages can be read (``[]`` = configured)."""
    if site is None:
        return ["site"]
    module = adapter_module(site.adapter_key)
    if module is None:
        return ["adapter_key"]
    return [name for name in module.REQUIRED_FIELDS if not str(getattr(site, name) or "").strip()]


def configured_adapter(site: SiteConfig | None) -> ModuleType | None:
    """The site's reader when the site is active and every required field is filled."""
    if site is None or not site.is_active or missing_fields(site):
        return None
    return adapter_module(site.adapter_key)
