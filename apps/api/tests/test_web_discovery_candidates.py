"""Candidate sites for a customer: sources, exclusions, product choice, guesses, home-page loading.

Pure: ``assemble_candidates`` and ``load_homepages`` take fakes, so no database or network is used.
"""

from __future__ import annotations

import json

from app.services import tenant_settings as ts
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery.polite import Fetched
from app.services.listing_capture.web_discovery.scoring import (
    OUTCOME_DROPPED,
    OUTCOME_MONITORED,
    SOURCE_EMAIL,
    SOURCE_GUESS,
    SOURCE_NAME_SEARCH,
    SOURCE_PRODUCT_SEARCH,
    SOURCE_USER,
)
from tests.web_discovery_support import (
    FakeGetter,
    FakeSearch,
    home_page,
    make_settings,
)

NAME = "Alpha Gadgets (Pty) Ltd"


def _ctx(**over) -> cand.CustomerContext:
    values = {"customer_id": 1, "name": NAME}
    values.update(over)
    return cand.CustomerContext(**values)


def _no_dns(_host: str) -> list[str]:
    return []


def _by_host(items: list[cand.Candidate]) -> dict[str, cand.Candidate]:
    return {item.host: item for item in items}


# --------------------------------------------------------------------------- products


def _product(pid: int, *, sales=None, part=None, name="Plain name", source=0) -> cand.ProductInfo:
    return cand.ProductInfo(
        id=pid, sales_model_name=sales, part_number=part, name=name, source_index=source
    )


def test_products_are_chosen_by_source_then_sales_model_then_id() -> None:
    products = [
        _product(30, sales=None, source=0),
        _product(20, sales="Model B", source=0),
        _product(10, sales="Model A", source=0),
        _product(5, sales="Model Z", source=1),
        _product(20, sales="Model B", source=1),  # duplicate id: the first one wins
    ]
    chosen = cand.choose_products(products)
    assert [p.id for p in chosen] == [10, 20, 30]
    assert len(cand.choose_products(products + [_product(1, source=0)])) == 3


def test_a_later_source_is_used_when_the_first_has_few_products() -> None:
    chosen = cand.choose_products(
        [_product(2, source=0), _product(9, source=2), _product(7, source=1), _product(8, source=3)]
    )
    assert [p.id for p in chosen] == [2, 7, 9]


def test_product_queries_search_model_part_and_description() -> None:
    # Requirement: free search uses the sales model, the part code and the
    # description, each on its own.
    assert cand.product_queries(
        _product(1, sales="Model A", part="PN-1", name="A long description"), "Testland"
    ) == [
        '"Model A" Testland',
        '"PN-1" Testland',
        "A long description Testland",
    ]
    long_name = "n" * 120
    assert cand.product_queries(_product(1, name=long_name), "Testland") == [f"{'n' * 80} Testland"]
    assert cand.name_query("  Alpha Gadgets ", "Testland") == '"Alpha Gadgets" Testland'


# --------------------------------------------------------------------------- email


def test_a_domain_shared_by_two_customers_is_not_proposed() -> None:
    ctx = _ctx(
        contact_domains=["mailhost.example.test", "alphagadgets.example.test"],
        shared_contact_domains={"mailhost.example.test"},
    )
    found = cand.assemble_candidates(ctx, make_settings(), search=None, resolve=_no_dns)
    hosts = _by_host(found)
    assert set(hosts) == {"alphagadgets.example.test"}
    assert hosts["alphagadgets.example.test"].sources == {SOURCE_EMAIL}
    assert "@" not in json.dumps([c.extra for c in found])


# --------------------------------------------------------------------------- on file


def test_on_file_sources_and_already_monitored_sites() -> None:
    ctx = _ctx(
        seed_host="seeded.example.test",
        confirmed_hosts=["confirmed.example.test"],
        listing_hosts=["listed.example.test", "other-customer.example.test"],
        own_site_hosts={"listed.example.test": "listed-key"},
        other_site_hosts={"other-customer.example.test": "other-key"},
    )
    hosts = _by_host(cand.assemble_candidates(ctx, make_settings(), search=None, resolve=_no_dns))
    # Requirement: listing_seed is not a source, so a seed host is not a candidate.
    assert "seeded.example.test" not in hosts
    assert hosts["confirmed.example.test"].outcome_hint == OUTCOME_MONITORED
    assert hosts["listed.example.test"].outcome_hint == OUTCOME_MONITORED
    assert (
        hosts["listed.example.test"].gate_key == "listed-key"
    )  # the existing site's gate, so spacing is shared
    assert hosts["other-customer.example.test"].outcome_hint == OUTCOME_DROPPED
    assert hosts["other-customer.example.test"].drop_reason == cand.DROP_OTHER_CUSTOMER_SITE


def test_a_user_entered_domain_on_another_customers_site_is_not_dropped() -> None:
    ctx = _ctx(other_site_hosts={"shared.example.test": "other-key"})
    found = cand.assemble_candidates(
        ctx, make_settings(), search=None, resolve=_no_dns, user_domain="shared.example.test"
    )
    assert [(c.host, c.outcome_hint) for c in found] == [("shared.example.test", None)]


# --------------------------------------------------------------------------- search


def test_product_and_name_search_use_the_country_name_and_keep_three_hosts_per_query() -> None:
    search = FakeSearch(
        {
            '"Model A"': [
                "one.example.test",
                "two.example.test",
                "three.example.test",
                "four.example.test",
            ],
            '"Alpha': ["two.example.test", "five.example.test"],
        }
    )
    ctx = _ctx(products=[_product(10, sales="Model A")])
    hosts = _by_host(cand.assemble_candidates(ctx, make_settings(), search=search, resolve=_no_dns))
    assert search.queries == ['"Model A" Testland', "Plain name Testland", f'"{NAME}" Testland']
    assert "four.example.test" not in hosts
    assert hosts["one.example.test"].sources == {SOURCE_PRODUCT_SEARCH}
    assert hosts["one.example.test"].product_hits == [
        {"product_id": 10, "product_label": "Model A", "query": '"Model A" Testland', "rank": 1}
    ]
    assert hosts["two.example.test"].sources == {SOURCE_PRODUCT_SEARCH, SOURCE_NAME_SEARCH}
    assert hosts["five.example.test"].sources == {SOURCE_NAME_SEARCH}
    assert hosts["five.example.test"].product_hits == []


def test_at_most_three_products_are_searched_and_every_hit_names_its_product() -> None:
    search = FakeSearch({"Model": ["shop.example.test"]})
    ctx = _ctx(products=[_product(i, sales=f"Model {i}") for i in range(1, 6)])
    hosts = _by_host(cand.assemble_candidates(ctx, make_settings(), search=search, resolve=_no_dns))
    # Requirement: model and description are separate searches.
    # 3 products x 2, plus the customer name.
    assert len(search.queries) == 7
    assert sorted(hit["product_id"] for hit in hosts["shop.example.test"].product_hits) == [1, 2, 3]


def test_no_search_function_means_no_search_sources() -> None:
    ctx = _ctx(products=[_product(10, sales="Model A")])
    assert cand.assemble_candidates(ctx, make_settings(), search=None, resolve=_no_dns) == []


def test_no_products_adds_a_note_and_the_name_search_still_runs() -> None:
    search = FakeSearch({"Alpha": ["shop.example.test"]})
    notes: list[str] = []
    found = cand.assemble_candidates(
        _ctx(), make_settings(), search=search, resolve=_no_dns, notes=notes
    )
    assert notes == ["No products on record for this customer"]
    assert [c.sources for c in found] == [{SOURCE_NAME_SEARCH}]


def test_excluded_domains_engine_hosts_and_unusable_hosts_are_never_candidates() -> None:
    settings = make_settings(**{ts.KEY_DISCOVERY_EXCLUDED_DOMAINS: ["blocked.example.test"]})
    search = FakeSearch(
        {
            '"Model A"': [
                "blocked.example.test",
                "shop.blocked.example.test",
                "engine.example.test",
            ],
            '"Alpha': ["not a host", "fine.example.test"],
        }
    )
    found = cand.assemble_candidates(
        _ctx(products=[_product(10, sales="Model A")]),
        settings,
        search=search,
        resolve=_no_dns,
        engine_hosts=frozenset({"engine.example.test"}),
    )
    assert {c.host for c in found} == {"fine.example.test"}


def test_excluded_domains_also_remove_on_file_and_email_sources() -> None:
    settings = make_settings(**{ts.KEY_DISCOVERY_EXCLUDED_DOMAINS: ["blocked.example.test"]})
    ctx = _ctx(seed_host="blocked.example.test", contact_domains=["blocked.example.test"])
    assert cand.assemble_candidates(ctx, settings, search=None, resolve=_no_dns) == []


def test_www_is_stripped_and_hosts_are_deduplicated_across_sources() -> None:
    search = FakeSearch({"Alpha": ["www.shop.example.test"]})
    ctx = _ctx(contact_domains=["shop.example.test"])
    found = cand.assemble_candidates(ctx, make_settings(), search=search, resolve=_no_dns)
    assert [(c.host, c.sources) for c in found] == [
        ("shop.example.test", {SOURCE_EMAIL, SOURCE_NAME_SEARCH})
    ]


def test_resolve_is_never_called() -> None:
    # Requirement: free search only. DNS guesses from the customer name are not a source.
    asked: list[str] = []

    def resolve(host: str) -> list[str]:
        asked.append(host)
        return ["8.8.8.8"]

    found = cand.assemble_candidates(_ctx(), make_settings(), search=None, resolve=resolve)
    assert asked == []
    assert found == []


def test_the_user_domain_scope_skips_every_other_source() -> None:
    search = FakeSearch({"Alpha": ["shop.example.test"]})
    called: list[str] = []
    ctx = _ctx(
        seed_host="seeded.example.test",
        contact_domains=["mail.example.test"],
        products=[_product(1, sales="M")],
    )
    found = cand.assemble_candidates(
        ctx,
        make_settings(),
        search=search,
        resolve=lambda h: called.append(h) or ["8.8.8.8"],
        user_domain="typed.example.test",
    )
    assert [(c.host, c.sources) for c in found] == [("typed.example.test", {SOURCE_USER})]
    assert search.queries == [] and called == []


# --------------------------------------------------------------------------- home pages


def _fetched(
    url: str, status: int = 200, body: str | None = None, *, final: str | None = None, refused=None
) -> Fetched:
    return Fetched(
        status,
        body if body is not None else home_page("Alpha Gadgets"),
        final or url,
        refused=refused,
    )


def test_home_pages_load_through_the_getter_with_the_right_gate_keys() -> None:
    getter = FakeGetter(
        {
            "https://listed.example.test/": _fetched("https://listed.example.test/"),
            "https://new.example.test/": _fetched("https://new.example.test/"),
        }
    )
    items = [
        cand.Candidate(
            host="listed.example.test", gate_key="listed-key", outcome_hint=OUTCOME_MONITORED
        ),
        cand.Candidate(host="new.example.test"),
    ]
    loaded = cand.load_homepages(items, getter)
    assert getter.calls == [
        ("https://listed.example.test/", "listed-key"),
        ("https://new.example.test/", "host:new.example.test"),
    ]
    assert all(
        c.http_status == 200 and c.robots == "allowed" and c.home is not None for c in loaded
    )
    assert loaded[1].home.title == "Alpha Gadgets"


def test_unreachable_refused_and_non_200_candidates_are_dropped_with_a_reason() -> None:
    getter = FakeGetter(
        {
            "https://robots.example.test/": Fetched(
                0, "", "https://robots.example.test/", refused="robots"
            ),
            "https://paused.example.test/": Fetched(
                429, "", "https://paused.example.test/", refused="site_paused"
            ),
            "https://down.example.test/": Fetched(0, "", "https://down.example.test/"),
            "https://missing.example.test/": Fetched(404, "", "https://missing.example.test/"),
        }
    )
    items = [
        cand.Candidate(host=h)
        for h in (
            "robots.example.test",
            "paused.example.test",
            "down.example.test",
            "missing.example.test",
        )
    ]
    loaded = {c.host: c for c in cand.load_homepages(items, getter)}
    assert loaded["robots.example.test"].drop_reason == cand.DROP_ROBOTS
    assert loaded["robots.example.test"].robots == "disallowed"
    assert loaded["paused.example.test"].drop_reason == "site_paused"
    assert loaded["down.example.test"].drop_reason == cand.DROP_UNREACHABLE
    assert loaded["missing.example.test"].drop_reason == "http_404"
    assert all(c.outcome_hint == OUTCOME_DROPPED and c.home is None for c in loaded.values())


def test_a_monitored_site_that_cannot_be_read_stays_monitored() -> None:
    getter = FakeGetter(
        {"https://listed.example.test/": Fetched(0, "", "https://listed.example.test/")}
    )
    item = cand.Candidate(
        host="listed.example.test", gate_key="listed-key", outcome_hint=OUTCOME_MONITORED
    )
    (loaded,) = cand.load_homepages([item], getter)
    assert loaded.outcome_hint == OUTCOME_MONITORED and loaded.drop_reason == cand.DROP_UNREACHABLE


def test_a_redirect_to_another_host_replaces_the_host_and_merges_the_sources() -> None:
    getter = FakeGetter(
        {
            "https://old.example.test/": _fetched(
                "https://old.example.test/", final="https://www.new.example.test/start"
            ),
            "https://new.example.test/": _fetched("https://new.example.test/"),
        }
    )
    old = cand.Candidate(
        host="old.example.test", sources={SOURCE_GUESS}, extra={"guessed_host": "old.example.test"}
    )
    new = cand.Candidate(
        host="new.example.test", sources={SOURCE_NAME_SEARCH}, product_hits=[{"product_id": 1}]
    )
    merged = cand.load_homepages([old, new], getter)
    assert len(merged) == 1
    only = merged[0]
    assert only.host == "new.example.test"
    assert only.sources == {SOURCE_GUESS, SOURCE_NAME_SEARCH}
    assert only.product_hits == [{"product_id": 1}]
    assert only.redirected_from == "old.example.test"


def test_a_redirect_alone_renames_the_candidate_and_its_gate_key() -> None:
    getter = FakeGetter(
        {
            "https://old.example.test/": _fetched(
                "https://old.example.test/", final="https://new.example.test/"
            )
        }
    )
    (item,) = cand.load_homepages([cand.Candidate(host="old.example.test")], getter)
    assert item.host == "new.example.test" and item.redirected_from == "old.example.test"
    assert item.gate_key == "host:new.example.test"


def test_candidates_over_the_home_page_limit_are_dropped_not_fetched() -> None:
    getter = FakeGetter(
        {f"https://h{i}.example.test/": _fetched(f"https://h{i}.example.test/") for i in range(4)}
    )
    items = [cand.Candidate(host=f"h{i}.example.test") for i in range(4)]
    loaded = cand.load_homepages(items, getter, limit=2)
    assert len(getter.calls) == 2
    assert [c.drop_reason for c in loaded] == [
        None,
        None,
        cand.DROP_NOT_CHECKED,
        cand.DROP_NOT_CHECKED,
    ]


def test_items_already_dropped_are_not_fetched() -> None:
    getter = FakeGetter()
    item = cand.Candidate(
        host="x.example.test",
        outcome_hint=OUTCOME_DROPPED,
        drop_reason=cand.DROP_OTHER_CUSTOMER_SITE,
    )
    cand.load_homepages([item], getter)
    assert getter.calls == []
