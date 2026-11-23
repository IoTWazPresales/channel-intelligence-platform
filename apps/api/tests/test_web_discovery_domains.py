"""Offline PSL parsing, tenant endings and candidate host extraction."""

import requests
from app.services.listing_capture.web_discovery import candidates, scoring
from tldextract import TLDExtract


def test_psl_and_candidate_hosts_need_no_network_or_cache(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Suffix parsing must remain offline")

    monkeypatch.setattr(requests.sessions.Session, "request", refuse)
    # Start cold, rather than allowing a previous test to warm the extractor.
    monkeypatch.setattr(
        scoring,
        "_DOMAIN_EXTRACTOR",
        TLDExtract(
            suffix_list_urls=(),
            cache_dir=None,
        ),
    )
    scoring._extractor_for_endings.cache_clear()
    monkeypatch.setenv("TLDEXTRACT_CACHE", str(tmp_path / "unused"))
    assert scoring.domain_key("catalogue.alpha-gadgets.co.uk", []) == "alphagadgets"
    assert scoring.domain_key("store.alpha-gadgets.com.au", []) == "alphagadgets"
    assert candidates._host_of("https://WWW.Store.Alpha.CO.UK/path?q=x") == "store.alpha.co.uk"
    assert candidates._host_of("store.alpha.co.uk/path") == "store.alpha.co.uk"
    assert candidates._host_of(None) == ""
    assert not list(tmp_path.iterdir())


def test_synthetic_and_unknown_endings_keep_s1_behavior():
    assert scoring.domain_key("shop.alpha.example.test", [".example.test"]) == "alpha"
    assert scoring.domain_key("alpha.co.zz", [".zz", ".co.zz"]) == "alpha"
    assert scoring.domain_key("alpha.co.zz", [".zz"]) == "co"
    assert scoring.domain_key("alpha.unknown", []) == "alpha"


def test_psl_never_supplies_country_evidence_without_tenant_endings():
    country = {"code": "GB", "name": "Test Country"}
    assert scoring.domain_key("alpha.co.uk", []) == "alpha"
    assert scoring.matched_ending("alpha.co.uk", []) is None
    assert scoring.country_match("alpha.co.uk", [], country, None)["value"] is False
    configured = {"code": "ZZ", "name": "Testland"}
    assert scoring.country_match("alpha.co.zz", [".co.zz"], configured, None) == {
        "value": True,
        "how": "cctld",
    }
