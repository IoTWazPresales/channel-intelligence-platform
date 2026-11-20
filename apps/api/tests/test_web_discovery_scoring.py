"""Scoring and the auto-accept decision. Pure: no database, no network. Synthetic names and hosts."""

from __future__ import annotations

import itertools
import json

import pytest

from app.services.listing_capture.web_discovery import scoring
from app.services.listing_capture.web_discovery.homepage import HomeSignals, parse_home
from tests.web_discovery_support import COUNTRY, ENDINGS, fixture_text

NAME = "Alpha Gadgets (Pty) Ltd"
HIT = {"product_id": 9, "product_label": "Widget One", "query": '"WID-1" Testland', "rank": 1}


def _evidence(
    host: str,
    *,
    name: str = NAME,
    home: HomeSignals | None = None,
    hits: list | None = None,
    status: int = 200,
    robots: str = "allowed",
    sources: set[str] | None = None,
) -> dict:
    return scoring.build_evidence(
        host=host,
        customer_name=name,
        sources=sources or {scoring.SOURCE_GUESS},
        endings=ENDINGS,
        country=COUNTRY,
        home=home if home is not None else HomeSignals(title="Home"),
        http_status=status,
        final_url=f"https://{host}/",
        robots=robots,
        product_hits=hits or [],
    )


# --------------------------------------------------------------------------- name keys


def test_customer_keys_strip_legal_suffixes_and_punctuation() -> None:
    assert scoring.customer_keys("Alpha Gadgets (Pty) Ltd") == ["alphagadgets"]
    assert scoring.customer_keys("  ALPHA   gadgets  ") == ["alphagadgets"]
    assert scoring.customer_keys("") == []
    assert scoring.customer_keys(None) == []


def test_customer_keys_include_the_trade_name_after_trading_as() -> None:
    keys = scoring.customer_keys("Gamma Supplies Ltd t/a Delta Shop")
    assert "deltashop" in keys
    assert all(key.isalnum() and key == key.lower() for key in keys)


def test_domain_key_strips_www_the_longest_ending_and_hyphens() -> None:
    assert scoring.domain_key("www.alpha-gadgets.example.test", ENDINGS) == "alphagadgets"
    assert scoring.domain_key("ALPHAGADGETS.ZZ", ENDINGS) == "alphagadgets"
    # No configured ending: the last label is dropped.
    assert scoring.domain_key("alphagadgets.unknown", ENDINGS) == "alphagadgets"
    # The longest configured ending wins over a shorter one.
    assert scoring.domain_key("alpha.co.zz", [".zz", ".co.zz"]) == "alpha"
    assert scoring.domain_key("alpha.co.zz", [".zz"]) == "co"


def test_name_exact_is_string_equality_only() -> None:
    assert scoring.name_match("alphagadgets.zz", NAME, ENDINGS)["exact"] is True
    assert scoring.name_match("www.alpha-gadgets.zz", NAME, ENDINGS)["exact"] is True
    # One letter off is not a match, in either direction. No fuzzy scoring anywhere.
    assert scoring.name_match("alphagadget.zz", NAME, ENDINGS)["exact"] is False
    assert scoring.name_match("alphagadgetz.zz", NAME, ENDINGS)["exact"] is False
    assert scoring.name_match("alphagadgets2.zz", NAME, ENDINGS)["exact"] is False
    assert scoring.name_match("alphagadgets.zz", "", ENDINGS)["exact"] is False


def test_trade_name_matches_the_domain() -> None:
    assert scoring.name_match("deltashop.zz", "Gamma Supplies Ltd t/a Delta Shop", ENDINGS)["exact"] is True


def test_matched_ending_needs_a_name_part_in_front_of_it() -> None:
    assert scoring.matched_ending("alphagadgets.example.test", ENDINGS) == ".example.test"
    assert scoring.matched_ending("alphagadgets.zz", ENDINGS) == ".zz"
    assert scoring.matched_ending("alphagadgets.other", ENDINGS) is None
    assert scoring.matched_ending(".zz", ENDINGS) is None


# --------------------------------------------------------------------------- country


def test_country_from_the_domain_ending_needs_a_two_letter_ending_equal_to_the_code() -> None:
    assert scoring.country_match("alphagadgets.zz", ENDINGS, COUNTRY, None) == {"value": True, "how": "cctld"}
    # ".example.test" ends in a long label: not a country ending.
    assert scoring.country_match("alphagadgets.example.test", ENDINGS, COUNTRY, None)["value"] is False
    # A two-letter ending for another country does not match.
    other = {"code": "YY", "name": "Otherland"}
    assert scoring.country_match("alphagadgets.zz", ENDINGS, other, None)["value"] is False


def test_country_from_the_page_address() -> None:
    home = parse_home(fixture_text("home_org_jsonld.html"))
    assert scoring.country_match("alphagadgets.example.test", ENDINGS, COUNTRY, home) == {
        "value": True,
        "how": "address_country",
    }
    wrong = HomeSignals(address_countries=["Elsewhere"])
    assert scoring.country_match("alphagadgets.example.test", ENDINGS, COUNTRY, wrong)["value"] is False


def test_country_from_the_page_locale_region() -> None:
    home = parse_home(fixture_text("home_locale.html"))
    assert scoring.country_match("alphagadgets.example.test", ENDINGS, COUNTRY, home) == {
        "value": True,
        "how": "page_locale",
    }
    # A bare language is not a region.
    assert scoring.country_match("x.example.test", ENDINGS, COUNTRY, HomeSignals(html_lang="en"))["value"] is False


def test_country_not_set_is_never_a_match() -> None:
    assert scoring.country_match("alphagadgets.zz", ENDINGS, None, None) == {"value": False, "how": None}


# --------------------------------------------------------------------------- home page


def test_homepage_match_from_the_organisation_name() -> None:
    home = parse_home(fixture_text("home_org_jsonld.html"))
    assert scoring.homepage_match(home, ["alphagadgets"]) == {"match": True, "via": "org_name"}


def test_homepage_match_from_og_site_name() -> None:
    home = parse_home(fixture_text("home_locale.html"))
    assert scoring.homepage_match(home, ["alphagadgets"]) == {"match": True, "via": "og_site_name"}


def test_homepage_match_from_a_title_segment() -> None:
    home = parse_home(fixture_text("home_title_segments.html"))
    assert scoring.homepage_match(home, ["alphagadgets"]) == {"match": True, "via": "title"}
    assert scoring.homepage_match(home, ["somethingelse"])["match"] is False


def test_a_hyphen_without_spaces_does_not_split_a_title() -> None:
    home = HomeSignals(title="Alpha e-shop")
    assert scoring.homepage_match(home, ["alpha"])["match"] is False
    assert scoring.homepage_match(HomeSignals(title="Welcome - Alpha"), ["alpha"])["match"] is True


def test_homepage_match_without_a_page_or_keys() -> None:
    assert scoring.homepage_match(None, ["alpha"])["match"] is False
    assert scoring.homepage_match(HomeSignals(title="Alpha"), [])["match"] is False


# --------------------------------------------------------------------------- the decision


def _combination(name_ok: bool, country_ok: bool, product_ok: bool) -> dict:
    key = "alphagadgets" if name_ok else "othername"
    ending = ".zz" if country_ok else ".example.test"
    return _evidence(f"{key}{ending}", hits=[dict(HIT)] if product_ok else [])


@pytest.mark.parametrize(("name_ok", "country_ok", "product_ok"), list(itertools.product([True, False], repeat=3)))
def test_auto_accept_truth_table(name_ok: bool, country_ok: bool, product_ok: bool) -> None:
    evidence = _combination(name_ok, country_ok, product_ok)
    assert evidence["name_match"]["exact"] is name_ok
    assert evidence["country_match"]["value"] is country_ok
    expected = scoring.OUTCOME_AUTO if (name_ok and country_ok and product_ok) else scoring.OUTCOME_QUEUE
    assert scoring.decide(evidence) == expected


def test_auto_accept_needs_the_home_page_to_load_and_robots_to_allow() -> None:
    assert scoring.decide(_evidence("alphagadgets.zz", hits=[dict(HIT)])) == scoring.OUTCOME_AUTO
    assert scoring.decide(_evidence("alphagadgets.zz", hits=[dict(HIT)], status=404)) == scoring.OUTCOME_QUEUE
    assert scoring.decide(_evidence("alphagadgets.zz", hits=[dict(HIT)], status=0)) == scoring.OUTCOME_QUEUE
    assert scoring.decide(_evidence("alphagadgets.zz", hits=[dict(HIT)], robots="disallowed")) == scoring.OUTCOME_QUEUE
    assert scoring.decide(_evidence("alphagadgets.zz", hits=[dict(HIT)], robots="unknown")) == scoring.OUTCOME_QUEUE


def test_country_from_the_page_can_stand_in_for_the_ending() -> None:
    home = parse_home(fixture_text("home_org_jsonld.html"))
    evidence = _evidence("alphagadgets.example.test", home=home, hits=[dict(HIT)])
    assert evidence["country_match"]["how"] == "address_country"
    assert scoring.decide(evidence) == scoring.OUTCOME_AUTO


def test_a_rejected_site_is_never_auto_accepted() -> None:
    evidence = _evidence("alphagadgets.zz", hits=[dict(HIT)])
    assert scoring.decide(evidence, rejected=True) == scoring.OUTCOME_REJECTED
    assert scoring.decide(evidence, rejected=True, user_entered=True) == scoring.OUTCOME_REJECTED


def test_a_user_entered_domain_is_confirmed_by_the_user_even_without_evidence() -> None:
    evidence = _evidence("nothing-alike.example.test")
    assert scoring.decide(evidence) == scoring.OUTCOME_QUEUE
    assert scoring.decide(evidence, user_entered=True) == scoring.OUTCOME_USER


def test_already_monitored_is_reported_as_such() -> None:
    evidence = _evidence("alphagadgets.zz", hits=[dict(HIT)])
    assert scoring.decide(evidence, already_monitored=True) == scoring.OUTCOME_MONITORED


def test_the_decision_ignores_any_outcome_written_into_the_evidence() -> None:
    evidence = _evidence("othername.example.test")
    evidence["outcome"] = scoring.OUTCOME_AUTO
    evidence["auto_accept"] = True
    assert scoring.decide(evidence) == scoring.OUTCOME_QUEUE


# --------------------------------------------------------------------------- evidence and ranking


def test_evidence_is_json_and_never_holds_an_email_address() -> None:
    evidence = _evidence(
        "alphagadgets.zz",
        home=parse_home(fixture_text("home_org_jsonld.html")),
        hits=[dict(HIT)],
        sources={scoring.SOURCE_EMAIL, scoring.SOURCE_GUESS},
    )
    blob = json.dumps(evidence)
    assert "@" not in blob
    assert evidence["sources"] == ["email", "guess"]
    assert evidence["ending_match"] == ".zz"
    assert evidence["homepage"]["org_name"] == "Alpha Gadgets"
    assert "home_signals" in evidence


def test_rank_key_orders_name_country_hits_homepage_file_email() -> None:
    strong = _evidence("alphagadgets.zz", hits=[dict(HIT)], sources={scoring.SOURCE_ON_FILE})
    name_only = _evidence("alphagadgets.example.test")
    country_only = _evidence("other.zz")
    nothing = _evidence("other.example.test", sources={scoring.SOURCE_EMAIL})
    ranked = sorted([nothing, country_only, name_only, strong], key=scoring.rank_key)
    assert ranked == [strong, name_only, country_only, nothing]
    two_hits = _evidence("alphagadgets.example.test", hits=[dict(HIT), dict(HIT, rank=2)])
    one_hit = _evidence("alphagadgets.example.test", hits=[dict(HIT)])
    assert scoring.rank_key(two_hits) < scoring.rank_key(one_hit)


def test_normalize_host() -> None:
    assert scoring.normalize_host(" WWW.Alpha.ZZ. ") == "alpha.zz"
    assert scoring.normalize_host("") == ""
