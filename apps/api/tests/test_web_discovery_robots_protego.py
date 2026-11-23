"""Protego adapter compatibility and documented differences from the S1 parser."""

from app.services.listing_capture.web_discovery.robots import RobotsRules, parse_robots


def test_legacy_rule_list_cache_is_enforced_by_protego():
    rules = RobotsRules.from_dict(
        {
            "mode": "parsed",
            "rules": [[False, "/private/*"], [True, "/private/open/"]],
            "crawl_delay": 7,
            "sitemaps": ["https://shop.example.test/sitemap.xml"],
        }
    )
    assert not rules.allowed("/private/closed")
    assert rules.allowed("/private/open/item")
    assert rules.spacing_floor() == 7
    restored = RobotsRules.from_dict(rules.to_dict())
    assert not restored.allowed("/private/closed")
    assert restored.allowed("/private/open/item")


def test_new_source_text_cache_round_trip_and_merged_star_groups():
    rules = parse_robots(
        "User-agent: other\nDisallow: /\n"
        "User-agent: *\nDisallow: /one\n"
        "User-agent: *\nDisallow: /two\nAllow: /two/open\n"
        "Sitemap: https://shop.example.test/sitemap.xml\n"
    )
    assert rules.allowed("/")
    assert not rules.allowed("/one") and not rules.allowed("/two/closed")
    assert rules.allowed("/two/open")
    encoded = rules.to_dict()
    assert isinstance(encoded["robots_txt"], str)
    restored = RobotsRules.from_dict(encoded)
    assert not restored.allowed("/one")
    assert not restored.allowed("/two/closed")
    assert restored.sitemaps == ["https://shop.example.test/sitemap.xml"]


def test_protego_uses_last_valid_crawl_delay_instead_of_the_s1_maximum():
    # Documented migration difference: Protego's setter uses the last valid value.
    rules = parse_robots("User-agent: *\nCrawl-delay: 12\nCrawl-delay: 3\nCrawl-delay: bad\n")
    assert rules.crawl_delay == 3 and rules.spacing_floor() == 3


def test_protego_normalizes_percent_encoded_unreserved_characters():
    # Documented library difference: the old regex matcher compared these literally.
    rules = parse_robots("User-agent: *\nDisallow: /blocked\n")
    assert not rules.allowed("/%62locked")
    assert not RobotsRules.from_dict(rules.to_dict()).allowed("/%62locked")


def test_allowing_index_html_also_allows_the_directory_in_protego():
    # Protego's documented matcher behavior for an index.html Allow rule.
    rules = parse_robots("User-agent: *\nDisallow: /folder/\nAllow: /folder/index.html\n")
    assert rules.allowed("/folder/")
    assert rules.allowed("/folder/index.html")
    assert not rules.allowed("/folder/closed")
