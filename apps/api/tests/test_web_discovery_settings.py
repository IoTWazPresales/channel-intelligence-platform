"""Tenant settings for Discovery V2: validators, the loader, the fingerprint. No database."""

from __future__ import annotations

import pytest

from app.services import tenant_settings as ts
from app.services.listing_capture.web_discovery import settings as wd_settings
from tests.web_discovery_support import COUNTRY, ENDINGS, make_settings, settings_values


def test_all_keys_are_registered() -> None:
    for key in (
        ts.KEY_TENANT_COUNTRY,
        ts.KEY_TENANT_DOMAIN_ENDINGS,
        ts.KEY_DISCOVERY_SEARCH_PROVIDERS,
        ts.KEY_DISCOVERY_SEARXNG_URL,
        ts.KEY_DISCOVERY_EXCLUDED_DOMAINS,
        ts.KEY_DISCOVERY_BROWSER_FALLBACK,
        ts.KEY_DISCOVERY_SCHEDULE,
    ):
        assert key in ts.SETTING_VALIDATORS


def test_country_needs_code_and_name() -> None:
    assert ts._as_country({"code": "ZZ", "name": " Testland "}) == {"code": "ZZ", "name": "Testland"}
    for bad in ({"code": "zz", "name": "Testland"}, {"code": "ZZZ", "name": "Testland"}, {"code": "ZZ"},
                {"code": "ZZ", "name": ""}, {"code": "ZZ", "name": "x" * 65}, "ZZ", None,
                {"code": "ZZ", "name": "Testland", "extra": 1}):
        with pytest.raises(ValueError):
            ts._as_country(bad)


def test_domain_endings_are_lowered_deduplicated_and_keep_order() -> None:
    assert ts._as_domain_endings([".Example.Test", ".zz", ".example.test"]) == [".example.test", ".zz"]
    for bad in ([], ["example.test"], [".exa mple"], [".a."], ["."], [5], "x", [f".e{i}" for i in range(21)]):
        with pytest.raises(ValueError):
            ts._as_domain_endings(bad)


def test_search_providers_are_a_subset_in_order() -> None:
    assert ts._as_search_providers(["ddg_lite", "ddg_html", "ddg_lite"]) == ["ddg_lite", "ddg_html"]
    assert ts._as_search_providers([]) == []
    with pytest.raises(ValueError):
        ts._as_search_providers(["bing"])
    with pytest.raises(ValueError):
        ts._as_search_providers("ddg_html")


def test_searxng_url_must_be_https_without_a_query() -> None:
    assert ts._as_https_base_url("https://search.example.test/") == "https://search.example.test"
    for bad in ("http://search.example.test", "https://search.example.test/?q=1", "search.example.test", 5,
                "https://user@search.example.test"):
        with pytest.raises(ValueError):
            ts._as_https_base_url(bad)


def test_excluded_domains_use_the_onboarding_host_check() -> None:
    assert ts._as_excluded_domains(["Shop.Example.Test", "shop.example.test"]) == ["shop.example.test"]
    with pytest.raises(ValueError):
        ts._as_excluded_domains(["https://shop.example.test"])
    with pytest.raises(ValueError):
        ts._as_excluded_domains([f"h{i}.example.test" for i in range(201)])


def test_searxng_in_providers_needs_the_url_first(monkeypatch) -> None:
    monkeypatch.setattr(ts, "get_setting", lambda *_a, **_k: None)
    with pytest.raises(ValueError, match="searxng_url"):
        ts.CROSS_CHECKS[ts.KEY_DISCOVERY_SEARCH_PROVIDERS](None, "t", ["searxng"])
    ts.CROSS_CHECKS[ts.KEY_DISCOVERY_SEARCH_PROVIDERS](None, "t", ["ddg_html"])
    monkeypatch.setattr(ts, "get_setting", lambda *_a, **_k: "https://search.example.test")
    ts.CROSS_CHECKS[ts.KEY_DISCOVERY_SEARCH_PROVIDERS](None, "t", ["searxng"])


def test_nothing_is_set_by_default() -> None:
    loaded = wd_settings.settings_from_values({})
    assert loaded.country is None and loaded.domain_endings == [] and loaded.search_providers == []
    assert loaded.excluded_domains == [] and loaded.browser_fallback_enabled is False
    assert loaded.missing == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]


def test_missing_by_scope() -> None:
    empty = wd_settings.settings_from_values({})
    assert empty.missing_for("customer") == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]
    assert empty.missing_for("reporting") == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]
    assert empty.missing_for("domain") == [ts.KEY_TENANT_COUNTRY]
    assert empty.missing_for("unlinked_listings") == []
    only_country = wd_settings.settings_from_values({ts.KEY_TENANT_COUNTRY: COUNTRY})
    assert only_country.missing_for("customer") == [ts.KEY_TENANT_DOMAIN_ENDINGS]
    assert only_country.missing_for("domain") == []
    assert make_settings().missing == []


def test_a_stored_value_that_no_longer_validates_reads_as_missing() -> None:
    loaded = wd_settings.settings_from_values(
        {ts.KEY_TENANT_COUNTRY: {"code": "bad", "name": "x"}, ts.KEY_TENANT_DOMAIN_ENDINGS: ["nodot"]}
    )
    assert loaded.country is None and loaded.domain_endings == []
    assert loaded.missing == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]


def test_searxng_without_a_url_is_dropped_from_the_providers() -> None:
    loaded = make_settings(**{ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["searxng", "ddg_html"]})
    assert loaded.search_providers == ["ddg_html"]
    with_url = make_settings(
        **{ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["searxng"], ts.KEY_DISCOVERY_SEARXNG_URL: "https://s.example.test"}
    )
    assert with_url.search_providers == ["searxng"] and with_url.searxng_url == "https://s.example.test"


def test_fingerprint_is_stable_and_changes_with_any_discovery_key() -> None:
    base = make_settings()
    assert base.fingerprint() == make_settings().fingerprint()
    assert make_settings(**{ts.KEY_TENANT_DOMAIN_ENDINGS: [".zz"]}).fingerprint() != base.fingerprint()
    assert make_settings(**{ts.KEY_DISCOVERY_EXCLUDED_DOMAINS: ["x.example.test"]}).fingerprint() != base.fingerprint()
    assert make_settings(**{ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["ddg_lite"]}).fingerprint() != base.fingerprint()
    assert make_settings(**{ts.KEY_TENANT_COUNTRY: {"code": "YY", "name": "Other"}}).fingerprint() != base.fingerprint()


def test_load_reads_the_tenant_rows(monkeypatch) -> None:
    monkeypatch.setattr(ts, "list_settings", lambda _s, tenant: settings_values() if tenant == "t1" else {})
    assert wd_settings.load_discovery_settings(None, "t1").domain_endings == ENDINGS
    assert wd_settings.load_discovery_settings(None, "t2").missing != []
