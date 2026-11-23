"""Apply and the site-candidate steward decisions. cip_test only, rolled back.

The plan is built by hand (a Preview needs a read-only transaction of its own), with the same pure
``scoring.build_evidence`` the Preview uses, so Apply is tested against what a Preview stores.
Fictional names, ``.test`` hosts.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.customer_web_site import (
    WEB_SITE_CONFIRMED,
    WEB_SITE_PROPOSED,
    WEB_SITE_REJECTED,
    CustomerWebSite,
)
from app.models.dimensions import DimCustomer
from app.models.listing_site import ListingSite
from app.services import tenant_settings as ts
from app.services.listing_capture import discovery
from app.services.listing_capture.sites import create_site
from app.services.listing_capture.web_discovery import apply as web_apply
from app.services.listing_capture.web_discovery import preview, scoring
from app.services.listing_capture.web_discovery.apply import ApplyError
from app.services.listing_capture.web_discovery.homepage import parse_home
from app.services.listing_capture.web_discovery.settings import load_discovery_settings
from tests.web_discovery_db import ALPHA_HOST, ALPHA_NAME, BETA_NAME, World, outer_tx_session, world  # noqa: F401
from tests.web_discovery_support import COUNTRY, ENDINGS, fixture_text

PID = "11111111-1111-4111-8111-111111111111"
USER = {"email": "steward@example.test", "id": "steward-1"}


@pytest.fixture(autouse=True)
def audit_calls(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def record(user, **kwargs) -> None:
        calls.append({"user": user, **kwargs})

    monkeypatch.setattr(web_apply, "record_steward_audit_sync", record)
    return calls


def _hit(world: World, product_id: int | None = None) -> dict[str, Any]:
    return {
        "product_id": product_id if product_id is not None else world.product_id,
        "product_label": "Widget One",
        "query": '"Widget One" Testland',
        "rank": 1,
    }


def _entry(
    item_id: str,
    host: str,
    outcome: str,
    *,
    name: str = ALPHA_NAME,
    hits: list[dict[str, Any]] | None = None,
    sources: set[str] | None = None,
    status: int = 200,
) -> dict[str, Any]:
    evidence = scoring.build_evidence(
        host=host,
        customer_name=name,
        sources=sources or {scoring.SOURCE_GUESS},
        endings=ENDINGS,
        country=COUNTRY,
        home=parse_home(fixture_text("home_org_jsonld.html")),
        http_status=status,
        final_url=f"https://{host}/",
        robots="allowed",
        product_hits=hits or [],
    )
    return {
        "item_id": item_id,
        "domain": host,
        "outcome": outcome,
        "drop_reason": None,
        "proposed_site_key": discovery._site_key_from_origin(f"https://{host}"),
        "evidence": evidence,
    }


def _store_plan(
    session: Session,
    world: World,
    candidates: list[dict[str, Any]],
    *,
    customer_id: int | None = None,
    status: str = preview.STATUS_DONE,
    fingerprint: str | None = None,
    store: preview.MemoryPlanStore | None = None,
    preview_id: str = PID,
) -> preview.MemoryPlanStore:
    store = store or preview.MemoryPlanStore()
    plan = preview.new_plan(world.tenant, preview_id, {"scope": "reporting"})
    plan["status"] = status
    plan["settings_fingerprint"] = fingerprint or load_discovery_settings(session, world.tenant).fingerprint()
    plan["result"] = {
        "scope": "reporting",
        "customers": [
            {
                "customer_id": customer_id or world.alpha_id,
                "customer_name": ALPHA_NAME,
                "reporting": True,
                "notes": [],
                "candidates": candidates,
                "sites": [],
            }
        ],
        "listings": [],
        "totals": {},
    }
    store.save(world.tenant, preview_id, plan)
    return store


def _apply(session: Session, world: World, store: preview.MemoryPlanStore, preview_id: str = PID) -> dict[str, Any]:
    return web_apply.apply_plan(session, store, tenant_id=world.tenant, preview_id=preview_id, user=USER)


def _count(session: Session, table: str, world: World) -> int:
    return int(session.scalar(text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": world.tenant}))


def _row(session: Session, world: World, host: str, customer_id: int | None = None) -> CustomerWebSite | None:
    return session.scalar(
        select(CustomerWebSite).where(
            CustomerWebSite.tenant_id == world.tenant,
            CustomerWebSite.customer_id == (customer_id or world.alpha_id),
            CustomerWebSite.domain == host,
        )
    )


# --------------------------------------------------------------------------- what Apply writes


def test_apply_saves_the_confirmed_site_and_the_review_queue_and_nothing_else(
    outer_tx_session: Session, world: World, audit_calls
) -> None:
    session = outer_tx_session
    candidates = [
        _entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)]),
        _entry("c-2", "other.example.test", "steward_queue"),
        _entry("c-3", "down.example.test", "dropped", status=0),
        _entry("c-4", "monitored.example.test", "already_monitored"),
        _entry("c-5", "rejected.example.test", "already_rejected"),
    ]
    store = _store_plan(session, world, candidates)

    result = _apply(session, world, store)

    assert {k: v for k, v in result.items() if k not in ("applied_at",)} == {
        "sites_confirmed": 1,
        "sites_queued": 1,
        "sites_created": 1,
        "pages_linked": 0,
        "proposals_created": 0,
        "pages_queued": 0,
        "listings_linked": 0,
        "listings_queued": 0,
        "auto_links": [],
        "skipped": [],
    }
    confirmed = _row(session, world, ALPHA_HOST)
    assert confirmed is not None and confirmed.status == WEB_SITE_CONFIRMED and confirmed.source == "auto"
    assert confirmed.preview_id == PID and confirmed.decided_by == USER["email"] and confirmed.site_id is not None
    assert confirmed.evidence["name_match"]["exact"] is True
    site = session.get(ListingSite, confirmed.site_id)
    assert site.tenant_id == world.tenant
    assert site.site_key == discovery._site_key_from_origin(f"https://{ALPHA_HOST}")
    assert site.display_name == "Alpha Gadgets"  # the home page's organisation name

    queued = _row(session, world, "other.example.test")
    assert queued is not None and queued.status == WEB_SITE_PROPOSED and queued.source == "auto"
    assert queued.site_id is None  # a proposal creates no site

    for host in ("down.example.test", "monitored.example.test", "rejected.example.test"):
        assert _row(session, world, host) is None
    assert _count(session, "customer_web_site", world) == 2
    assert _count(session, "listing_site", world) == 1

    (audit,) = audit_calls
    assert audit["action"] == "discovery_apply" and audit["importer"] == "listing_discovery"
    assert audit["payload"]["preview_id"] == PID and audit["payload"]["counts"]["sites_confirmed"] == 1


def test_a_second_apply_returns_the_same_body_and_writes_nothing(
    outer_tx_session: Session, world: World, audit_calls
) -> None:
    session = outer_tx_session
    store = _store_plan(
        session,
        world,
        [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)]), _entry("c-2", "other.example.test", "steward_queue")],
    )
    first = _apply(session, world, store)
    before = (_count(session, "customer_web_site", world), _count(session, "listing_site", world))
    second = _apply(session, world, store)
    assert second == first
    assert (_count(session, "customer_web_site", world), _count(session, "listing_site", world)) == before
    assert len(audit_calls) == 1


def test_a_user_entered_domain_is_confirmed_even_without_the_other_evidence(
    outer_tx_session: Session, world: World
) -> None:
    session = outer_tx_session
    entry = _entry("c-1", "typed.example.test", "user_confirmed", sources={scoring.SOURCE_USER})
    store = _store_plan(session, world, [entry], customer_id=world.beta_id)
    result = _apply(session, world, store)
    assert result["sites_confirmed"] == 1 and result["skipped"] == []
    row = _row(session, world, "typed.example.test", world.beta_id)
    assert row.status == WEB_SITE_CONFIRMED and row.source == "user"


def test_a_second_customer_on_the_same_host_reuses_the_site(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    first = _apply(session, world, _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])]))
    assert first["sites_created"] == 1
    entry = _entry("c-1", ALPHA_HOST, "user_confirmed", name=BETA_NAME, sources={scoring.SOURCE_USER})
    other_pid = "22222222-2222-4222-8222-222222222222"
    store = _store_plan(session, world, [entry], customer_id=world.beta_id, preview_id=other_pid)
    second = _apply(session, world, store, other_pid)
    assert second["sites_confirmed"] == 1 and second["sites_created"] == 0
    assert _count(session, "listing_site", world) == 1
    assert _row(session, world, ALPHA_HOST).site_id == _row(session, world, ALPHA_HOST, world.beta_id).site_id


def test_a_site_whose_patterns_use_the_host_is_reused(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    mine = create_site(
        session,
        tenant_id=world.tenant,
        site_key="mine",
        fields={"search_url_pattern": f"https://www.{ALPHA_HOST}/search?q={{query}}"},
        actor=None,
    )
    result = _apply(session, world, _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])]))
    assert result["sites_created"] == 0
    assert _row(session, world, ALPHA_HOST).site_id == mine.id
    assert _count(session, "listing_site", world) == 1


def test_a_taken_site_key_gets_a_numbered_suffix(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    base = discovery._site_key_from_origin(f"https://{ALPHA_HOST}")
    create_site(session, tenant_id=world.tenant, site_key=base, fields={}, actor=None)
    _apply(session, world, _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])]))
    site = session.get(ListingSite, _row(session, world, ALPHA_HOST).site_id)
    assert site.site_key == f"{base}-2"


def test_unique_site_key_fits_the_length_limit() -> None:
    assert web_apply.unique_site_key("shop", {"other"}) == "shop"
    assert web_apply.unique_site_key("shop", {"shop"}) == "shop-2"
    assert web_apply.unique_site_key("shop", {"shop", "shop-2"}) == "shop-3"
    long_key = "a" * 32
    suffixed = web_apply.unique_site_key(long_key, {long_key})
    assert suffixed == "a" * 30 + "-2" and len(suffixed) == 32


# --------------------------------------------------------------------------- refusals


def test_changed_settings_refuse_the_apply(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    store = _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])])
    ts.set_setting(session, world.tenant, ts.KEY_TENANT_DOMAIN_ENDINGS, [".zz"], actor="test")
    with pytest.raises(ApplyError) as caught:
        _apply(session, world, store)
    assert (caught.value.code, caught.value.status_code) == ("settings_changed", 409)
    assert _count(session, "customer_web_site", world) == 0


def test_an_expired_plan_is_410_and_another_tenant_cannot_see_it(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    with pytest.raises(ApplyError) as caught:
        _apply(session, world, preview.MemoryPlanStore())
    assert (caught.value.code, caught.value.status_code) == ("preview_expired", 410)
    store = _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])])
    with pytest.raises(ApplyError) as other:
        web_apply.apply_plan(session, store, tenant_id="another-tenant", preview_id=PID, user=USER)
    assert other.value.status_code == 410


@pytest.mark.parametrize("status", [preview.STATUS_QUEUED, preview.STATUS_RUNNING, preview.STATUS_FAILED])
def test_a_preview_that_has_not_finished_cannot_be_applied(outer_tx_session: Session, world: World, status: str) -> None:
    session = outer_tx_session
    store = _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])], status=status)
    with pytest.raises(ApplyError) as caught:
        _apply(session, world, store)
    assert (caught.value.code, caught.value.status_code) == ("preview_not_done", 409)
    assert _count(session, "customer_web_site", world) == 0


# --------------------------------------------------------------------------- stale and tampered items


def test_an_item_rejected_since_the_preview_is_skipped(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    store = _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])])
    session.add(
        CustomerWebSite(
            tenant_id=world.tenant, customer_id=world.alpha_id, domain=ALPHA_HOST, status=WEB_SITE_REJECTED,
            source="steward", evidence={},
        )
    )
    session.flush()
    result = _apply(session, world, store)
    assert result["sites_confirmed"] == 0 and result["skipped"] == [{"item_id": "c-1", "reason": "changed_since_preview"}]
    assert _row(session, world, ALPHA_HOST).status == WEB_SITE_REJECTED
    assert _count(session, "listing_site", world) == 0


def test_a_queued_item_confirmed_since_the_preview_is_not_downgraded(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    store = _store_plan(session, world, [_entry("c-1", "other.example.test", "steward_queue")])
    session.add(
        CustomerWebSite(
            tenant_id=world.tenant, customer_id=world.alpha_id, domain="other.example.test",
            status=WEB_SITE_CONFIRMED, source="steward", evidence={},
        )
    )
    session.flush()
    result = _apply(session, world, store)
    assert result["sites_queued"] == 0 and result["skipped"] == [{"item_id": "c-1", "reason": "changed_since_preview"}]
    assert _row(session, world, "other.example.test").status == WEB_SITE_CONFIRMED


def test_every_item_of_a_customer_merged_away_since_the_preview_is_skipped(
    outer_tx_session: Session, world: World
) -> None:
    session = outer_tx_session
    store = _store_plan(
        session,
        world,
        [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)]), _entry("c-2", "other.example.test", "steward_queue")],
    )
    session.get(DimCustomer, world.alpha_id).merged_into_customer_id = world.beta_id
    session.flush()
    result = _apply(session, world, store)
    assert result["sites_confirmed"] == 0 and result["sites_queued"] == 0
    assert [s["item_id"] for s in result["skipped"]] == ["c-1", "c-2"]
    assert _count(session, "customer_web_site", world) == 0


def test_a_tampered_plan_cannot_raise_an_item_to_an_automatic_write(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    forged_name = _entry("c-1", "other.example.test", "auto_accept", hits=[_hit(world)])
    forged_name["evidence"]["name_match"] = {"exact": True, "customer_keys": ["other"], "domain_key": "other"}
    forged_name["evidence"]["country_match"] = {"value": True, "how": "cctld"}
    forged_hits = _entry("c-2", ALPHA_HOST, "auto_accept", hits=[_hit(world, product_id=2_000_000_000)])
    forged_user = _entry("c-3", "nothing-alike.example.test", "user_confirmed")  # no "user" source in the evidence
    store = _store_plan(session, world, [forged_name, forged_hits, forged_user])

    result = _apply(session, world, store)

    assert result["sites_confirmed"] == 0 and result["sites_queued"] == 0
    assert [(s["item_id"], s["reason"]) for s in result["skipped"]] == [
        ("c-1", "changed_since_preview"),
        ("c-2", "changed_since_preview"),
        ("c-3", "changed_since_preview"),
    ]
    assert _count(session, "customer_web_site", world) == 0
    assert _count(session, "listing_site", world) == 0


def test_a_product_hit_from_another_tenant_does_not_count(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    other_tenant_product = session.scalar(
        text("SELECT id FROM dim_product WHERE tenant_id <> :t ORDER BY id LIMIT 1"), {"t": world.tenant}
    )
    if other_tenant_product is None:
        pytest.skip("no product in another tenant on this database")
    entry = _entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world, product_id=int(other_tenant_product))])
    result = _apply(session, world, _store_plan(session, world, [entry]))
    assert result["sites_confirmed"] == 0 and len(result["skipped"]) == 1


# --------------------------------------------------------------------------- discovery reads confirmed sites


def test_discovery_reads_the_confirmed_site_of_a_customer(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    _apply(session, world, _store_plan(session, world, [_entry("c-1", ALPHA_HOST, "auto_accept", hits=[_hit(world)])]))
    key = discovery._site_key_from_origin(f"https://{ALPHA_HOST}")
    alpha_keys = discovery._site_keys(session, tenant_id=world.tenant, customer_id=world.alpha_id, seed={})
    assert key in alpha_keys  # next to the marketplace of the customer's own listing
    # Another customer of the tenant does not inherit it.
    assert discovery._site_keys(session, tenant_id=world.tenant, customer_id=world.beta_id, seed={}) == []


def test_a_proposed_site_is_not_read_by_discovery(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    _apply(session, world, _store_plan(session, world, [_entry("c-1", "other.example.test", "steward_queue")]))
    keys = discovery._site_keys(session, tenant_id=world.tenant, customer_id=world.alpha_id, seed={})
    assert discovery._site_key_from_origin("https://other.example.test") not in keys


def test_the_seed_origin_falls_back_to_a_confirmed_domain_only_when_the_seed_names_none() -> None:
    assert discovery._seed_origin({}, "shop.example.test") == "https://shop.example.test"
    assert discovery._seed_origin({}) is None
    assert discovery._seed_origin({"site": {"domain": "https://seeded.example.test"}}, "shop.example.test") == (
        "https://seeded.example.test"
    )
    assert discovery._seed_origin({}, "not a host/with path") is None


# --------------------------------------------------------------------------- steward decisions


def _proposed(session: Session, world: World, host: str = "queued.example.test") -> CustomerWebSite:
    row = CustomerWebSite(
        tenant_id=world.tenant,
        customer_id=world.alpha_id,
        domain=host,
        status=WEB_SITE_PROPOSED,
        source="auto",
        evidence=_entry("x", host, "steward_queue")["evidence"],
        preview_id=PID,
    )
    session.add(row)
    session.flush()
    return row


def test_the_queue_lists_proposals_with_the_customer_name_only(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    row = _proposed(session, world)
    items = web_apply.list_site_candidates(session, world.tenant)
    assert [(i["id"], i["customer_id"], i["customer_name"], i["domain"]) for i in items] == [
        (row.id, world.alpha_id, ALPHA_NAME, "queued.example.test")
    ]
    assert "name_match" in items[0]["evidence"] and items[0]["created_at"]
    assert web_apply.list_site_candidates(session, "another-tenant") == []
    assert web_apply.list_site_candidates(session, world.tenant, WEB_SITE_CONFIRMED) == []


def test_a_steward_confirms_a_proposal_then_rejects_it_without_deleting_the_site(
    outer_tx_session: Session, world: World, audit_calls
) -> None:
    session = outer_tx_session
    row = _proposed(session, world)

    confirmed = web_apply.decide_site_candidate(
        session, tenant_id=world.tenant, candidate_id=row.id, action="confirm", user=USER
    )
    assert confirmed == {"id": row.id, "status": WEB_SITE_CONFIRMED, "site_created": True}
    session.refresh(row)
    assert row.status == WEB_SITE_CONFIRMED and row.source == "steward" and row.decided_by == USER["email"]
    site_id = row.site_id
    assert site_id is not None and session.get(ListingSite, site_id).display_name

    with pytest.raises(ApplyError) as again:
        web_apply.decide_site_candidate(session, tenant_id=world.tenant, candidate_id=row.id, action="confirm", user=USER)
    assert (again.value.code, again.value.status_code) == ("not_proposed", 409)

    rejected = web_apply.decide_site_candidate(
        session, tenant_id=world.tenant, candidate_id=row.id, action="reject", user=USER
    )
    assert rejected["status"] == WEB_SITE_REJECTED and rejected["site_created"] is False
    session.refresh(row)
    assert row.status == WEB_SITE_REJECTED and row.site_id == site_id
    assert session.get(ListingSite, site_id) is not None  # a reject never deletes the site

    with pytest.raises(ApplyError) as twice:
        web_apply.decide_site_candidate(session, tenant_id=world.tenant, candidate_id=row.id, action="reject", user=USER)
    assert (twice.value.code, twice.value.status_code) == ("not_rejectable", 409)
    assert [c["action"] for c in audit_calls] == ["site_candidate_confirm", "site_candidate_reject"]


def test_a_proposal_can_be_rejected_directly_and_is_remembered(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    row = _proposed(session, world)
    web_apply.decide_site_candidate(session, tenant_id=world.tenant, candidate_id=row.id, action="reject", user=USER)
    session.refresh(row)
    assert row.status == WEB_SITE_REJECTED and row.site_id is None
    # A later Preview that finds the same host again must not save it.
    store = _store_plan(session, world, [_entry("c-1", "queued.example.test", "steward_queue")])
    result = _apply(session, world, store)
    assert result["sites_queued"] == 0 and len(result["skipped"]) == 1
    assert _row(session, world, "queued.example.test").status == WEB_SITE_REJECTED


def test_unknown_candidates_and_actions_are_refused(outer_tx_session: Session, world: World) -> None:
    session = outer_tx_session
    row = _proposed(session, world)
    with pytest.raises(ApplyError) as missing:
        web_apply.decide_site_candidate(session, tenant_id=world.tenant, candidate_id=2_000_000_000, action="confirm", user=USER)
    assert missing.value.status_code == 404
    with pytest.raises(ApplyError) as wrong_tenant:
        web_apply.decide_site_candidate(session, tenant_id="another-tenant", candidate_id=row.id, action="confirm", user=USER)
    assert wrong_tenant.value.status_code == 404
    with pytest.raises(ApplyError) as bad_action:
        web_apply.decide_site_candidate(session, tenant_id=world.tenant, candidate_id=row.id, action="delete", user=USER)
    assert (bad_action.value.code, bad_action.value.status_code) == ("action_invalid", 422)
