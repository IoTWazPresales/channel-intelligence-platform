"""Fictional listing sites for listing-capture tests. No real site, retailer or seller names."""

from __future__ import annotations

from app.services.listing_capture.adapters import SiteConfig, SiteSeller

HTML_SITE_KEY = "shop-a"
REST_SITE_KEY = "market-b"
REST_HOST = "https://market-b.example.test"
REST_API = "https://api.market-b.example.test"


def html_site(key: str = HTML_SITE_KEY, *, rate: float | None = 2.0, sellers=(), first_party: str | None = "Shop A") -> SiteConfig:
    return SiteConfig(
        site_key=key,
        display_name=key.replace("-", " ").title(),
        adapter_key="html_page",
        first_party_seller=first_party,
        rate_limit_seconds=rate,
        sellers=tuple(sellers),
    )


def rest_site(key: str = REST_SITE_KEY, *, rate: float | None = 2.0, sellers=(), search: bool = True) -> SiteConfig:
    return SiteConfig(
        site_key=key,
        display_name="Market B",
        adapter_key="rest_buybox_json",
        product_url_pattern=f"{REST_HOST}/x/ID{{page_id}}",
        page_id_pattern=r"ID(\d{5,12})",
        details_url_pattern=f"{REST_API}/rest/details/ID{{page_id}}?platform=desktop",
        search_url_pattern=f"{REST_API}/rest/search?q={{query}}" if search else None,
        first_party_seller="Market B Retail",
        rate_limit_seconds=rate,
        sellers=tuple(sellers),
    )


def unconfigured_site(key: str = "shop-c") -> SiteConfig:
    return SiteConfig(site_key=key, display_name=key)


def own_seller(customer_id: int, *names: str, ids: tuple[str, ...] = ()) -> SiteSeller:
    return SiteSeller(customer_id=customer_id, names=tuple(names), ids=ids)
